"""Interface de linha de comando."""

from __future__ import annotations

from pathlib import Path

import click

from .config import (
    CLOSED_END_CHOICES,
    HOLE_ALIGN_CHOICES,
    HOLE_SHAPES,
    HOLE_SIZE_MODES,
    OUTPUT_FORMATS,
    ConfigError,
    OutputOptions,
    TipParams,
)
from .export import ExportError, export_mesh, preview3d_path, preview_path
from .fonts import FontError
from .holes import HoleError
from .preview import render_preview
from .preview3d import render_preview_3d
from .profile2d import ProfileError, build_profile
from .report import Result, all_warnings, describe, summarize_batch
from .solid import SolidError, build_solid

GeneratorError = (ConfigError, FontError, ProfileError, HoleError, SolidError, ExportError)


def read_names(names: tuple[str, ...], names_file: Path | None) -> list[str]:
    """Junta os nomes da linha de comando com os do arquivo em lote."""
    collected = [name for name in names if name.strip()]
    if names_file:
        for line in names_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                collected.append(line)
    return collected


def length_message(text: str, width: float, params: TipParams) -> str:
    return (
        f"{text}: {width:.2f} mm passa do limite de {params.max_length:g} mm "
        "(metade de um lapis novo); para encurtar, reduza --min-letter-exposure "
        "ou --text-height"
    )


def confirm_length(
    text: str, width: float, params: TipParams, assume_yes: bool, strict: bool
) -> bool:
    """Regra 4.4 do README: nome maior que o limite pede confirmacao."""
    if width <= params.max_length:
        return True
    message = length_message(text, width, params)
    if strict:
        raise ProfileError(message)
    if assume_yes:
        # Vai para o stderr: com --quiet o stdout carrega so os caminhos.
        click.echo(f"  aviso           {message}; seguindo por causa de --yes", err=True)
        return True
    try:
        return click.confirm(f"{message}. Gerar mesmo assim?", default=True)
    except click.Abort as exc:  # sem terminal para responder (lote, pipe, CI)
        raise ProfileError(f"{message}; use --yes para gerar assim mesmo") from exc


def generate_one(
    text: str,
    params: TipParams,
    options: OutputOptions,
    *,
    assume_yes: bool = False,
    strict: bool = False,
    preview_only: bool = False,
) -> Result:
    """Gera uma ponteira: perfil, solido e, se for o caso, arquivo e preview.

    Em ``preview_only`` a malha ainda e construida e validada -- o booleano
    custa quase o mesmo que o perfil, e sem ele o preview mostraria medidas de
    uma peca que talvez nem feche. O que muda e que nada de malha vai para o
    disco, e o limite de comprimento vira aviso em vez de pergunta: quem esta
    conferindo antes de gerar quer justamente ver o exagero na tela.
    """
    profile = build_profile(text, params)
    extra: list[str] = []
    if preview_only:
        if profile.width > params.max_length:
            extra.append(length_message(text, profile.width, params))
    elif not confirm_length(text, profile.width, params, assume_yes, strict):
        return Result(text=text, skipped=True)

    solid = build_solid(profile, params)
    path = None if preview_only else export_mesh(solid.mesh, text, options)
    svg = None
    if options.preview or preview_only:
        svg = render_preview(solid, params, text, preview_path(text, options))
    png = None
    if options.preview_3d:
        png = render_preview_3d(solid, preview3d_path(text, options))
    return Result(
        text=text,
        solid=solid,
        path=path,
        preview_path=svg,
        preview_3d_path=png,
        preview_only=preview_only,
        warnings=tuple([*all_warnings(solid), *extra]),
    )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--name", "-n", "names", multiple=True, help="Nome a gerar (repetivel).")
