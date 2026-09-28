"""Perfil 2D: escala, espinha, borda, barras de suporte e conexidade."""

from __future__ import annotations

import pytest
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box

from pencil_tip_gen.fonts import outline_text
from pencil_tip_gen.profile2d import (
    PINCH_TOLERANCE,
    ProfileError,
    build_profile,
    connect_components,
    contact_shift,
    drop_collinear_vertices,
    has_pinch,
    heal_pinches,
    layout_letters,
)


def test_perfil_e_uma_peca_unica(params):
    profile = build_profile("ALICE", params)
    assert profile.geometry.geom_type == "Polygon"
    assert profile.geometry.is_valid


def test_altura_nunca_fica_abaixo_da_secao(make_params):
    params = make_params(text_height=5.0)  # pedido menor que a secao
    profile = build_profile("ALICE", params)
    assert profile.text_height == pytest.approx(params.section)
    assert any("ampliadas" in w for w in profile.warnings)


def test_altura_automatica_respeita_o_comprimento_maximo(params):
    profile = build_profile("ALICE", params)
    assert profile.width <= params.max_length + 1e-6
    assert profile.text_height >= params.readable_text_height - 1e-9


def test_altura_automatica_tem_teto(make_params):
    params = make_params(max_text_height=24.0)
    profile = build_profile("Ana", params)
    assert profile.text_height == pytest.approx(24.0)


def test_teto_explicito_vence_o_piso_de_legibilidade(make_params):
    """Teto abaixo do piso legivel e obedecido, com aviso -- mas nunca fura a secao."""
    params = make_params(max_text_height=18.0)
    profile = build_profile("Ana", params)
    assert profile.text_height == pytest.approx(18.0)
    assert profile.text_height >= params.section
    assert any("legivel" in w for w in profile.warnings)


def test_teto_nunca_desce_abaixo_da_secao(make_params):
    params = make_params(max_text_height=5.0)
    profile = build_profile("Ana", params)
    assert profile.text_height == pytest.approx(params.section)


def test_espinha_cobre_toda_a_faixa_do_furo(params):
    profile = build_profile("ALICE", params)
    band = box(
        profile.hole_x_start,
        profile.hole_axis_y - params.section / 2,
        profile.hole_x_end,
        profile.hole_axis_y + params.section / 2,
    )
    # O arredondamento microscopico dos cantos (fechamento morfologico) faz
    # contains() falhar por micrometros; o que importa e a area descoberta.
    assert band.difference(profile.geometry).area < 1e-4


def test_alinhamento_do_furo(make_params):
    baixo = build_profile("ALICE", make_params(hole_align="bottom"))
    centro = build_profile("ALICE", make_params(hole_align="center"))
    alto = build_profile("ALICE", make_params(hole_align="top"))
    assert baixo.hole_axis_y < centro.hole_axis_y < alto.hole_axis_y


def test_offset_desloca_o_eixo(make_params):
    base = build_profile("ALICE", make_params())
    movido = build_profile("ALICE", make_params(hole_offset_y=2.0))
    assert movido.hole_axis_y == pytest.approx(base.hole_axis_y + 2.0)


def test_pingo_do_i_recebe_barra_de_suporte(make_params):
    params = make_params(enable_border=False)
    profile = build_profile("i", params)
    assert profile.geometry.geom_type == "Polygon"
    assert any("barra" in w for w in profile.warnings)


def test_sem_barras_o_pingo_solto_e_erro(make_params):
    params = make_params(enable_border=False, enable_struts=False)
    with pytest.raises(ProfileError, match="desconexos"):
        build_profile("i", params)


def test_tampa_alonga_a_peca_e_encurta_o_canal(make_params):
    # Altura fixa: com altura automatica a tampa entraria na conta do
    # comprimento maximo e as duas pecas sairiam do mesmo tamanho.
    aberto = build_profile("ALICE", make_params(text_height=20.0))
    tampado = build_profile(
        "ALICE", make_params(text_height=20.0, closed_end="right", cap_thickness=2.0)
    )
    assert tampado.width == pytest.approx(aberto.width + 2.0)
    assert tampado.hole_length == pytest.approx(aberto.hole_length)
    assert tampado.hole_x_end < tampado.geometry.bounds[2]


def test_conexao_de_pedacos_soltos():
    solto = box(0, 0, 2, 2).union(box(0, 5, 2, 7))
    ligado, struts = connect_components(solto, strut_width=1.0)
    assert struts == 1
    assert ligado.geom_type == "Polygon"


def test_pinca_e_detectada_e_curada():
    # Anel que passa duas vezes por (2, 2): os dois lobos se tocam num ponto.
    pinched = Polygon(
        [(0, 0), (2, 0), (2, 2), (4, 2), (4, 4), (2, 4), (2, 2), (0, 2)]
    )
    assert has_pinch(pinched)
    healed = heal_pinches(pinched)
    assert not has_pinch(healed)
    assert healed.contains(Point(2, 2))


