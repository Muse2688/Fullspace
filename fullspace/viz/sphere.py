"""Render the capability manifold as an interactive 3D sphere (HTML, no deps)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from fullspace.manifold.manifold import Manifold

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _plotly_js() -> str:
    """Inline the plotly bundle when the package is installed (offline-ready);
    fall back to the CDN otherwise so the zero-dep default still works online."""
    try:
        from plotly.offline import get_plotlyjs  # type: ignore

        return "<script>" + get_plotlyjs() + "</script>"
    except ImportError:  # pragma: no cover - fallback path
        return f"<script src='{PLOTLY_CDN}'></script>"

_JS_BODY = r"""
const DATA = window.__FS_DATA__;
const nodes = DATA.nodes;
const normal = nodes.filter(n => !n.sink);
const sinks = nodes.filter(n => n.sink);
function scatter(arr, name, color, size) {
  return {
    type: 'scatter3d', mode: 'markers+text', name: name,
    x: arr.map(n => n.pos[0]), y: arr.map(n => n.pos[1]), z: arr.map(n => n.pos[2]),
    text: arr.map(n => n.label), textposition: 'top center',
    marker: {size: size, color: color, line: {width: 0.5, color: '#1e293b'}},
    hovertemplate: '<b>%{text}</b><br>%{x:.2f}, %{y:.2f}, %{z:.2f}<extra></extra>'
  };
}
const traces = [];
traces.push({
  type: 'surface', x: DATA.surface[0], y: DATA.surface[1], z: DATA.surface[2],
  opacity: 0.06, showscale: false, colorscale: [[0, '#3b82f6'], [1, '#3b82f6']],
  name: 'sphere', hoverinfo: 'skip'
});
traces.push(scatter(normal, 'capability', '#60a5fa', 7));
traces.push(scatter(sinks, 'sink', '#ef4444', 9));
if (DATA.path && DATA.path.pts && DATA.path.pts.length) {
  const p = DATA.path.pts;
  traces.push({
    type: 'scatter3d', mode: 'lines+markers', name: 'trajectory',
    x: p.map(q => q[0]), y: p.map(q => q[1]), z: p.map(q => q[2]),
    line: {color: '#f59e0b', width: 5}, marker: {size: 5, color: '#f59e0b'}
  });
}
Plotly.newPlot('chart', traces, {
  title: {text: 'Fullspace — capability manifold (3D projection of the high-dim space)'},
  scene: {xaxis: {visible: false}, yaxis: {visible: false}, zaxis: {visible: false},
          aspectmode: 'data'},
  margin: {l: 0, r: 0, t: 40, b: 0}, showlegend: true, legend: {x: 0, y: 1}
}, {displayModeBar: true});
"""


def _on_unit_sphere(v: np.ndarray) -> np.ndarray:
    """Project a 3D point radially onto the unit sphere (the 'sphere' look)."""
    n = np.linalg.norm(v)
    return (v / n).astype(np.float32) if n > 0 else v.astype(np.float32)


def _sphere_surface(n: int = 24):
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    x = np.outer(np.cos(u), np.sin(v))
    y = np.outer(np.sin(u), np.sin(v))
    z = np.outer(np.ones_like(u), np.cos(v))
    return x.tolist(), y.tolist(), z.tolist()


def render_sphere(
    manifold: Manifold,
    trajectory: Optional[list[str]] = None,
    step_groups: Optional[list[list[str]]] = None,
    output_path: str = "fullspace_sphere.html",
    title: str = "Fullspace capability manifold",
) -> str:
    """Write an interactive 3D HTML view of the manifold to ``output_path``.

    Args:
        manifold: the capability manifold (must have capabilities registered).
        trajectory: optional flat list of visited capability ids (drawn as a path).
        step_groups: optional per-step groups (preferred over ``trajectory``;
            flattened for the path).
        output_path: where to write the self-contained HTML file.
    """
    positions = manifold.project_all()
    pts = {cid: _on_unit_sphere(np.asarray(p, dtype=np.float32)).tolist() for cid, p in positions.items()}
    caps = manifold.capabilities
    nodes = [
        {
            "id": cid,
            "label": cid,
            "description": caps[cid].description,
            "pos": pts[cid],
            "sink": caps[cid].is_sink,
        }
        for cid in pts
    ]

    flat: list[str] = []
    if step_groups:
        for g in step_groups:
            flat.extend(g)
    elif trajectory:
        flat = list(trajectory)
    path = None
    if flat:
        path = {
            "ids": [c for c in flat if c in pts],
            "pts": [pts[c] for c in flat if c in pts],
        }

    surf_x, surf_y, surf_z = _sphere_surface()
    data = json.dumps({"nodes": nodes, "path": path, "surface": [surf_x, surf_y, surf_z]})

    html = (
        "<!DOCTYPE html>\n<html lang='en'><head><meta charset='utf-8'>\n"
        f"<title>{title}</title>\n"
        + _plotly_js()
        + "\n<style>body{margin:0;font-family:system-ui,sans-serif;background:#0b1020;color:#e2e8f0}"
        "#chart{width:100vw;height:100vh}</style>\n"
        "</head><body><div id='chart'></div>\n"
        "<script>window.__FS_DATA__ = " + data + ";</script>\n"
        "<script>\n" + _JS_BODY + "\n</script></body></html>"
    )
    out = Path(output_path)
    out.write_text(html, encoding="utf-8")
    return str(out)
