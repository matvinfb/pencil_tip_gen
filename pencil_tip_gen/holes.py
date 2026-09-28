"""Perfil 2D do canal de encaixe e o solido usado para perfura-lo.

O cortador e sempre construido por *loft* de aneis ao longo de X: a mesma
rotina serve para o circulo e para os poligonos regulares, e o chanfro de
entrada e so um anel ampliado na boca do canal.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh
from shapely.geometry import Polygon

from .config import TipParams


class HoleError(ValueError):
    """Canal impossivel de construir com os parametros dados."""


def hole_profile(params: TipParams) -> np.ndarray:
    """Perfil do furo no plano YZ, centrado na origem, em milimetros.

    Retorna ``(n, 2)`` com os vertices em sentido anti-horario. A orientacao
    padrao deixa uma face plana embaixo (lapis sextavado apoiado), e
    ``--hole-rotation`` gira o perfil por cima disso.
    """
    sides = params.hole_sides
    radius = params.hole_circumradius
    if params.hole_shape == "circle":
        offset = 0.0
    else:
        # Impar: vertice para cima e face plana embaixo. Par: faces em cima e embaixo.
        offset = 90.0 if sides % 2 else 90.0 + 180.0 / sides
    start = math.radians(offset + params.hole_rotation)
    angles = start + np.arange(sides) * (2 * math.pi / sides)
    return np.column_stack((radius * np.cos(angles), radius * np.sin(angles)))


def hole_polygon(params: TipParams) -> Polygon:
    """Mesmo perfil, como poligono do shapely (usado no preview e nos testes)."""
    return Polygon(hole_profile(params))


def _loft(rings: list[tuple[float, float]], profile: np.ndarray) -> trimesh.Trimesh:
    """Gera um solido fechado a partir de aneis ``(x, fator_de_escala)``.

    Cada anel e o perfil escalado radialmente; os aneis sao ligados por quads e
    as duas pontas fechadas por leque a partir do centro (perfis convexos).
    """
    count = len(profile)
    vertices: list[np.ndarray] = []
    for x, factor in rings:
        block = np.column_stack(
            (np.full(count, x), profile[:, 0] * factor, profile[:, 1] * factor)
        )
        vertices.append(block)
    verts = np.vstack(vertices)

    faces: list[tuple[int, int, int]] = []
    for r in range(len(rings) - 1):
        base_a, base_b = r * count, (r + 1) * count
        for i in range(count):
            j = (i + 1) % count
            faces.append((base_a + i, base_a + j, base_b + j))
            faces.append((base_a + i, base_b + j, base_b + i))

    # Tampas: um vertice central em cada extremidade.
    first_center = len(verts)
    last_center = first_center + 1
    verts = np.vstack(
        (verts, [[rings[0][0], 0.0, 0.0], [rings[-1][0], 0.0, 0.0]])
    )
    last_base = (len(rings) - 1) * count
    for i in range(count):
        j = (i + 1) % count
        faces.append((first_center, j, i))
        faces.append((last_center, last_base + i, last_base + j))

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    if mesh.volume < 0:
        mesh.invert()
    if not mesh.is_watertight or not mesh.is_volume:
        raise HoleError("cortador do canal saiu com a malha aberta")
    return mesh


def build_cutter(
    params: TipParams,
    x_start: float,
    x_end: float,
    axis_y: float,
    axis_z: float,
) -> tuple[trimesh.Trimesh, list[str]]:
    """Cortador do canal, entre ``x_start`` e ``x_end``, centrado em (y, z).

    As bocas abertas recebem o chanfro de entrada de ``--chamfer`` (45 graus) e
    sao estendidas alem da peca para que a subtracao booleana nao deixe uma
    casquinha de face coplanar.
    """
    length = x_end - x_start
    if length <= 0:
        raise HoleError("comprimento do canal nao positivo")

    profile = hole_profile(params)
    radius = params.hole_circumradius
    warnings: list[str] = []

    chamfer = params.chamfer
    open_ends = 2 if params.closed_end == "none" else 1
    if chamfer > 0 and chamfer * open_ends > length / 3.0:
        chamfer = max(0.0, length / 3.0 / open_ends)
        warnings.append(
            f"chanfro reduzido para {chamfer:.2f} mm: o canal tem so {length:.2f} mm"
        )

    mouth = (radius + chamfer) / radius if chamfer > 0 else 1.0
    overshoot = max(0.05, 0.02 * length)

    rings: list[tuple[float, float]] = []
    if params.closed_end == "left":
        rings.append((x_start, 1.0))  # ponta cega, sem chanfro
    elif chamfer > 0:
        rings.append((x_start - overshoot, mouth))
        rings.append((x_start, mouth))
        rings.append((x_start + chamfer, 1.0))
    else:
        rings.append((x_start - overshoot, 1.0))

    if params.closed_end == "right":
        rings.append((x_end, 1.0))
    elif chamfer > 0:
        rings.append((x_end - chamfer, 1.0))
        rings.append((x_end, mouth))
        rings.append((x_end + overshoot, mouth))
    else:
        rings.append((x_end + overshoot, 1.0))

    cutter = _loft(rings, profile)
    cutter.apply_translation((0.0, axis_y, axis_z))
    return cutter, warnings
