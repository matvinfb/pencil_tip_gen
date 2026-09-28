"""Parametros da ponteira e valores derivados."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

HOLE_SHAPES = {
    "circle": 0,  # 0 = suave, usa --hole-segments
    "triangle": 3,
    "square": 4,
    "hexagon": 6,
    "octagon": 8,
}

CLOSED_END_CHOICES = ("none", "left", "right")
HOLE_ALIGN_CHOICES = ("bottom", "center", "top")
HOLE_SIZE_MODES = ("circum", "inscribed")
OUTPUT_FORMATS = ("stl", "obj", "3mf")


class ConfigError(ValueError):
    """Parametro invalido informado pelo usuario."""


@dataclass
class TipParams:
    """Todos os parametros geometricos da ponteira, em milimetros."""

    font_path: Path

    # Encaixe do lapis
    hole_size: float = 7.5
    hole_shape: str = "circle"
    hole_size_mode: str = "circum"
    tolerance: float = 0.2
    hole_rotation: float = 0.0
    hole_segments: int = 64
    hole_align: str = "bottom"
    hole_offset_y: float = 0.0
    chamfer: float = 1.0
    closed_end: str = "none"
    cap_thickness: float = 2.0

    # Estrutura
    min_wall_thickness: float = 3.0
    max_length: float = 87.5
    enable_spine: bool = True
    enable_border: bool = False
    border_width: float = 1.0
    tighten_letters: bool | None = None
    letter_overlap: float = 0.4
    enable_struts: bool = True
    strut_width: float = 1.2

    # Texto
    relief: float = 2.0
    text_height: float | None = None
    max_text_height: float = 30.0
    min_letter_exposure: float = 6.0
    depth: float | None = None
    letter_spacing: float = 0.0
    curve_tolerance: float = 0.05
    min_feature: float = 0.8

    def __post_init__(self) -> None:
        self.font_path = Path(self.font_path)
        if not self.font_path.is_file():
            raise ConfigError(f"arquivo de fonte nao encontrado: {self.font_path}")
        if self.hole_shape not in HOLE_SHAPES:
            raise ConfigError(
                f"--hole-shape invalido: {self.hole_shape!r} "
                f"(opcoes: {', '.join(HOLE_SHAPES)})"
            )
        if self.hole_size_mode not in HOLE_SIZE_MODES:
            raise ConfigError(f"--hole-size-mode invalido: {self.hole_size_mode!r}")
        if self.closed_end not in CLOSED_END_CHOICES:
            raise ConfigError(f"--closed-end invalido: {self.closed_end!r}")
        if self.hole_align not in HOLE_ALIGN_CHOICES:
            raise ConfigError(
                f"--hole-align invalido: {self.hole_align!r} "
                f"(opcoes: {', '.join(HOLE_ALIGN_CHOICES)})"
            )
        if self.hole_size <= 0:
            raise ConfigError("--hole-size deve ser maior que zero")
        if self.tolerance < 0:
            raise ConfigError("--tolerance nao pode ser negativa")
        if self.min_wall_thickness <= 0:
            raise ConfigError("--min-wall-thickness deve ser maior que zero")
        if self.hole_segments < 8:
            raise ConfigError("--hole-segments deve ser no minimo 8")
        if self.chamfer < 0:
            raise ConfigError("--chamfer nao pode ser negativo")
        if self.border_width < 0:
            raise ConfigError("--border-width nao pode ser negativa")
        if self.strut_width <= 0:
            raise ConfigError("--strut-width deve ser maior que zero")
        if self.letter_overlap < 0:
            raise ConfigError("--letter-overlap nao pode ser negativa")
        if self.relief < 0:
            raise ConfigError("--relief nao pode ser negativo")
        if self.curve_tolerance <= 0:
            raise ConfigError("--curve-tolerance deve ser maior que zero")
        if self.max_length <= 0:
            raise ConfigError("--max-length deve ser maior que zero")
        if self.closed_end != "none" and self.cap_thickness <= 0:
            raise ConfigError("--cap-thickness deve ser maior que zero com --closed-end")
        if self.text_height is not None and self.text_height <= 0:
            raise ConfigError("--text-height deve ser maior que zero")
        if self.max_text_height <= 0:
            raise ConfigError("--max-text-height deve ser maior que zero")
        if self.min_letter_exposure < 0:
            raise ConfigError("--min-letter-exposure nao pode ser negativa")
        if self.depth is not None and self.depth <= 0:
            raise ConfigError("--depth deve ser maior que zero")
        if 2 * self.chamfer >= self.hole_length_min:
            raise ConfigError("--chamfer grande demais para o comprimento do canal")

    # ------------------------------------------------------------------
    # Valores derivados
    # ------------------------------------------------------------------
    @property
    def hole_sides(self) -> int:
        """Numero de lados do perfil do furo (circulo = --hole-segments)."""
        sides = HOLE_SHAPES[self.hole_shape]
        return self.hole_segments if sides == 0 else sides

    @property
    def hole_circumradius(self) -> float:
        """Raio do circulo circunscrito ao perfil do furo, ja com tolerancia.

        Em ``circum`` o --hole-size e o diametro circunscrito (padrao, garante
        que a peca abraca um lapis de bitola nominal). Em ``inscribed`` o valor
        e a distancia entre faces opostas, util para lapis sextavados medidos
        com paquimetro.
        """
        radius = (self.hole_size + self.tolerance) / 2.0
        if self.hole_size_mode == "inscribed" and self.hole_shape != "circle":
            radius /= math.cos(math.pi / self.hole_sides)
        return radius

    @property
    def section(self) -> float:
        """Secao minima da peca em Y e Z: furo + tolerancia + 2 paredes."""
        return 2 * self.hole_circumradius + 2 * self.min_wall_thickness

    @property
    def hole_length_min(self) -> float:
        """Menor canal que faz sentido validar (usado so contra chanfro absurdo)."""
        return max(self.section, 4.0)

    @property
    def has_base(self) -> bool:
        """Existe uma base distinta das letras para elas subirem em relevo?

        Sem espinha e sem borda o perfil e so as letras: levantar as letras
        acima de si mesmas nao muda nada e ainda engrossa a peca inteira.
        """
        return self.enable_spine or self.enable_border

    @property
    def effective_relief(self) -> float:
        """Relevo que sera de fato aplicado (zero quando nao ha base)."""
        return self.relief if self.has_base else 0.0

    @property
    def needs_letter_contact(self) -> bool:
        """Sem espinha e sem borda, so o encosto entre letras segura a peca."""
        return not self.enable_spine and not self.enable_border

    @property
    def should_tighten(self) -> bool:
        """Aperta as letras ate se encostarem?

        Sem borda sao as proprias letras que formam a silhueta, entao elas
        precisam se tocar. Com borda o offset ja preenche os vaos, e apertar so
        embolaria o desenho -- mas ``--tighten``/``--no-tighten`` decide na mao.
        """
        if self.tighten_letters is not None:
            return self.tighten_letters
        return not self.enable_border

    @property
    def total_depth(self) -> float:
        """Profundidade total da peca: a base mais o relevo das letras."""
        return self.target_depth + self.effective_relief

    @property
    def readable_text_height(self) -> float:
        """Altura em que sobra ``--min-letter-exposure`` de letra fora da espinha.

        Abaixo disso a espinha cobre quase toda a letra e o nome deixa de ser
        legivel -- a peca vira um tijolo com a silhueta arredondada.
        """
        return self.section + self.min_letter_exposure

    @property
    def target_depth(self) -> float:
        """Profundidade da extrusao: nunca menor que a secao exigida pelo furo."""
        return max(self.depth or 0.0, self.section)


@dataclass
class OutputOptions:
    """Opcoes de saida, separadas da geometria."""

    output_dir: Path = field(default_factory=lambda: Path("output"))
    fmt: str = "stl"
    preview: bool = False
    preview_3d: bool = False
    overwrite: bool = False

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.fmt not in OUTPUT_FORMATS:
            raise ConfigError(
                f"--format invalido: {self.fmt!r} (opcoes: {', '.join(OUTPUT_FORMATS)})"
            )
