"""Montagem do perfil 2D da ponteira (secao no plano XY, em milimetros).

Eixos usados em todo o projeto:

* **X** direcao da escrita e do canal do lapis;
* **Y** altura das letras;
* **Z** profundidade da extrusao.

A estrategia e a "espinha interna": uma barra retangular de altura exatamente
igual a secao exigida pelo furo atravessa o nome inteiro por dentro das letras
(por padrao rente a base delas) e e unida a elas. Isso resolve de uma vez os
dois problemas do README -- a peca nunca sai em pedacos soltos (letras
separadas, pingo do "i") e a parede minima ao redor do canal passa a ser
garantida por construcao, em vez de depender da forma da fonte.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.affinity import scale as shapely_scale
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from .config import TipParams
from .fonts import outline_text
from .geom import polygon_parts


class ProfileError(ValueError):
    """Perfil 2D impossivel de gerar com os parametros dados."""


@dataclass
class Profile:
    """Perfil 2D pronto para extrusao, normalizado com bbox comecando em (0, 0)."""

    geometry: Polygon
    text_geometry: BaseGeometry
    spine: Polygon | None
    scale: float
    text_height: float
    hole_axis_y: float
    hole_x_start: float
    hole_x_end: float
    font_name: str
    warnings: list[str] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.geometry.bounds[2] - self.geometry.bounds[0]

    @property
    def height(self) -> float:
        return self.geometry.bounds[3] - self.geometry.bounds[1]

    @property
    def hole_length(self) -> float:
        return self.hole_x_end - self.hole_x_start


def _as_polygon(geometry: BaseGeometry) -> Polygon:
    """Garante que o perfil e uma peca unica e conexa."""
    if geometry.is_empty:
        raise ProfileError("perfil vazio")
    if geometry.geom_type == "Polygon":
        return geometry
    parts = polygon_parts(geometry)
    if len(parts) == 1:
        return parts[0]
    raise ProfileError(
        f"o perfil ficou em {len(parts)} pedacos desconexos; "
        "ligue as barras de suporte (--struts) ou a espinha (--spine), "
        "aumente --letter-overlap ou --border-width, "
        "ou reduza --letter-spacing"
    )


def connect_components(
    geometry: BaseGeometry, strut_width: float, max_struts: int = 32
) -> tuple[BaseGeometry, int]:
    """Liga pedacos soltos ao corpo principal com barras de suporte.

    E o caso que o README preve: o pingo do "i" e do "j", acentos e letras que
    a borda nao alcanca ficam flutuando. Cada pedaco solto e ligado ao corpo
    principal pelo menor segmento possivel (para um pingo isso da uma haste
    vertical, que e o que um desenhista faria), engrossado em ``strut_width``.
    """
    struts = 0
    for _ in range(max_struts):
        parts = polygon_parts(geometry)
        if len(parts) <= 1:
            break
        parts.sort(key=lambda g: g.area, reverse=True)
        main, rest = parts[0], unary_union(parts[1:])
        point_a, point_b = nearest_points(main, rest)
        span = point_a.distance(point_b)
        if span <= 0:
            # Pedacos que so se encostam num ponto: a uniao nao os funde e nao
            # ha vao para atravessar com barra. Um fechamento minimo resolve,
            # e nao conta como barra porque nao muda a silhueta.
            geometry = _close(geometry, 0.02)
            continue
        # A barra entra um pouco nas duas pecas: encostar tangente criaria um
        # ponto de pinca, que o triangulador da extrusao nao consegue fechar.
        bite = strut_width / 2.0
        dx = (point_b.x - point_a.x) / span
        dy = (point_b.y - point_a.y) / span
        strut = LineString(
            [
                (point_a.x - dx * bite, point_a.y - dy * bite),
                (point_b.x + dx * bite, point_b.y + dy * bite),
            ]
        ).buffer(strut_width / 2.0, cap_style=1, quad_segs=8)
        geometry = unary_union([geometry, strut])
        struts += 1
    return geometry, struts


def _point_to_segment(point, start, end) -> float:
    """Distancia perpendicular de ``point`` ao segmento ``start``-``end``."""
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0.0:
        return math.hypot(px - ax, py - ay)
    return abs(dx * (py - ay) - dy * (px - ax)) / length


def _clean_ring(coords, tolerance: float) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for x, y in list(coords)[:-1]:  # o ultimo ponto repete o primeiro
        if not points or math.hypot(x - points[-1][0], y - points[-1][1]) > tolerance:
            points.append((x, y))
    if len(points) > 1 and math.hypot(
        points[0][0] - points[-1][0], points[0][1] - points[-1][1]
    ) <= tolerance:
        points.pop()

    changed = True
    while changed and len(points) > 3:
        changed = False
        index = 0
        while index < len(points) and len(points) > 3:
            before = points[index - 1]
            middle = points[index]
            after = points[(index + 1) % len(points)]
            if _point_to_segment(middle, before, after) <= tolerance:
                del points[index]
                changed = True
            else:
                index += 1
    return points


def drop_collinear_vertices(geometry: BaseGeometry, tolerance: float = 1e-6):
    """Tira vertices colineares e repetidos de todos os aneis.

    A uniao da borda com a espinha deixa pontos no meio de arestas retas. O
    triangulador da extrusao descarta os triangulos de area nula que eles geram,
    a malha fica com uma aresta solta e nunca fecha. ``simplify(0)`` resolve a
    maioria dos casos, mas preserva topologia e ancora alguns vertices -- entao
    a limpeza aqui e explicita.
    """
    cleaned = []
    for part in polygon_parts(geometry):
        exterior = _clean_ring(part.exterior.coords, tolerance)
        if len(exterior) < 3:
            continue
        interiors = [
            ring
            for ring in (_clean_ring(hole.coords, tolerance) for hole in part.interiors)
            if len(ring) >= 3
        ]
        cleaned.append(Polygon(exterior, interiors))
    return unary_union(cleaned) if cleaned else geometry


# Vertices dentro dessa distancia sao o mesmo ponto para efeito de pinca.
PINCH_TOLERANCE = 1e-6

# Quanto de si mesmo um glifo pode avancar sobre o anterior ao ser apertado.
# Segura o "AV", que so encosta depois de encaixar bastante, sem deixar uma
# letra engolir a outra.
MAX_INTERLOCK = 0.6


def contact_shift(
    cluster: BaseGeometry, glyph: BaseGeometry, overlap: float
) -> float:
    """Quanto deslizar o glifo para a esquerda ate ele encostar no que ja foi posto.

    Nao ha formula fechada para "distancia horizontal ate o contato" entre dois
    poligonos, entao vale bissecao: o glifo ou toca o vizinho a partir de certo
    deslocamento, ou nao toca nunca. O ``overlap`` empurra um pouco alem do
    contato, porque encostar exatamente cria um ponto de pinca -- o mesmo
    problema que as barras de suporte tiveram.
    """
    x_min, _, x_max, _ = glyph.bounds
    gap = x_min - cluster.bounds[2]
    limit = max(0.0, gap) + MAX_INTERLOCK * (x_max - x_min)
    if limit <= 0 or cluster.intersects(glyph):
        return 0.0
    if not translate(glyph, xoff=-limit).intersects(cluster):
        return limit  # nao se encontram nem no limite: fecha o que da

    low, high = 0.0, limit
    for _ in range(24):
        middle = (low + high) / 2.0
        if translate(glyph, xoff=-middle).intersects(cluster):
            high = middle
        else:
            low = middle
    return low + overlap


def layout_letters(outline, params: TipParams, text_height: float):
    """Posiciona as letras em milimetros e devolve (uniao, escala).

    Espacos nao sao apertados: o vao entre palavras e preservado e quem segura
    as duas metades e a espinha.
    """
    _, y_min, _, y_max = outline.geometry.bounds
    factor = text_height / (y_max - y_min)

    placed: list[BaseGeometry] = []
    cluster: BaseGeometry | None = None
    shift = 0.0
    after_gap = True
    for glyph in outline.glyphs:
        if glyph.geometry.is_empty:
            after_gap = True
            continue
        piece = shapely_scale(glyph.geometry, xfact=factor, yfact=factor, origin=(0, 0))
        piece = translate(piece, xoff=-shift)
        if cluster is not None and not after_gap and params.should_tighten:
            extra = contact_shift(cluster, piece, params.letter_overlap)
            piece = translate(piece, xoff=-extra)
            shift += extra
        if cluster is not None and params.letter_spacing:
            # Depois do aperto, senao o encosto engoliria o afastamento pedido.
            piece = translate(piece, xoff=params.letter_spacing)
            shift -= params.letter_spacing
        placed.append(piece)
        cluster = piece if cluster is None else unary_union([cluster, piece])
        after_gap = False

    letters = unary_union(placed)
    letters = letters.simplify(params.curve_tolerance, preserve_topology=True)
    return letters.buffer(0), factor


def _close(geometry: BaseGeometry, epsilon: float) -> BaseGeometry:
    """Fechamento morfologico: dilata e erode pela mesma quantidade."""
    return geometry.buffer(epsilon, join_style=1, quad_segs=8).buffer(
        -epsilon, join_style=1, quad_segs=8
    )


def _ring_has_coincident(coords, tolerance: float) -> bool:
    """Ha dois vertices do anel a menos de ``tolerance`` um do outro?

    Varredura por x ordenado, e nao arredondamento numa grade: dois pontos a
    fracoes de nanometro podem cair em celulas vizinhas da grade e passar
    despercebidos, e o resultado ainda muda se a peca inteira for transladada.
    """
    points = sorted(coords)
    for index, (x, y) in enumerate(points):
        for other_x, other_y in points[index + 1 :]:
            if other_x - x > tolerance:
                break
            if abs(other_y - y) <= tolerance:
                return True
    return False


def has_pinch(polygon: Polygon, tolerance: float = PINCH_TOLERANCE) -> bool:
    """Detecta vertices coincidentes: o contorno encosta em si mesmo num ponto.

    Quando duas letras se encostam sem sobreposicao, a uniao devolve dois
    vertices separados por fracoes de nanometro em vez de um so. Sao distintos
    para o shapely, mas formam a mesma lasca de area zero que deixa a extrusao
    aberta -- e a malha nunca fecha.
    """
    return any(
        _ring_has_coincident(list(ring.coords)[:-1], tolerance)
        for ring in (polygon.exterior, *polygon.interiors)
    )


def heal_pinches(geometry: BaseGeometry) -> BaseGeometry:
    """Abre pontos de pinca com um fechamento morfologico (dilata e erode).

    Uniao de letra com borda ou com barra de suporte as vezes deixa dois lobos
    encostados num unico ponto. O poligono continua valido para o shapely, mas
    a extrusao sai com arestas soltas -- e a malha nunca fecha. Dilatar e erodir
    por uma fracao de milimetro transforma o contato num pescoco de verdade.
    """
    for epsilon in (0.005, 0.02, 0.05):
        if not any(has_pinch(part) for part in polygon_parts(geometry)):
            return geometry
        geometry = _close(geometry, epsilon)
    return geometry


def finalize(geometry: BaseGeometry) -> BaseGeometry:
    """Deixa a geometria pronta para extrudar: sem pinca e sem colinear.

    As duas limpezas se afetam -- tirar um vertice colinear pode encostar dois
    vizinhos, e abrir uma pinca cria vertices novos --, entao vale repetir ate
    parar de mudar.
    """
    for _ in range(3):
        geometry = drop_collinear_vertices(heal_pinches(geometry))
        if not any(has_pinch(part) for part in polygon_parts(geometry)):
            break
    return geometry


def _thin_feature_warning(geometry: Polygon, min_feature: float) -> str | None:
    """Detecta regioes mais finas que ``min_feature`` por erosao/dilatacao."""
    if min_feature <= 0:
        return None
    half = min_feature / 2.0
    eroded = geometry.buffer(-half, join_style=2).buffer(half, join_style=2)
    if eroded.is_empty:
        return f"toda a peca e mais fina que --min-feature ({min_feature:g} mm)"
    lost = geometry.difference(eroded)
    if lost.is_empty:
        return None
    limit = max(0.5, 0.005 * geometry.area)
    if lost.area > limit:
        pct = 100.0 * lost.area / geometry.area
        return (
            f"{pct:.1f}% da area tem detalhes mais finos que "
            f"{min_feature:g} mm (--min-feature); considere uma fonte mais pesada, "
            "--text-height maior ou --border-width maior"
        )
    return None


def _fixed_extra_width(text: str, params: TipParams) -> float:
    """Largura que nao acompanha a escala das letras (borda e tampa).

    O espacamento entre letras nao entra: quando ha aperto ele ja aparece na
    largura medida, e sem aperto a estimativa linear so serve de ponto de
    partida para as medidas que vem depois.
    """
    extra = 2 * params.border_width if params.enable_border else 0.0
    if params.closed_end != "none":
        extra += params.cap_thickness
    return extra


def choose_text_height(text: str, params: TipParams, outline) -> tuple[float, list[str]]:
    """Decide a altura das letras.

    Com ``--text-height`` explicito so aplicamos o piso estrutural (a secao do
    furo). Sem ele, procuramos a maior altura que ainda cabe em ``--max-length``,
    limitada entre a altura legivel e ``--max-text-height``.

    A largura seria linear na altura se as letras nao fossem apertadas -- mas o
    aperto encurta o nome numa proporcao que so se sabe medindo. Entao partimos
    da estimativa linear e corrigimos com poucas medidas reais, aproveitando que
    a largura continua praticamente proporcional a altura.
    """
    warnings: list[str] = []
    if params.text_height is not None:
        height = params.text_height
        if height < params.section:
            height = params.section
            warnings.append(
                f"--text-height {params.text_height:g} mm e menor que a secao exigida "
                f"pelo furo ({params.section:g} mm); as letras foram ampliadas"
            )
        elif height < params.readable_text_height:
            warnings.append(
                f"--text-height {height:g} mm deixa menos de "
                f"{params.min_letter_exposure:g} mm de letra acima da espinha; "
                "o nome pode ficar dificil de ler"
            )
        return height, warnings

    # O piso estrutural (a secao do furo) nunca cede: abaixo dele a parede
    # deixa de existir. Ja o piso de legibilidade cede para um --max-text-height
    # explicito, porque esse o usuario pediu -- mas avisando.
    ceiling = max(params.max_text_height, params.section)
    floor_height = min(params.readable_text_height, ceiling)
    if floor_height < params.readable_text_height:
        warnings.append(
            f"--max-text-height {params.max_text_height:g} mm fica abaixo da altura "
            f"legivel ({params.readable_text_height:g} mm); sobra pouca letra acima "
            "da espinha"
        )
    extra = _fixed_extra_width(text, params)
    x_min, y_min, x_max, y_max = outline.geometry.bounds
    ratio = (x_max - x_min) / (y_max - y_min)
    room = params.max_length - extra

    # Estimativa sem aperto: como apertar so encurta, ela nunca fica curta demais.
    height = room / ratio if ratio > 0 and room > 0 else floor_height
    height = min(ceiling, max(floor_height, height))

    best = height
    for _ in range(4):
        letters, _ = layout_letters(outline, params, height)
        width = letters.bounds[2] - letters.bounds[0] + extra
        if width <= params.max_length:
            best = height
            folga = params.max_length - width
            if height >= ceiling - 1e-9 or folga < 0.2:
                break
            height = min(ceiling, height * params.max_length / width)
            if height - best < 1e-6:
                break
        else:
            if height <= floor_height + 1e-9:
                return floor_height, warnings
            height = max(floor_height, height * params.max_length / width)
    return best, warnings


def build_profile(text: str, params: TipParams) -> Profile:
    """Constroi o perfil 2D final do nome, ja em milimetros."""
    outline = outline_text(params.font_path, text)
    raw = outline.geometry
    if raw.is_empty:
        raise ProfileError(f"o texto {text!r} nao produziu nenhum contorno visivel")

    # 1. Altura das letras: nunca menor que a secao exigida pelo furo.
    _, ymin, _, ymax = raw.bounds
    if ymax - ymin <= 0:
        raise ProfileError(f"o texto {text!r} nao tem altura")
    text_height, warnings = choose_text_height(text, params, outline)

    # 2. Letras posicionadas em mm, apertadas ate se encostarem quando for o caso.
    text_geometry, factor = layout_letters(outline, params, text_height)

    tx_min, ty_min, tx_max, ty_max = text_geometry.bounds

    # 3. Borda de silhueta em volta das letras.
    body = text_geometry
    if params.enable_border and params.border_width > 0:
        border = text_geometry.buffer(params.border_width, join_style=1, quad_segs=16)
        body = unary_union([text_geometry, border])

    bx_min, _, bx_max, _ = body.bounds

    # 4. Eixo do canal e as pecas que o cercam.
    half_section = params.section / 2.0
    if params.hole_align == "bottom":
        axis_y = ty_min + half_section
    elif params.hole_align == "top":
        axis_y = ty_max - half_section
    else:
        axis_y = (ty_min + ty_max) / 2.0
    axis_y += params.hole_offset_y

    parts: list[BaseGeometry] = [body]
    spine = None
    if params.enable_spine:
        # Reforco: barra de altura igual a secao, na largura toda da peca. Com
        # ela a parede minima e garantida por construcao; sem ela quem segura o
        # canal sao as proprias letras, e a parede passa a ser so medida.
        spine = box(bx_min, axis_y - half_section, bx_max, axis_y + half_section)
        parts.append(spine)

    # A tampa da ponta cega e independente da espinha: sem ela nao ha o que
    # fechar o canal.
    if params.closed_end == "left":
        parts.append(
            box(
                bx_min - params.cap_thickness,
                axis_y - half_section,
                bx_min,
                axis_y + half_section,
            )
        )
    elif params.closed_end == "right":
        parts.append(
            box(
                bx_max,
                axis_y - half_section,
                bx_max + params.cap_thickness,
                axis_y + half_section,
            )
        )

    merged = unary_union(parts).buffer(0)
    if params.enable_struts:
        merged, struts = connect_components(merged, params.strut_width)
        if struts:
            warnings.append(
                f"{struts} barra(s) de suporte adicionada(s) para prender pedacos "
                "soltos (pingo de i/j, acentos); use --strut-width para engrossar"
            )
    profile = _as_polygon(finalize(merged))

    # 5. Normaliza para o primeiro quadrante.
    px_min, py_min, _, _ = profile.bounds
    profile = translate(profile, xoff=-px_min, yoff=-py_min)
    if spine is not None:
        spine = translate(spine, xoff=-px_min, yoff=-py_min)
    text_geometry = translate(text_geometry, xoff=-px_min, yoff=-py_min)
    axis_y -= py_min

    if has_pinch(profile):  # a translacao pode ter reaproximado vertices
        profile = _as_polygon(finalize(profile))

    hole_x_start, _, hole_x_end, _ = profile.bounds
    if params.closed_end == "left":
        hole_x_start += params.cap_thickness
    elif params.closed_end == "right":
        hole_x_end -= params.cap_thickness

    thin = _thin_feature_warning(profile, params.min_feature)
    if thin:
        warnings.append(thin)

    return Profile(
        geometry=profile,
        text_geometry=text_geometry,
        spine=spine,
        scale=factor,
        text_height=text_height,
        hole_axis_y=axis_y,
        hole_x_start=hole_x_start,
        hole_x_end=hole_x_end,
        font_name=outline.font_name,
        warnings=warnings,
    )
