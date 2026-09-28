"""Preview do perfil em SVG, na escala 1:1 (1 unidade = 1 mm).

Duas vistas: a silhueta no plano XY (o que se le na peca, com o canal
tracejado por dentro) e a secao no plano YZ na ponta direita, mostrando o
perfil real do furo dentro do retangulo altura x profundidade.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

from .config import TipParams
from .geom import polygon_parts
from .holes import hole_profile
from .solid import Solid

MARGIN = 12.0
GAP = 14.0
LABEL = 3.2
LINE = 4.6
# Largura media de um caractere monoespacado no corpo usado nos rotulos.
CHAR_WIDTH = LABEL * 0.62

_STYLE = """
  .body { fill: #d8dee9; stroke: #2e3440; stroke-width: 0.25; }
  .hole { fill: #ffffff; stroke: #bf616a; stroke-width: 0.3;
          stroke-dasharray: 1.6 1.2; }
  .axis { stroke: #bf616a; stroke-width: 0.2; stroke-dasharray: 3 1.5 0.6 1.5; }
  .spine { fill: none; stroke: #5e81ac; stroke-width: 0.2;
           stroke-dasharray: 2 1.5; }
  .text { fill: none; stroke: #5e81ac; stroke-width: 0.15; opacity: 0.75; }
  .dim { stroke: #4c566a; stroke-width: 0.18; }
  .txt { font-family: monospace; font-size: 3.2px; fill: #2e3440; }
  .ttl { font-family: monospace; font-size: 4.4px; fill: #2e3440;
         font-weight: bold; }
"""


def _ring_path(coords, flip_height: float, dx: float, dy: float) -> str:
    parts = []
    for i, (x, y) in enumerate(coords):
        command = "M" if i == 0 else "L"
        parts.append(f"{command}{x + dx:.3f},{flip_height - y + dy:.3f}")
    parts.append("Z")
    return "".join(parts)


def _polygon_path(polygon: Polygon, flip_height: float, dx: float, dy: float) -> str:
    path = _ring_path(polygon.exterior.coords, flip_height, dx, dy)
    for interior in polygon.interiors:
        path += _ring_path(interior.coords, flip_height, dx, dy)
    return path


def render_preview(solid: Solid, params: TipParams, text: str, path: Path) -> Path:
    """Grava o SVG do perfil e devolve o caminho."""
    profile = solid.profile
    width, height = float(profile.width), float(profile.height)
    depth, relief = solid.depth, solid.relief

    lines = [
        f"{width:.2f} x {height:.2f} x {depth + relief:.2f} mm (X x Y x Z)"
        f"  |  volume {solid.volume_cm3:.2f} cm3",
        f"furo {params.hole_shape} {params.hole_size:g} + {params.tolerance:g} mm"
        f"  |  parede {params.min_wall_thickness:g} mm"
        f"  |  chanfro {params.chamfer:g} mm"
        f"  |  letras {profile.text_height:.2f} mm"
        + ("" if profile.spine is not None else "  |  sem espinha")
        + (f"  |  relevo {relief:g} mm sobre base de {depth:g} mm" if relief else ""),
    ]
    label_width = max(len(line) for line in lines) * CHAR_WIDTH
    canvas_w = MARGIN * 2 + max(width + GAP + depth + relief, label_width)
    canvas_h = MARGIN * 2 + height + 8.0 + LINE * len(lines)
    top = MARGIN

    # --- vista XY -----------------------------------------------------
    body = _polygon_path(profile.geometry, height, MARGIN, top)
    letters = "".join(
        _polygon_path(part, height, MARGIN, top)
        for part in polygon_parts(profile.text_geometry)
    )
    hole = hole_profile(params)
    hole_half = float(np.abs(hole[:, 1]).max())
    axis = profile.hole_axis_y
    hx0, hx1 = profile.hole_x_start, profile.hole_x_end
    spine_block = ""
    if profile.spine is not None:
        sx0, sy0, sx1, sy1 = profile.spine.bounds
        spine_block = (
            f'  <rect class="spine" x="{MARGIN + sx0:.3f}" '
            f'y="{top + height - sy1:.3f}" '
            f'width="{sx1 - sx0:.3f}" height="{sy1 - sy0:.3f}"/>'
        )

    # --- vista da secao YZ (ponta direita) ----------------------------
    section_x = MARGIN + width + GAP
    section_poly = Polygon(np.column_stack((hole[:, 1] + depth / 2.0, hole[:, 0] + axis)))
    section_path = _polygon_path(section_poly, height, section_x, top)

    # Degrau do relevo na vista da secao: ate onde as letras sobem.
    relief_block = (
        f'  <rect class="spine" x="{section_x + depth:.3f}" y="{top:.3f}" '
        f'width="{relief:.3f}" height="{height:.3f}"/>'
        if relief
        else ""
    )

    label_block = "\n".join(
        f'  <text class="txt" x="{MARGIN:.3f}" '
        f'y="{top + height + 12.0 + i * LINE:.3f}">{_escape(line)}</text>'
        for i, line in enumerate(lines)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" version="1.1"
     width="{canvas_w:.2f}mm" height="{canvas_h:.2f}mm"
     viewBox="0 0 {canvas_w:.3f} {canvas_h:.3f}">
  <style>{_STYLE}</style>
  <rect width="{canvas_w:.3f}" height="{canvas_h:.3f}" fill="#fbfbfd"/>
  <path class="body" fill-rule="evenodd" d="{body}"/>
  <path class="text" fill-rule="evenodd" d="{letters}"/>
{spine_block}
  <rect class="hole" x="{MARGIN + hx0:.3f}" y="{top + height - axis - hole_half:.3f}"
        width="{hx1 - hx0:.3f}" height="{2 * hole_half:.3f}"/>
  <line class="axis" x1="{MARGIN - 4:.3f}" y1="{top + height - axis:.3f}"
        x2="{MARGIN + width + 4:.3f}" y2="{top + height - axis:.3f}"/>
  <rect class="body" fill="none" x="{section_x:.3f}" y="{top:.3f}"
        width="{depth:.3f}" height="{height:.3f}"/>
{relief_block}
  <path class="hole" d="{section_path}"/>
  <text class="ttl" x="{MARGIN:.3f}" y="{top + height + 7:.3f}">{_escape(text)}</text>
{label_block}
  <text class="txt" x="{section_x:.3f}" y="{top + height + 7:.3f}">secao YZ</text>
</svg>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return path


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
