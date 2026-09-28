"""Extracao de contornos de fontes .ttf/.otf para poligonos 2D do shapely.

Usa fontTools (puro Python, le TrueType e OpenType/CFF pelo mesmo glyphSet),
achatando as curvas de Bezier em polilinhas e resolvendo os furos das letras
(contra-formas de "O", "A", "e") por aninhamento, e nao por sentido de rotacao
do contorno -- TrueType costuma usar horario e CFF anti-horario, entao contar
quantos contornos envolvem o outro e a unica regra confiavel para as duas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geom import polygon_parts

# Achatamento feito em unidades de fonte; a geometria e simplificada depois,
# ja em milimetros, com a tolerancia real pedida pelo usuario.
_RELATIVE_FLATNESS = 1.0 / 1000.0
_MAX_SEGMENTS = 128


class FontError(ValueError):
    """Fonte ilegivel ou sem os glifos necessarios."""


class _FlatteningPen(BasePen):
    """Pen que acumula contornos fechados como listas de pontos."""

    def __init__(self, glyph_set, flatness: float):
        super().__init__(glyph_set)
        self.flatness = flatness
        self.contours: list[list[tuple[float, float]]] = []
        self._current: list[tuple[float, float]] = []

    # -- protocolo do BasePen ------------------------------------------
    def _moveTo(self, pt):
        self._flush()
        self._current = [pt]

    def _lineTo(self, pt):
        self._current.append(pt)

    def _curveToOne(self, pt1, pt2, pt3):
        p0 = self._current[-1]
        n = _cubic_segments(p0, pt1, pt2, pt3, self.flatness)
        for i in range(1, n + 1):
            self._current.append(_cubic_point(p0, pt1, pt2, pt3, i / n))

    def _qCurveToOne(self, pt1, pt2):
        p0 = self._current[-1]
        n = _quadratic_segments(p0, pt1, pt2, self.flatness)
        for i in range(1, n + 1):
            self._current.append(_quadratic_point(p0, pt1, pt2, i / n))

    def _closePath(self):
        self._flush()

    def _endPath(self):
        self._flush()

    def _flush(self):
        if len(self._current) >= 3:
            self.contours.append(self._current)
        self._current = []

    def finish(self) -> list[list[tuple[float, float]]]:
        self._flush()
        return self.contours


def _wang_segments(second_diff: float, degree: int, flatness: float) -> int:
    """Formula de Wang: quantos segmentos mantem o erro abaixo de ``flatness``."""
    if second_diff <= 0.0:
        return 1
    factor = degree * (degree - 1) / 8.0
    n = math.ceil(math.sqrt(factor * second_diff / flatness))
    return max(1, min(_MAX_SEGMENTS, n))


def _norm(ax: float, ay: float) -> float:
    return math.hypot(ax, ay)


def _cubic_segments(p0, p1, p2, p3, flatness: float) -> int:
    d1 = _norm(p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1])
    d2 = _norm(p1[0] - 2 * p2[0] + p3[0], p1[1] - 2 * p2[1] + p3[1])
    return _wang_segments(max(d1, d2), 3, flatness)


def _quadratic_segments(p0, p1, p2, flatness: float) -> int:
    d = _norm(p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1])
    return _wang_segments(d, 2, flatness)


def _cubic_point(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    )


def _quadratic_point(p0, p1, p2, t: float) -> tuple[float, float]:
    u = 1.0 - t
    a, b, c = u * u, 2 * u * t, t * t
    return (a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1])


def _repair(polygon: Polygon) -> list[Polygon]:
    """Devolve as partes validas de um contorno, mesmo se ele se auto-intersecta.

    Fontes CFF costumam desenhar letras com tracos sobrepostos, contando com o
    preenchimento nonzero do rasterizador. Para o shapely isso e um poligono
    invalido, e qualquer operacao seguinte explode; ``buffer(0)`` resolve as
    interseccoes e devolve a mesma area em pecas validas.
    """
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon_parts(polygon)


def contours_to_polygons(contours) -> list[Polygon]:
    """Monta poligonos a partir de contornos brutos, resolvendo furos.

    Vale a regra par-impar: um contorno envolvido por um numero impar de outros
    e furo, os demais sao massa. Em vez de casar cada furo com o seu contorno
    externo, as camadas de aninhamento sao unidas e subtraidas alternadamente --
    assim ilhas dentro de furos (o miolo do "%" ou do "@") saem certas sozinhas.

    O teste de aninhamento usa um vertice do contorno, e nao um ponto interno:
    contornos de fonte nao se cruzam, entao um vertice de um nunca cai sobre o
    outro -- ja um ponto interno do contorno externo do "A" cairia dentro da
    contra-forma e faria o proprio contorno externo ser lido como furo.
    """
    rings: list[Polygon] = []
    for points in contours:
        for part in _repair(Polygon(points)):
            rings.append(Polygon(part.exterior))
    if not rings:
        return []

    probes = [Point(ring.exterior.coords[0]) for ring in rings]
    layers: dict[int, list[Polygon]] = {}
    for index, ring in enumerate(rings):
        depth = sum(
            1
            for other_index, other in enumerate(rings)
            if other_index != index and other.contains(probes[index])
        )
        layers.setdefault(depth, []).append(ring)

    result: BaseGeometry = Polygon()
    for depth in sorted(layers):
        layer = unary_union(layers[depth])
        result = result.union(layer) if depth % 2 == 0 else result.difference(layer)
    return polygon_parts(result)


@dataclass
class GlyphRun:
    """Um glifo posicionado, em unidades de fonte."""

    char: str
    geometry: BaseGeometry  # vazia para espaco e afins
    origin_x: float
    advance: float


@dataclass
class TextOutline:
    """Resultado da extracao de um texto inteiro, em unidades de fonte."""

    glyphs: list[GlyphRun]
    units_per_em: int
    font_name: str

    @property
    def geometry(self) -> BaseGeometry:
        return unary_union([g.geometry for g in self.glyphs if not g.geometry.is_empty])


def load_font(font_path: Path) -> TTFont:
    try:
        font = TTFont(str(font_path), fontNumber=0, lazy=True)
    except Exception as exc:  # noqa: BLE001 - fontTools levanta varios tipos
        raise FontError(f"nao foi possivel ler a fonte {font_path}: {exc}") from exc
    if "glyf" not in font and "CFF " not in font and "CFF2" not in font:
        raise FontError(f"fonte sem contornos vetoriais suportados: {font_path}")
    return font


def _font_name(font: TTFont) -> str:
    try:
        record = font["name"].getDebugName(4) or font["name"].getDebugName(1)
        return record or "?"
    except Exception:  # noqa: BLE001
        return "?"


def _kerning_table(font: TTFont) -> dict[tuple[str, str], int]:
    """Kerning do formato legado ``kern``; GPOS nao e interpretado."""
    try:
        kern = font["kern"]
    except KeyError:
        return {}
    table: dict[tuple[str, str], int] = {}
    for subtable in getattr(kern, "kernTables", []):
        table.update(getattr(subtable, "kernTable", {}))
    return table


def outline_text(font_path: Path, text: str) -> TextOutline:
    """Extrai o texto como glifos posicionados, em unidades de fonte."""
    if not text.strip():
        raise FontError("texto vazio")

    font = load_font(font_path)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    kerning = _kerning_table(font)
    flatness = upem * _RELATIVE_FLATNESS

    missing = sorted({ch for ch in text if ord(ch) not in cmap})
    if missing:
        raise FontError(
            "a fonte nao possui glifo para: "
            + ", ".join(f"{ch!r} (U+{ord(ch):04X})" for ch in missing)
        )

    glyphs: list[GlyphRun] = []
    pen_x = 0.0
    previous: str | None = None
    for char in text:
        name = cmap[ord(char)]
        if previous is not None:
            pen_x += kerning.get((previous, name), 0)
        pen = _FlatteningPen(glyph_set, flatness)
        glyph_set[name].draw(pen)
        polygons = contours_to_polygons(pen.finish())
        geometry = unary_union(polygons) if polygons else Polygon()
        if not geometry.is_empty:
            from shapely.affinity import translate

            geometry = translate(geometry, xoff=pen_x)
        advance = float(glyph_set[name].width)
        glyphs.append(GlyphRun(char, geometry, pen_x, advance))
        pen_x += advance
        previous = name

    return TextOutline(glyphs=glyphs, units_per_em=upem, font_name=_font_name(font))
