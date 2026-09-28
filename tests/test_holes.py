"""Perfil do canal e o solido que o corta."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pencil_tip_gen.config import HOLE_SHAPES
from pencil_tip_gen.holes import build_cutter, hole_profile


@pytest.mark.parametrize("shape", list(HOLE_SHAPES))
def test_perfil_tem_o_raio_circunscrito_pedido(make_params, shape):
    params = make_params(hole_shape=shape)
    profile = hole_profile(params)
    radii = np.linalg.norm(profile, axis=1)
    esperado = (params.hole_size + params.tolerance) / 2
    assert radii.max() == pytest.approx(esperado)
    assert radii.min() == pytest.approx(esperado)


@pytest.mark.parametrize("shape,lados", [(k, v) for k, v in HOLE_SHAPES.items() if v])
def test_poligonos_tem_o_numero_de_lados(make_params, shape, lados):
    assert len(hole_profile(make_params(hole_shape=shape))) == lados


@pytest.mark.parametrize("shape", ["triangle", "square", "hexagon", "octagon"])
def test_orientacao_padrao_deixa_face_plana_embaixo(make_params, shape):
    profile = hole_profile(make_params(hole_shape=shape))
    y_min = profile[:, 1].min()
    apoiados = np.isclose(profile[:, 1], y_min).sum()
    assert apoiados == 2, "a base deve ser uma aresta, nao um vertice"


def test_modo_entre_faces_aumenta_o_circunscrito(make_params):
    circum = make_params(hole_shape="hexagon", hole_size_mode="circum")
    inscribed = make_params(hole_shape="hexagon", hole_size_mode="inscribed")
    assert inscribed.hole_circumradius > circum.hole_circumradius
    profile = hole_profile(inscribed)
    entre_faces = 2 * abs(profile[:, 1].min())
    assert entre_faces == pytest.approx(inscribed.hole_size + inscribed.tolerance)


def test_rotacao_gira_o_perfil(make_params):
    base = hole_profile(make_params(hole_shape="square"))
    girado = hole_profile(make_params(hole_shape="square", hole_rotation=45.0))
    assert not np.allclose(base, girado)
    assert np.linalg.norm(girado, axis=1).max() == pytest.approx(
        np.linalg.norm(base, axis=1).max()
    )


def test_cortador_e_estanque_e_atravessa_a_peca(make_params):
    params = make_params()
    cutter, warnings = build_cutter(params, x_start=0.0, x_end=50.0, axis_y=8.0, axis_z=6.85)
    assert cutter.is_watertight and cutter.is_volume
    assert not warnings
    (x0, _, _), (x1, _, _) = cutter.bounds
    assert x0 < 0.0 and x1 > 50.0, "o cortador deve passar da peca nas duas pontas"


def _raio_no_x(cutter, x: float, axis_y: float, axis_z: float) -> float:
    """Maior distancia ao eixo entre os vertices do anel que fica em ``x``."""
    anel = cutter.vertices[np.isclose(cutter.vertices[:, 0], x)]
    assert len(anel) > 2, f"nenhum anel em x={x}"
    return float(
        np.linalg.norm(anel[:, 1:] - np.array([axis_y, axis_z]), axis=1).max()
    )


def test_boca_chanfrada_e_maior_que_a_secao_reta(make_params):
    params = make_params(chamfer=1.0)
    cutter, _ = build_cutter(params, 0.0, 50.0, axis_y=8.0, axis_z=6.85)
    boca = _raio_no_x(cutter, 0.0, 8.0, 6.85)
    reta = _raio_no_x(cutter, params.chamfer, 8.0, 6.85)
    assert reta == pytest.approx(params.hole_circumradius)
    assert boca == pytest.approx(params.hole_circumradius + params.chamfer)
    assert boca > reta


def test_ponta_cega_nao_e_perfurada(make_params):
    params = make_params(closed_end="right")
    cutter, _ = build_cutter(params, 0.0, 50.0, axis_y=8.0, axis_z=6.85)
    (x0, _, _), (x1, _, _) = cutter.bounds
    assert x1 == pytest.approx(50.0), "o lado cego para exatamente na tampa"
    assert x0 < 0.0, "o lado aberto continua atravessando"


def test_chanfro_e_reduzido_em_canal_curto(make_params):
    params = make_params(chamfer=1.0)
    cutter, warnings = build_cutter(params, 0.0, 4.0, axis_y=8.0, axis_z=6.85)
    assert cutter.is_watertight
    assert any("chanfro reduzido" in w for w in warnings)


def test_secao_do_circulo_bate_com_a_area_teorica(make_params):
    params = make_params(hole_segments=256)
    profile = hole_profile(params)
    from shapely.geometry import Polygon

    area = Polygon(profile).area
    assert area == pytest.approx(math.pi * params.hole_circumradius**2, rel=1e-3)