def test_pedacos_que_so_se_encostam_sao_fundidos():
    tocando = box(0, 0, 2, 2).union(box(2, 2, 4, 4))
    assert tocando.geom_type == "MultiPolygon"
    ligado, struts = connect_components(tocando, strut_width=1.0)
    assert ligado.geom_type == "Polygon"
    assert struts == 0, "fundir um contato nao e uma barra de suporte"


def test_vertices_colineares_sao_removidos():
    # Quadrado com um vertice sobrando no meio de cada aresta.
    com_sobra = Polygon(
        [(0, 0), (5, 0), (10, 0), (10, 5), (10, 10), (5, 10), (0, 10), (0, 5)]
    )
    limpo = drop_collinear_vertices(com_sobra)
    assert len(limpo.exterior.coords) - 1 == 4
    assert limpo.area == pytest.approx(com_sobra.area)


def test_vertices_repetidos_sao_removidos():
    repetido = Polygon([(0, 0), (10, 0), (10, 0), (10, 10), (0, 10)])
    limpo = drop_collinear_vertices(repetido)
    assert len(limpo.exterior.coords) - 1 == 4


def test_furos_tambem_sao_limpos():
    com_furo = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        [[(2, 2), (5, 2), (8, 2), (8, 8), (2, 8)]],
    )
    limpo = drop_collinear_vertices(com_furo)
    assert len(limpo.interiors[0].coords) - 1 == 4
    assert limpo.area == pytest.approx(com_furo.area)


def test_perfil_sai_sem_colineares(params):
    """O perfil entregue a extrusao nao pode ter vertice no meio de reta."""
    import math

    profile = build_profile("ALICE", params)
    ring = list(profile.geometry.exterior.coords)[:-1]
    for i in range(len(ring)):
        antes, meio, depois = ring[i - 1], ring[i], ring[(i + 1) % len(ring)]
        base = math.dist(antes, depois)
        if base == 0:
            continue
        altura = abs(
            (depois[0] - antes[0]) * (meio[1] - antes[1])
            - (depois[1] - antes[1]) * (meio[0] - antes[0])
        ) / base
        assert altura > 1e-6, f"vertice colinear em {meio}"


def test_perfil_normalizado_no_primeiro_quadrante(params):
    profile = build_profile("Bruno", params)
    x_min, y_min, _, _ = profile.geometry.bounds
    assert x_min == pytest.approx(0.0)
    assert y_min == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Aperto das letras (silhueta sem borda)
# ----------------------------------------------------------------------


def _partes(geometry) -> int:
    return 1 if geometry.geom_type == "Polygon" else len(geometry.geoms)


def test_borda_vem_desligada_por_padrao(params):
    assert params.enable_border is False
    assert params.should_tighten is True


def test_com_borda_o_aperto_desliga_sozinho(make_params):
    assert make_params(enable_border=True).should_tighten is False


def test_flag_explicita_vence_o_automatico(make_params):
    assert make_params(enable_border=True, tighten_letters=True).should_tighten
    assert not make_params(enable_border=False, tighten_letters=False).should_tighten


def test_aperto_encosta_as_letras_e_encurta_o_nome(font_path, make_params):
    outline = outline_text(font_path, "ALICE")
    solto, _ = layout_letters(outline, make_params(tighten_letters=False), 20.0)
    junto, _ = layout_letters(outline, make_params(tighten_letters=True), 20.0)

    assert _partes(solto) > 1, "no espacamento natural as letras ficam soltas"
    assert _partes(junto) == 1, "apertadas viram uma peca so"
    largura = lambda g: g.bounds[2] - g.bounds[0]
    assert largura(junto) < largura(solto)


def test_aperto_preserva_a_altura(font_path, make_params):
    outline = outline_text(font_path, "ALICE")
    junto, _ = layout_letters(outline, make_params(tighten_letters=True), 20.0)
    assert junto.bounds[3] - junto.bounds[1] == pytest.approx(20.0)


def test_espaco_entre_palavras_nao_e_apertado(font_path, make_params):
    """A espinha e que segura as duas palavras; o vao continua la."""
    outline = outline_text(font_path, "Ana Ana")
    junto, _ = layout_letters(outline, make_params(tighten_letters=True), 20.0)
    assert _partes(junto) == 2


def test_letter_spacing_afasta_mesmo_com_aperto(font_path, make_params):
    outline = outline_text(font_path, "ALICE")
    colado, _ = layout_letters(outline, make_params(tighten_letters=True), 20.0)
    afastado, _ = layout_letters(
        outline, make_params(tighten_letters=True, letter_spacing=2.0), 20.0
    )
    assert afastado.bounds[2] - afastado.bounds[0] > colado.bounds[2] - colado.bounds[0]


