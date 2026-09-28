"""Malha final: estanqueidade, secao minima e parede ao redor do canal."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from pencil_tip_gen.profile2d import build_profile
from pencil_tip_gen.solid import BOOLEAN_ENGINE, build_solid, wall_coverage


@pytest.fixture(scope="module")
def solid_alice(font_path):
    from pencil_tip_gen.config import TipParams

    params = TipParams(font_path=font_path)
    return build_solid(build_profile("ALICE", params), params), params


def test_malha_e_estanque(solid_alice):
    solid, _ = solid_alice
    assert solid.mesh.is_watertight
    assert solid.mesh.is_volume
    assert solid.mesh.volume > 0


def test_secao_respeita_a_parede_minima(solid_alice):
    solid, params = solid_alice
    _, altura, profundidade = solid.extents
    assert altura >= params.section - 1e-6
    # O relevo fica acima da base e nao conta como parede em volta do canal.
    assert profundidade - solid.relief >= params.section - 1e-6


def test_o_lapis_atravessa_a_peca(solid_alice):
    """Um cilindro da bitola nominal passa livre de ponta a ponta."""
    solid, params = solid_alice
    profile = solid.profile
    comprimento = profile.hole_length + 20
    transform = trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0))
    transform[:3, 3] = (
        (profile.hole_x_start + profile.hole_x_end) / 2,
        profile.hole_axis_y,
        solid.depth / 2,
    )
    lapis = trimesh.creation.cylinder(
        radius=params.hole_size / 2, height=comprimento, sections=64, transform=transform
    )
    colisao = trimesh.boolean.intersection([lapis, solid.mesh], engine=BOOLEAN_ENGINE)
    assert len(colisao.faces) == 0, "o lapis nao deveria encostar em material"


def test_parede_minima_e_solida_em_todas_as_direcoes(solid_alice):
    """A casca entre o furo e o furo + parede tem que ser 100% material."""
    solid, params = solid_alice
    cobertura = wall_coverage(solid.mesh, solid.profile, params, solid.depth)
    assert cobertura == pytest.approx(1.0, abs=1e-3)


def test_volume_bate_com_a_area_do_perfil(solid_alice):
    solid, params = solid_alice
    profile = solid.profile
    # O canal corre em X: tira a area do furo vezes o comprimento do canal,
    # e nao vezes a profundidade da extrusao.
    area_furo = np.pi * params.hole_circumradius**2
    estimado = (
        profile.geometry.area * solid.depth
        + profile.text_geometry.area * solid.relief
        - area_furo * profile.hole_length
    )
    # O chanfro alarga a boca, entao o volume real fica um pouco menor.
    assert solid.mesh.volume == pytest.approx(estimado, rel=0.01)
    assert solid.mesh.volume < estimado


def test_profundidade_personalizada(make_params, font_path):
    params = make_params(depth=25.0)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.depth == pytest.approx(25.0)
    assert solid.extents[2] == pytest.approx(25.0 + params.relief)
    assert solid.mesh.is_watertight


def test_profundidade_minima_e_a_secao(make_params):
    params = make_params(depth=2.0)  # fino demais para o furo
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.depth == pytest.approx(params.section)


def test_relevo_levanta_so_as_letras(make_params):
    """O volume acima da base tem que ser exatamente as letras vezes o relevo."""
    params = make_params(relief=2.0)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.extents[2] == pytest.approx(params.target_depth + 2.0)
    caixa = trimesh.creation.box(
        extents=(500, 500, params.relief),
        transform=trimesh.transformations.translation_matrix(
            (0, 0, params.target_depth + params.relief / 2)
        ),
    )
    acima = trimesh.boolean.intersection([caixa, solid.mesh], engine=BOOLEAN_ENGINE)
    esperado = solid.profile.text_geometry.area * params.relief
    assert acima.volume == pytest.approx(esperado, rel=1e-3)


def test_sem_relevo_a_peca_tem_profundidade_uniforme(make_params):
    params = make_params(relief=0.0)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.extents[2] == pytest.approx(params.target_depth)
    assert solid.mesh.is_watertight


def test_relevo_funciona_com_borda(make_params):
    params = make_params(enable_border=True, relief=2.0)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.mesh.is_watertight and solid.mesh.is_volume
    assert solid.extents[2] == pytest.approx(params.target_depth + 2.0)


@pytest.mark.parametrize("shape", ["circle", "triangle", "square", "hexagon", "octagon"])
def test_todos_os_perfis_geram_malha_valida(make_params, shape):
    params = make_params(hole_shape=shape)
    solid = build_solid(build_profile("Bruno", params), params)
    assert solid.mesh.is_watertight and solid.mesh.is_volume


@pytest.mark.parametrize("name", ["Alice", "João", "Zoé", "i", "MM"])
def test_nomes_dificeis_geram_malha_valida(make_params, name):
    params = make_params()
    solid = build_solid(build_profile(name, params), params)
    assert solid.mesh.is_watertight and solid.mesh.is_volume


def test_ponta_cega_fica_solida(make_params):
    params = make_params(closed_end="right", cap_thickness=2.0, text_height=20.0)
    solid = build_solid(build_profile("ALICE", params), params)
    profile = solid.profile
    # Uma sonda dentro da tampa tem que encontrar material.
    sonda = trimesh.creation.box(
        extents=(1.0, 2.0, 2.0),
        transform=trimesh.transformations.translation_matrix(
            (profile.geometry.bounds[2] - 1.0, profile.hole_axis_y, solid.depth / 2)
        ),
    )
    dentro = trimesh.boolean.intersection([sonda, solid.mesh], engine=BOOLEAN_ENGINE)
    assert dentro.volume == pytest.approx(sonda.volume, rel=1e-3)


def test_espinha_fecha_a_parede_do_canal(make_params):
    """Com espinha a parede minima e garantida por construcao."""
    params = make_params(enable_spine=True)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.wall_coverage == pytest.approx(1.0, abs=1e-3)
    assert not any("parede" in w for w in solid.warnings)


def test_sem_espinha_a_parede_e_medida_e_avisada(make_params):
    """Sem espinha o canal atravessa as letras: vaza, e isso tem que aparecer."""
    params = make_params(enable_spine=False)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.mesh.is_watertight and solid.mesh.is_volume
    assert 0.0 < solid.wall_coverage < 0.99
    assert any("sem espinha" in w for w in solid.warnings)


def test_sem_espinha_gasta_menos_material(make_params):
    com = build_solid(
        build_profile("ALICE", make_params(enable_spine=True)),
        make_params(enable_spine=True),
    )
    sem = build_solid(
        build_profile("ALICE", make_params(enable_spine=False)),
        make_params(enable_spine=False),
    )
    assert sem.volume_cm3 < com.volume_cm3


def test_sem_base_a_peca_nao_engrossa_a_toa(make_params):
    params = make_params(enable_spine=False, enable_border=False, relief=2.0)
    solid = build_solid(build_profile("ALICE", params), params)
    assert solid.relief == 0.0
    assert solid.extents[2] == pytest.approx(params.target_depth)


@pytest.mark.parametrize("kwargs", [
    {"enable_spine": False},
    {"enable_spine": False, "enable_border": True},
    {"enable_spine": False, "closed_end": "right"},
    {"enable_spine": False, "letter_overlap": 0.0},
])
def test_malha_valida_sem_espinha(make_params, kwargs):
    params = make_params(**kwargs)
    solid = build_solid(build_profile("Bruno", params), params)
    assert solid.mesh.is_watertight and solid.mesh.is_volume
