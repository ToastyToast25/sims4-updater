"""Tests for update path planner (BFS shortest-path algorithm)."""

from __future__ import annotations

import pytest

from sims4_updater.core.exceptions import NoUpdatePathError
from sims4_updater.patch.manifest import FileEntry, Manifest, PatchEntry
from sims4_updater.patch.planner import _bfs_all_shortest, plan_update


def _patch(frm: str, to: str, size: int = 100) -> PatchEntry:
    """Helper to create a PatchEntry with a single file of given size."""
    return PatchEntry(
        version_from=frm,
        version_to=to,
        files=[FileEntry(url=f"{frm}_to_{to}.zip", size=size, md5="aaa")],
    )


def _manifest(patches: list[PatchEntry], latest: str = "") -> Manifest:
    """Helper to build a Manifest from patches."""
    if not latest:
        latest = patches[-1].version_to if patches else ""
    return Manifest(latest=latest, patches=patches)


class TestPlanUpdate:
    def test_already_up_to_date(self):
        m = _manifest([_patch("1.0", "2.0")], latest="2.0")
        plan = plan_update(m, "2.0")
        assert plan.is_up_to_date
        assert plan.step_count == 0
        assert plan.total_download_size == 0

    def test_single_hop(self):
        m = _manifest([_patch("1.0", "2.0", size=500)])
        plan = plan_update(m, "1.0")
        assert plan.step_count == 1
        assert plan.steps[0].patch.version_from == "1.0"
        assert plan.steps[0].patch.version_to == "2.0"
        assert plan.total_download_size == 500

    def test_multi_hop(self):
        m = _manifest(
            [
                _patch("1.0", "2.0"),
                _patch("2.0", "3.0"),
                _patch("3.0", "4.0"),
            ]
        )
        plan = plan_update(m, "1.0")
        assert plan.step_count == 3
        assert plan.steps[0].step_number == 1
        assert plan.steps[2].step_number == 3
        assert plan.steps[2].total_steps == 3

    def test_no_path_raises(self):
        m = _manifest([_patch("1.0", "2.0")], latest="3.0")
        with pytest.raises(NoUpdatePathError, match="No update path found"):
            plan_update(m, "1.0")

    def test_explicit_target_version(self):
        m = _manifest(
            [
                _patch("1.0", "2.0"),
                _patch("2.0", "3.0"),
            ]
        )
        plan = plan_update(m, "1.0", target_version="2.0")
        assert plan.target_version == "2.0"
        assert plan.step_count == 1

    def test_picks_shortest_path(self):
        # Two paths: 1->2->4 (2 hops) and 1->3->4 (2 hops) but first is smaller
        m = _manifest(
            [
                _patch("1.0", "2.0", size=50),
                _patch("2.0", "4.0", size=50),
                _patch("1.0", "3.0", size=200),
                _patch("3.0", "4.0", size=200),
            ],
            latest="4.0",
        )
        plan = plan_update(m, "1.0")
        assert plan.step_count == 2
        assert plan.total_download_size == 100  # picks the smaller path

    def test_prefers_fewer_steps_over_size(self):
        # Direct: 1->3 (1 hop, 500 bytes) vs 1->2->3 (2 hops, 100 bytes)
        m = _manifest(
            [
                _patch("1.0", "3.0", size=500),
                _patch("1.0", "2.0", size=50),
                _patch("2.0", "3.0", size=50),
            ],
            latest="3.0",
        )
        plan = plan_update(m, "1.0")
        assert plan.step_count == 1  # BFS prefers fewest steps
        assert plan.total_download_size == 500

    def test_step_numbering(self):
        m = _manifest([_patch("1.0", "2.0"), _patch("2.0", "3.0")])
        plan = plan_update(m, "1.0")
        assert plan.steps[0].step_number == 1
        assert plan.steps[0].total_steps == 2
        assert plan.steps[1].step_number == 2
        assert plan.steps[1].total_steps == 2


class TestBfsAllShortest:
    def test_start_equals_end(self):
        result = _bfs_all_shortest({}, "A", "A")
        assert result == [[]]

    def test_no_path(self):
        result = _bfs_all_shortest({"A": [_patch("A", "B")]}, "A", "C")
        assert result == []

    def test_single_path(self):
        p = _patch("A", "B")
        result = _bfs_all_shortest({"A": [p]}, "A", "B")
        assert len(result) == 1
        assert result[0] == [p]

    def test_multiple_shortest_paths(self):
        p1 = _patch("A", "B", size=100)
        p2 = _patch("A", "B", size=200)
        result = _bfs_all_shortest({"A": [p1, p2]}, "A", "B")
        assert len(result) == 2