@click.option(
    "--file",
    "-f",
    "names_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Arquivo .txt com um nome por linha (# comenta).",
)
@click.option(
    "--font-path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Arquivo .ttf ou .otf a usar.",
)
@click.option("--hole-size", default=7.5, show_default=True, help="Bitola do encaixe em mm.")
@click.option(
    "--hole-shape",
    type=click.Choice(list(HOLE_SHAPES)),
    default="circle",
    show_default=True,
    help="Perfil do canal de encaixe.",
)
@click.option(
    "--hole-size-mode",
    type=click.Choice(list(HOLE_SIZE_MODES)),
    default="circum",
    show_default=True,
    help="Como ler --hole-size: circulo circunscrito ou distancia entre faces.",
)
@click.option("--tolerance", default=0.2, show_default=True, help="Folga de impressao em mm.")
@click.option("--hole-rotation", default=0.0, show_default=True, help="Giro do perfil em graus.")
@click.option("--hole-segments", default=64, show_default=True, help="Lados do circulo.")
@click.option(
    "--hole-align",
    type=click.Choice(list(HOLE_ALIGN_CHOICES)),
    default="bottom",
    show_default=True,
    help="Onde o canal fica na altura das letras.",
)
@click.option("--hole-offset-y", default=0.0, show_default=True, help="Ajuste fino do eixo em mm.")
@click.option("--chamfer", default=1.0, show_default=True, help="Chanfro de entrada em mm.")
@click.option(
    "--closed-end",
    type=click.Choice(list(CLOSED_END_CHOICES)),
    default="none",
    show_default=True,
    help="Fecha uma das pontas do canal.",
)
@click.option("--cap-thickness", default=2.0, show_default=True, help="Espessura da tampa em mm.")
@click.option(
    "--min-wall-thickness", default=3.0, show_default=True, help="Parede ao redor do canal em mm."
)
@click.option("--max-length", default=87.5, show_default=True, help="Comprimento maximo em mm.")
@click.option(
    "--spine/--no-spine",
    "enable_spine",
    default=True,
    show_default=True,
    help="Barra central de reforco que fecha a parede em volta do canal.",
)
@click.option(
    "--enable-border/--no-border",
    default=False,
    show_default=True,
    help="Borda de silhueta ao redor das letras.",
)
@click.option("--border-width", default=1.0, show_default=True, help="Offset da borda em mm.")
@click.option(
    "--relief",
    default=2.0,
    show_default=True,
    help="Quanto as letras sobem acima da base, em mm.",
)
@click.option(
    "--tighten/--no-tighten",
    "tighten_letters",
    default=None,
    help="Aperta as letras ate se encostarem. Padrao: liga sem borda, desliga com borda.",
)
@click.option(
    "--letter-overlap",
    default=0.4,
    show_default=True,
    help="Quanto as letras apertadas se sobrepoem, em mm.",
)
@click.option(
    "--struts/--no-struts",
    "enable_struts",
    default=True,
    show_default=True,
    help="Barras de suporte para pingos e acentos soltos.",
)
@click.option("--strut-width", default=1.2, show_default=True, help="Espessura da barra em mm.")
@click.option("--text-height", type=float, default=None, help="Altura fixa das letras em mm.")
@click.option(
    "--max-text-height", default=30.0, show_default=True, help="Teto da altura automatica em mm."
)
@click.option(
    "--min-letter-exposure",
    default=6.0,
    show_default=True,
    help="Letra que deve sobrar acima da espinha, em mm.",
)
@click.option("--depth", type=float, default=None, help="Profundidade da extrusao em mm.")
@click.option("--letter-spacing", default=0.0, show_default=True, help="Espaco entre letras em mm.")
@click.option(
    "--curve-tolerance", default=0.05, show_default=True, help="Erro maximo ao achatar curvas."
)
@click.option("--min-feature", default=0.8, show_default=True, help="Detalhe minimo aceitavel.")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("output"),
    show_default=True,
    help="Pasta de saida.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(list(OUTPUT_FORMATS)),
    default="stl",
    show_default=True,
    help="Formato do arquivo de malha.",
)
@click.option("--preview", is_flag=True, help="Grava tambem um SVG do perfil.")
@click.option(
    "--preview-3d",
    "preview_3d",
    is_flag=True,
    help="Grava um PNG com a peca renderizada em 3D (leva alguns segundos).",
)
@click.option(
    "--preview-only",
    is_flag=True,
    help="So o SVG: confere as medidas sem gravar nenhuma malha.",
)
@click.option("--overwrite", is_flag=True, help="Sobrescreve arquivos existentes.")
@click.option("--yes", "-y", "assume_yes", is_flag=True, help="Nao pergunta nada.")
@click.option("--strict", is_flag=True, help="Falha em vez de perguntar.")
@click.option("--continue-on-error", is_flag=True, help="Segue o lote apos um erro.")
@click.option("--quiet", "-q", is_flag=True, help="So imprime os caminhos gerados.")
def main(names, names_file, output_dir, fmt, preview, preview_3d, preview_only,
         overwrite, assume_yes, strict, continue_on_error, quiet, **geometry):
    """Gera ponteiras 3D personalizadas com o nome em alto-relevo.

    Exemplos:

        pencil-tip-gen -n ALICE --font-path /usr/share/fonts/TTF/DejaVuSans-Bold.ttf

        pencil-tip-gen -f nomes.txt --font-path fonte.ttf --hole-shape hexagon --preview
    """
    collected = read_names(names, names_file)
    if not collected:
        raise click.UsageError("informe pelo menos um --name ou um --file")

    try:
        params = TipParams(**geometry)
        options = OutputOptions(
            output_dir=output_dir,
            fmt=fmt,
            preview=preview,
            preview_3d=preview_3d,
            overwrite=overwrite,
        )
    except ConfigError as exc:
        raise click.UsageError(str(exc)) from exc

    results: list[Result] = []
    failed = False
    for text in collected:
        try:
            result = generate_one(
                text,
                params,
                options,
                assume_yes=assume_yes,
                strict=strict,
                preview_only=preview_only,
            )
        except GeneratorError as exc:
            result = Result(text=text, error=str(exc))
            failed = True
            if not continue_on_error:
                click.echo(describe(result, params), err=True)
                raise SystemExit(1) from exc
        results.append(result)
        if quiet:
            saida = result.path or result.preview_path or result.preview_3d_path
            if saida:
                click.echo(str(saida))
        else:
            click.echo(describe(result, params))

    if not quiet:
        summary = summarize_batch(results)
        if summary:
            click.echo(summary)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
