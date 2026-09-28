"""Extracao de contornos da fonte."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from pencil_tip_gen.fonts import FontError, contours_to_polygons, outline_text


def _parts(geometry):
    if geometry.is_empty:
        return []
    return list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]


def test_letra_com_contraforma_vira_poligono_com_furo(font_path):
    outline = outline_text(font_path, "O")
    parts = _parts(outline.glyphs[0].geometry)
    assert len(parts) == 1
    assert len(parts[0].interiors) == 1


def test_letra_i_tem_duas_partes_soltas(font_path):
    outline = outline_text(font_path, "i")
    assert len(_parts(outline.glyphs[0].geometry)) == 2


def test_espaco_avanca_sem_desenhar(font_path):
    outline = outline_text(font_path, "a b")
    assert outline.glyphs[1].geometry.is_empty
    assert outline.glyphs[1].advance > 0
    assert outline.glyphs[2].origin_x > outline.glyphs[1].origin_x


def test_glifo_ausente_lista_os_caracteres(font_path):
    with pytest.raises(FontError, match="U\\+65E5"):
        outline_text(font_path, "日")


def test_texto_vazio_e_recusado(font_path):
    with pytest.raises(FontError):
        outline_text(font_path, "   ")


def test_uniao_do_texto_tem_area(font_path):
    outline = outline_text(font_path, "ALICE")
    assert outline.geometry.area > 0
    assert outline.geometry.is_valid
    assert outline.units_per_em > 0


def test_aninhamento_resolve_ilha_dentro_do_furo():
    """Anel dentro de furo dentro de contorno: tres niveis, dois poligonos."""
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(2, 2), (8, 2), (8, 8), (2, 8)]
    island = [(4, 4), (6, 4), (6, 6), (4, 6)]
    polygons = contours_to_polygons([outer, hole, island])
    assert len(polygons) == 2
    big = max(polygons, key=lambda g: g.area)
    small = min(polygons, key=lambda g: g.area)
    assert len(big.interiors) == 1
    assert small.equals(Polygon(island))
