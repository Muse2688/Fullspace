"""Tests for the 3D sphere visualization (Phase 5)."""

from __future__ import annotations

import json
from pathlib import Path

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.viz import render_sphere


def test_render_sphere_writes_valid_html(tmp_path: Path):
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha topic"),
            Capability("b", "beta topic"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    out = render_sphere(m, output_path=str(tmp_path / "sphere.html"))
    html = Path(out).read_text(encoding="utf-8")
    assert "<html" in html and "plotly" in html.lower()
    # The embedded data contains all capability ids and positions.
    raw = html.split("window.__FS_DATA__ = ", 1)[1].split(";</script>", 1)[0]
    data = json.loads(raw)
    ids = {n["id"] for n in data["nodes"]}
    assert ids == {"a", "b", "end"}
    for n in data["nodes"]:
        assert len(n["pos"]) == 3  # 3D, on the sphere


def test_render_sphere_includes_trajectory(tmp_path: Path):
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha begin"),
            Capability("b", "beta middle"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)
    eng.bind("a", lambda ctx: NodeResult(intent="beta middle"))
    eng.bind("b", lambda ctx: NodeResult(goto="end"))
    eng.bind("end", lambda ctx: NodeResult())
    res = eng.run("alpha begin")

    out = render_sphere(m, step_groups=res.step_groups, output_path=str(tmp_path / "t.html"))
    html = Path(out).read_text(encoding="utf-8")
    raw = html.split("window.__FS_DATA__ = ", 1)[1].split(";</script>", 1)[0]
    data = json.loads(raw)
    assert data["path"] is not None
    assert data["path"]["ids"] == ["a", "b", "end"]
