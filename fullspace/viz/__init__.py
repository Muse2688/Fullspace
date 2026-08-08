"""3D sphere visualization of the capability manifold.

Renders the manifold's 3D projection as an interactive sphere in a
self-contained HTML file (uses the plotly.js CDN; no Python plotting
dependency). Capabilities are points on the unit sphere; an optional trajectory
is drawn as a path across the sphere. This is the visual manifestation of the
"3D sphere" vision — for human navigation/inspection only; routing never uses
these positions.
"""

from fullspace.viz.sphere import render_sphere

__all__ = ["render_sphere"]
