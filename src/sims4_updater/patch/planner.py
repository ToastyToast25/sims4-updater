"""
Update path planner — finds the chain of patches from current version to target.

Uses BFS on the patch graph to find the shortest path (fewest patch steps).
Falls back to smallest total download size when multiple paths have equal length.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .manifest import Manifest, PatchEntry
from ..core.exceptions import NoUpdatePathError


@dataclass
class UpdateStep:
    """A single step in an update path."""

    patch: PatchEntry
    step_number: int
    total_steps: int


@dataclass
class UpdatePlan:
    """Complete plan for updating from one version to another."""

    current_version: str
    target_version: str
    steps: list[UpdateStep] = field(default_factory=list)

    @property
    def total_download_size(self) -> int:
        return sum(step.patch.total_size for step in self.steps)

    @property
    def is_up_to_date(self) -> bool:
        return self.current_version == self.target_version

    @property
    def step_count(self) -> int:
        return len(self.steps)


def plan_update(
    manifest: Manifest,
    current_version: str,
    target_version: str | None = None,
) -> UpdatePlan:
    """Plan the update path from current version to target.

    Args:
        manifest: Parsed manifest with available patches.
        current_version: Currently installed version string.
        target_version: Version to update to. Defaults to manifest.latest.

    Returns:
        UpdatePlan with ordered steps.

    Raises:
        NoUpdatePathError if no path exists.
    """
    if target_version is None:
        target_version = manifest.latest

    if current_version == target_version:
        return UpdatePlan(
            current_version=current_version,
            target_version=target_version,
        )

    # Build adjacency list: version_from -> list of PatchEntry
    graph: dict[str, list[PatchEntry]] = {}
    for patch in manifest.patches:
        graph.setdefault(patch.version_from, []).append(patch)

    # BFS to find shortest path (fewest steps)
    paths = _bfs_all_shortest(graph, current_version, target_version)

    if not paths:
        raise NoUpdatePathError(
            f"No update path found from {current_version} to {target_version}.\n"
            f"Available patches may not cover this version gap."
        )

    # Among shortest paths, pick the one with smallest total download
    best_path = min(paths, key=lambda p: sum(patch.total_size for patch in p))

    total = len(best_path)
    steps = [
        UpdateStep(patch=patch, step_number=i + 1, total_steps=total)
        for i, patch in enumerate(best_path)
    ]

    return UpdatePlan(
        current_version=current_version,
        target_version=target_version,
        steps=steps,
    )


def _bfs_all_shortest(
    graph: dict[str, list[PatchEntry]],
    start: str,
    end: str,
) -> list[list[PatchEntry]]:
    """BFS finding all shortest paths from start to end.

    Returns list of paths (each path is a list of PatchEntry).
    """
    if start == end:
        return [[]]

    # BFS with path tracking
    queue: deque[tuple[str, list[PatchEntry]]] = deque()
    queue.append((start, []))

    # Track shortest distance to each node to prune longer paths
    best_dist: dict[str, int] = {start: 0}
    results: list[list[PatchEntry]] = []
    shortest_found = float("inf")

    while queue:
        current, path = queue.popleft()

        if len(path) >= shortest_found:
            continue

        for patch in graph.get(current, []):
            next_version = patch.version_to
            new_path = path + [patch]
            new_dist = len(new_path)

            if next_version == end:
                if new_dist <= shortest_found:
                    shortest_found = new_dist
                    results.append(new_path)
                continue

            # Only explore if we haven't found a shorter path to this node
            if next_version not in best_dist or new_dist <= best_dist[next_version]:
                best_dist[next_version] = new_dist
                queue.append((next_version, new_path))

    return results
