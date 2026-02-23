"""
Lightweight animation engine for CustomTkinter.

Uses tkinter's .after() for scheduling at ~60fps (16ms intervals).
Provides easing functions, color interpolation, and a reusable Animator class.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable

# -- Easing Functions -------------------------------------------------------


def ease_linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_quad(t: float) -> float:
    return 1 - (1 - t) * (1 - t)


# -- Color Utilities --------------------------------------------------------


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")[:6]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_color(hex_a: str, hex_b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _hex_to_rgb(hex_a)
    r2, g2, b2 = _hex_to_rgb(hex_b)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# -- Animator ---------------------------------------------------------------

FRAME_MS = 16  # ~60fps


class _Animation:
    __slots__ = (
        "widget",
        "duration_ms",
        "on_tick",
        "on_done",
        "easing",
        "start_time",
        "after_id",
        "tag",
    )

    def __init__(self, widget, duration_ms, on_tick, on_done, easing, tag):
        self.widget = widget
        self.duration_ms = duration_ms
        self.on_tick = on_tick
        self.on_done = on_done
        self.easing = easing
        self.tag = tag
        self.start_time = time.perf_counter()
        self.after_id = None


class Animator:
    def __init__(self):
        self._animations: list[_Animation] = []

    def animate(
        self,
        widget,
        duration_ms: int,
        on_tick: Callable[[float], None],
        on_done: Callable[[], None] | None = None,
        easing: Callable[[float], float] = ease_out_cubic,
        tag: str = "",
    ) -> _Animation:
        anim = _Animation(widget, duration_ms, on_tick, on_done, easing, tag)
        self._animations.append(anim)
        self._schedule(anim)
        return anim

    def animate_color(
        self,
        widget,
        prop: str,
        start: str,
        end: str,
        duration_ms: int,
        easing: Callable[[float], float] = ease_out_cubic,
        tag: str = "",
    ) -> _Animation:
        def on_tick(t):
            color = lerp_color(start, end, t)
            with contextlib.suppress(Exception):
                widget.configure(**{prop: color})

        return self.animate(widget, duration_ms, on_tick, easing=easing, tag=tag)

    def cancel_all(self, widget=None, tag: str = ""):
        to_remove = []
        for anim in self._animations:
            match = True
            if widget is not None and anim.widget is not widget:
                match = False
            if tag and anim.tag != tag:
                match = False
            if match:
                if anim.after_id is not None:
                    with contextlib.suppress(Exception):
                        anim.widget.after_cancel(anim.after_id)
                to_remove.append(anim)
        for anim in to_remove:
            self._animations.remove(anim)

    def _schedule(self, anim: _Animation):
        def step():
            elapsed = (time.perf_counter() - anim.start_time) * 1000
            raw_t = min(elapsed / anim.duration_ms, 1.0) if anim.duration_ms > 0 else 1.0
            eased_t = anim.easing(raw_t)

            try:
                anim.on_tick(eased_t)
            except Exception:
                self._remove(anim)
                return

            if raw_t >= 1.0:
                self._remove(anim)
                if anim.on_done:
                    with contextlib.suppress(Exception):
                        anim.on_done()
            else:
                anim.after_id = anim.widget.after(FRAME_MS, step)

        anim.after_id = anim.widget.after(FRAME_MS, step)

    def _remove(self, anim: _Animation):
        with contextlib.suppress(ValueError):
            self._animations.remove(anim)
