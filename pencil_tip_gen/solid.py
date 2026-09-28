"""Extrusao do perfil 2D, perfuracao do canal e validacao da malha final."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from .config import TipParams
from .geom import polygon_parts
from .holes import build_cutter
from .profile2d import Profile

BOOLEAN_ENGINE = "manifold"


class SolidError(ValueError):
    """Malha final invalida."""


@dataclass
class Solid:
    """Ponteira pronta para exportar."""

    mesh: trimesh.Trimesh
    profile: Profile
    depth: float
    relief: float = 0.0
    wall_coverage: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_depth(self) -> float:
        return self.depth + self.relief

    @property
    def extents(self) -> np.ndarray:
        return self.mesh.extents

    @property
    def volume_cm3(self) -> float:
        return float(self.mesh.volume) / 1000.0


def _rotation_z_to_x() -> np.ndarray:
    """Matriz que deita o eixo Z (padrao dos primitivos) sobre o eixo X."""
    return trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0))


def _extrude(geometry, height: float, what: str) -> trimesh.Trimesh:
    parts = [
        trimesh.creation.extrude_polygon(part, height=height)
        for part in polygon_parts(geometry)
    ]
    if not parts:
        raise SolidError(f"nada para extrudar em {what}")
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    if not mesh.is_watertight:
        raise SolidError(
            f"a extrusao {what} nao ficou estanque; tente aumentar "
            "--curve-tolerance para simplificar os contornos da fonte"
        )
    return mesh


def build_solid(profile: Profile, params: TipParams) -> Solid:
    """Extruda a base, levanta as letras em relevo e subtrai o canal do lapis.

    A base (espinha, borda e barras de suporte) vai de z=0 ate ``--depth``; as
    letras vao ate ``--depth + --relief``. O fundo fica plano e o nome sobressai
    numa face so, que e o que torna o nome legivel quando a borda esta ligada --
    ali a silhueta sozinha nao diz nada.
    """
    depth = params.target_depth
    relief = params.effective_relief
    body = _extrude(profile.geometry, depth, "do perfil")
    if relief > 0 and not profile.text_geometry.is_empty:
        letters = _extrude(profile.text_geometry, depth + relief, "das letras")
        body = trimesh.boolean.union([body, letters], engine=BOOLEAN_ENGINE)
        if isinstance(body, list):
            body = trimesh.util.concatenate(body)

    cutter, warnings = build_cutter(
        params,
        x_start=profile.hole_x_start,
        x_end=profile.hole_x_end,
        axis_y=profile.hole_axis_y,
        axis_z=depth / 2.0,
    )

    mesh = trimesh.boolean.difference([body, cutter], engine=BOOLEAN_ENGINE)
    if isinstance(mesh, list):  # defensivo: versoes antigas devolvem lista
        mesh = trimesh.util.concatenate(mesh)

    coverage, wall_warnings = validate_solid(mesh, profile, params, depth)
    warnings.extend(wall_warnings)
    return Solid(
        mesh=mesh,
        profile=profile,
        depth=depth,
        relief=relief,
        wall_coverage=coverage,
        warnings=warnings,
    )


def validate_solid(
    mesh: trimesh.Trimesh, profile: Profile, params: TipParams, depth: float
) -> tuple[float, list[str]]:
    """Confere estanqueidade, secao minima e parede ao redor do canal.

    Devolve a fracao da parede minima que e material e os avisos do caminho.
    """
    if not mesh.is_watertight:
        raise SolidError(
            "a malha final nao ficou estanque (watertight); "
            "verifique a fonte ou reduza --curve-tolerance"
        )
    if not mesh.is_volume:
        raise SolidError("a malha final nao delimita um volume valido")
    if mesh.volume <= 0:
        raise SolidError("a malha final tem volume nao positivo")

    warnings: list[str] = []
    _, height, thickness = mesh.extents
    thickness -= params.effective_relief  # o relevo nao e parede da base
    section = params.section
    tol = 1e-6
    if height + tol < section:
        raise SolidError(
            f"altura final {height:.2f} mm menor que a secao exigida {section:.2f} mm"
        )
    if thickness + tol < section:
        raise SolidError(
            f"profundidade final {thickness:.2f} mm menor que a secao exigida "
            f"{section:.2f} mm"
        )

    coverage = wall_coverage(mesh, profile, params, depth)
    if coverage < 0.999:
        falta = 100 * (1 - coverage)
        if params.enable_spine:
            warnings.append(
                f"a parede ao redor do canal esta {falta:.1f}% incompleta; "
                "aumente --border-width ou --text-height"
            )
        else:
            # Sem espinha isso e esperado: o canal atravessa as proprias letras,
            # entao vaza nas contra-formas e nos vaos. Vira informacao, nao susto.
            warnings.append(
                f"sem espinha, {falta:.1f}% da parede minima ao redor do canal e "
                "vazio (contra-formas e vaos entre letras); ligue --spine para "
                "fechar o canal ou use --hole-align/--hole-offset-y para procurar "
                "mais material"
            )
    return coverage, warnings


def wall_coverage(
    mesh: trimesh.Trimesh, profile: Profile, params: TipParams, depth: float
) -> float:
    """Fracao da casca de parede minima que e realmente material solido.

    Constroi o tubo entre o raio do furo e o raio do furo mais a parede minima,
    ignorando as regioes de chanfro nas pontas, e mede quanto dele esta dentro
    da peca. 1.0 significa que a regra do README (secao 4.3) foi cumprida em
    todas as direcoes, e nao so nos eixos.
    """
    margin = params.chamfer + 0.01
    x0 = profile.hole_x_start + margin
    x1 = profile.hole_x_end - margin
    length = x1 - x0
    if length <= 0.1:
        return 1.0

    radius = params.hole_circumradius
    transform = _rotation_z_to_x()
    transform[:3, 3] = ((x0 + x1) / 2.0, profile.hole_axis_y, depth / 2.0)

    outer = trimesh.creation.cylinder(
        radius=radius + params.min_wall_thickness,
        height=length,
        sections=96,
        transform=transform,
    )
    inner = trimesh.creation.cylinder(
        radius=radius, height=length * 1.1, sections=96, transform=transform
    )
    shell = trimesh.boolean.difference([outer, inner], engine=BOOLEAN_ENGINE)
    if shell.volume <= 0:
        return 1.0
    solid_part = trimesh.boolean.intersection([shell, mesh], engine=BOOLEAN_ENGINE)
    return float(solid_part.volume / shell.volume)
