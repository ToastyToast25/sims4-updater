"""
Steam price service — fetches DLC pricing from the Steam Store API.

Caching: In-memory TTL cache (30 minutes). Prices rarely change mid-session.
Rate limiting: Steam allows ~200 requests per 5 minutes. With ~109 DLCs
and 8 concurrent workers, a single batch fetch completes in ~3 seconds.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import requests

logger = logging.getLogger(__name__)

STEAM_API_URL = "https://store.steampowered.com/api/appdetails"
STEAM_STORE_URL = "https://store.steampowered.com/app/{app_id}"
CACHE_TTL_SECONDS = 1800  # 30 minutes
REQUEST_TIMEOUT = 10
MAX_WORKERS = 8


@dataclass
class SteamPrice:
    """Pricing info for a single DLC from Steam."""

    app_id: int
    currency: str = "USD"
    initial_cents: int = 0
    final_cents: int = 0
    discount_percent: int = 0
    initial_formatted: str = ""
    final_formatted: str = ""
    is_free: bool = False

    @property
    def on_sale(self) -> bool:
        return self.discount_percent > 0

    @property
    def store_url(self) -> str:
        return STEAM_STORE_URL.format(app_id=self.app_id)


class SteamPriceCache:
    """In-memory cache with TTL for Steam price data."""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS):
        self._ttl = ttl
        self._data: dict[int, SteamPrice] = {}
        self._fetched_at: float = 0.0
        self.is_fetching: bool = False

    @property
    def is_valid(self) -> bool:
        return bool(self._data) and (time.monotonic() - self._fetched_at) < self._ttl

    def get(self, app_id: int) -> SteamPrice | None:
        if not self.is_valid:
            return None
        return self._data.get(app_id)

    def get_all(self) -> dict[int, SteamPrice]:
        if not self.is_valid:
            return {}
        return dict(self._data)

    def update(self, prices: dict[int, SteamPrice]):
        self._data.update(prices)
        self._fetched_at = time.monotonic()

    def clear(self):
        self._data.clear()
        self._fetched_at = 0.0


def _fetch_single_price(
    session: requests.Session, app_id: int, cc: str = "US",
) -> SteamPrice | None:
    """Fetch price for a single Steam app ID. Returns None on error."""
    try:
        resp = session.get(
            STEAM_API_URL,
            params={"appids": str(app_id), "cc": cc, "filters": "price_overview"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        app_data = data.get(str(app_id), {})
        if not app_data.get("success"):
            return None

        po = app_data.get("data", {}).get("price_overview")
        if po is None:
            return SteamPrice(app_id=app_id, is_free=True)

        return SteamPrice(
            app_id=app_id,
            currency=po.get("currency", "USD"),
            initial_cents=po.get("initial", 0),
            final_cents=po.get("final", 0),
            discount_percent=po.get("discount_percent", 0),
            initial_formatted=po.get("initial_formatted", ""),
            final_formatted=po.get("final_formatted", ""),
        )
    except Exception as e:
        logger.debug("Steam price fetch failed for %s: %s", app_id, e)
        return None


def fetch_prices_batch(
    app_ids: list[int],
    cc: str = "US",
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[int, SteamPrice]:
    """Fetch prices for multiple app IDs concurrently.

    Args:
        app_ids: List of Steam app IDs to fetch.
        cc: Country code for pricing (default US).
        on_progress: Optional callback(completed, total).

    Returns:
        Dict mapping app_id -> SteamPrice for successful fetches.
    """
    if not app_ids:
        return {}

    results: dict[int, SteamPrice] = {}
    total = len(app_ids)
    completed = 0

    session = requests.Session()
    session.headers["User-Agent"] = "Sims4Updater/1.0"

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_single_price, session, app_id, cc): app_id
                for app_id in app_ids
            }
            for future in as_completed(futures):
                app_id = futures[future]
                try:
                    price = future.result()
                    if price is not None:
                        results[app_id] = price
                except Exception:
                    pass
                completed += 1
                if on_progress:
                    on_progress(completed, total)
    finally:
        session.close()

    return results