def test_contact_shift_para_no_encosto():
    esquerda = box(0, 0, 10, 10)
    direita = box(15, 0, 25, 10)  # 5 mm de vao
    assert contact_shift(esquerda, direita, overlap=0.0) == pytest.approx(5.0, abs=1e-3)
    assert contact_shift(esquerda, direita, overlap=0.4) == pytest.approx(5.4, abs=1e-3)


def test_contact_shift_ignora_quem_ja_encosta():
    esquerda = box(0, 0, 10, 10)
    encostado = box(9, 0, 19, 10)
    assert contact_shift(esquerda, encostado, overlap=0.4) == 0.0


def test_contact_shift_respeita_o_limite_de_encaixe():
    """Formas que nunca se encontram nao deslizam alem do encaixe maximo."""
    baixo = box(0, 0, 10, 2)
    alto = box(15, 8, 25, 10)  # em alturas diferentes, nunca se tocam
    deslocamento = contact_shift(baixo, alto, overlap=0.4)
    assert deslocamento == pytest.approx(5.0 + 0.6 * 10.0)


def test_sem_borda_o_perfil_sai_conexo(params):
    profile = build_profile("Matheus", params)
    assert profile.geometry.geom_type == "Polygon"


def test_pinca_detectada_independe_de_onde_a_peca_esta():
    """Detector por grade falhava quando o par caia em celulas vizinhas."""
    quase = PINCH_TOLERANCE / 100
    pinchado = Polygon(
        [(0, 0), (2, 0), (2, 2), (4, 2), (4, 4), (2, 4), (2 + quase, 2), (0, 2)]
    )
    assert has_pinch(pinchado)
    for deslocamento in (0.0, 1e-7, 0.3333333, 13.7):
        assert has_pinch(translate(pinchado, xoff=deslocamento)), deslocamento


def test_letras_tangentes_nao_quebram_a_extrusao(make_params):
    """--letter-overlap 0 encosta as letras sem sobrepor: caso degenerado."""
    import trimesh

    params = make_params(letter_overlap=0.0, max_length=1e6)
    profile = build_profile("MM", params)
    assert not has_pinch(profile.geometry)
    malha = trimesh.creation.extrude_polygon(profile.geometry, height=params.section)
    assert malha.is_watertight


# ----------------------------------------------------------------------
# Espinha opcional (reforco)
# ----------------------------------------------------------------------


def test_espinha_vem_ligada_por_padrao(params):
    assert params.enable_spine is True
    assert build_profile("ALICE", params).spine is not None


def test_sem_espinha_o_perfil_e_so_as_letras(make_params):
    params = make_params(enable_spine=False)
    profile = build_profile("ALICE", params)
    assert profile.spine is None
    assert profile.geometry.geom_type == "Polygon", "as letras encostadas seguram a peca"
    # Sem a barra central sobra menos material na faixa do canal.
    com = build_profile("ALICE", make_params(enable_spine=True))
    assert profile.geometry.area < com.geometry.area


def test_sem_espinha_o_canal_percorre_a_peca_toda(make_params):
    profile = build_profile("ALICE", make_params(enable_spine=False))
    x_min, _, x_max, _ = profile.geometry.bounds
    assert profile.hole_x_start == pytest.approx(x_min)
    assert profile.hole_x_end == pytest.approx(x_max)


def test_tampa_existe_mesmo_sem_espinha(make_params):
    """A ponta cega e uma peca propria; sem ela nao ha o que fechar o canal."""
    params = make_params(enable_spine=False, closed_end="right", cap_thickness=2.0)
    profile = build_profile("ALICE", params)
    assert profile.hole_x_end < profile.geometry.bounds[2] - 1e-9
    assert profile.geometry.bounds[2] - profile.hole_x_end == pytest.approx(2.0)


def test_sem_espinha_e_sem_encosto_as_barras_seguram(make_params):
    params = make_params(enable_spine=False, tighten_letters=False)
    profile = build_profile("ALICE", params)
    assert profile.geometry.geom_type == "Polygon"
    assert any("barra" in w for w in profile.warnings)


def test_sem_nada_que_conecte_e_erro(make_params):
    params = make_params(enable_spine=False, tighten_letters=False, enable_struts=False)
    with pytest.raises(ProfileError, match="desconexos"):
        build_profile("ALICE", params)


def test_relevo_so_existe_quando_ha_base(make_params):
    sem_base = make_params(enable_spine=False, enable_border=False, relief=2.0)
    assert sem_base.has_base is False
    assert sem_base.effective_relief == 0.0
    for base in (
        make_params(enable_spine=True, relief=2.0),
        make_params(enable_spine=False, enable_border=True, relief=2.0),
    ):
        assert base.has_base is True
        assert base.effective_relief == pytest.approx(2.0)
