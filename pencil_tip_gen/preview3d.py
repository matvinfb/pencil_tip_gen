"""Render 3D da peca, para conferir de olho o que os numeros nao mostram.

Rasterizador proprio com z-buffer, sem dependencia nova: numpy ja vem com o
trimesh e o PNG e escrito na mao (zlib + quatro blocos).

A alternativa obvia -- ordenar os triangulos por profundidade e desenhar do
fundo para a frente, em SVG -- nao serve aqui. A peca e oca por dentro, e as
faces do canal tem profundidade media menor que a do painel grande a frente
delas, entao aparecem desenhadas por cima como listras que nao existem. Num
render de conferencia isso e pior que nao ter render.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import trimesh

from .solid import Solid

BACKGROUND = (0.980, 0.984, 0.992)
MATERIAL = (0.760, 0.755, 0.815)
LIGHT = (0.40, -0.55, 0.73)
AMBIENT = 0.32
SUPERSAMPLE = 2
GAP = 24  # pixels entre as duas vistas

# De cima, lendo o nome; e de frente para a boca do canal.
VIEWS = ((26.0, -40.0), (8.0, -84.0))


def _camera(elevation: float, azimuth: float):
    """Eixos da camera: para onde ela olha e o plano da tela."""
    elev, azim = np.radians(elevation), np.radians(azimuth)
    eye = np.array(
        [np.cos(elev) * np.sin(azim), -np.cos(elev) * np.cos(azim), np.sin(elev)]
    )
    right = np.cross((0.0, 0.0, 1.0), eye)
    right /= np.linalg.norm(right)
    return eye, right, np.cross(eye, right)


def _visible_triangles(mesh: trimesh.Trimesh, elevation: float, azimuth: float):
    """Projeta a malha e descarta as faces que dao as costas para a camera."""
    eye, right, up = _camera(elevation, azimuth)
    centered = mesh.vertices - mesh.centroid
    screen = np.column_stack((centered @ right, centered @ up))
    depth = centered @ eye

    facing = mesh.face_normals @ eye > 0
    faces = mesh.faces[facing]
    normals = mesh.face_normals[facing]

    light = np.array(LIGHT, dtype=np.float64)
    light /= np.linalg.norm(light)
    tone = AMBIENT + (1.0 - AMBIENT) * np.clip(normals @ light, 0.0, 1.0)
    colors = np.array(MATERIAL) * tone[:, None]
    return screen[faces], depth[faces], colors, screen


def _rasterize(triangles, depths, colors, width: int, height: int, origin, scale):
    """Pinta os triangulos num buffer com teste de profundidade por pixel."""
    image = np.empty((height, width, 3), dtype=np.float32)
    image[:] = BACKGROUND
    zbuffer = np.full((height, width), -np.inf, dtype=np.float64)

    pixels = (triangles - origin) * scale
    pixels[:, :, 1] = height - 1 - pixels[:, :, 1]

    for triangle, depth, color in zip(pixels, depths, colors):
        (x0, y0), (x1, y1), (x2, y2) = triangle
        min_x = max(int(np.floor(min(x0, x1, x2))), 0)
        max_x = min(int(np.ceil(max(x0, x1, x2))), width - 1)
        min_y = max(int(np.floor(min(y0, y1, y2))), 0)
        max_y = min(int(np.ceil(max(y0, y1, y2))), height - 1)
        if min_x > max_x or min_y > max_y:
            continue

        area = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(area) < 1e-12:
            continue

        xs = np.arange(min_x, max_x + 1) + 0.5
        ys = np.arange(min_y, max_y + 1) + 0.5
        grid_x, grid_y = np.meshgrid(xs, ys)

        first = ((y1 - y2) * (grid_x - x2) + (x2 - x1) * (grid_y - y2)) / area
        second = ((y2 - y0) * (grid_x - x2) + (x0 - x2) * (grid_y - y2)) / area
        third = 1.0 - first - second
        inside = (first >= 0) & (second >= 0) & (third >= 0)
        if not inside.any():
            continue

        z = first * depth[0] + second * depth[1] + third * depth[2]
        window = zbuffer[min_y : max_y + 1, min_x : max_x + 1]
        winner = inside & (z > window)
        if not winner.any():
            continue
        window[winner] = z[winner]
        image[min_y : max_y + 1, min_x : max_x + 1][winner] = color

    return image


def _downsample(image: np.ndarray, factor: int) -> np.ndarray:
    """Media dos blocos: e o antialiasing do supersampling."""
    if factor <= 1:
        return image
    height, width, channels = image.shape
    trimmed = image[: height // factor * factor, : width // factor * factor]
    blocks = trimmed.reshape(
        trimmed.shape[0] // factor, factor, trimmed.shape[1] // factor, factor, channels
    )
    return blocks.mean(axis=(1, 3))


def write_png(path: Path, image: np.ndarray) -> Path:
    """Grava um PNG RGB de 8 bits (zlib + IHDR/IDAT/IEND)."""
    data = np.clip(image * 255.0 + 0.5, 0, 255).astype(np.uint8)
    height, width, _ = data.shape
    raw = b"".join(b"\x00" + row.tobytes() for row in data)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    return path


def render_preview_3d(
    solid: Solid, path: Path, width: int = 1400, views=VIEWS
) -> Path:
    """Grava um PNG com a peca vista de alguns angulos, lado a lado."""
    mesh = solid.mesh
    scenes = [_visible_triangles(mesh, elev, azim) for elev, azim in views]

    # Uma escala so para todas as vistas, senao elas mentem sobre o tamanho.
    spans = []
    for _, _, _, screen in scenes:
        low, high = screen.min(axis=0), screen.max(axis=0)
        spans.append(high - low)
    total_span_x = sum(span[0] for span in spans)
    max_span_y = max(span[1] for span in spans)

    big_width = width * SUPERSAMPLE
    gap = GAP * SUPERSAMPLE
    margin = gap
    drawable = big_width - 2 * margin - gap * (len(scenes) - 1)
    scale = drawable / total_span_x
    big_height = int(round(max_span_y * scale)) + 2 * margin

    canvas = np.empty((big_height, big_width, 3), dtype=np.float32)
    canvas[:] = BACKGROUND

    left = margin
    for (triangles, depths, colors, screen), span in zip(scenes, spans):
        panel_width = int(round(span[0] * scale)) + 1
        panel_height = int(round(span[1] * scale)) + 1
        origin = screen.min(axis=0)
        panel = _rasterize(
            triangles, depths, colors, panel_width, panel_height, origin, scale
        )
        top = margin + (big_height - 2 * margin - panel_height) // 2
        canvas[top : top + panel_height, left : left + panel_width] = panel
        left += panel_width + gap

    return write_png(path, _downsample(canvas, SUPERSAMPLE))
