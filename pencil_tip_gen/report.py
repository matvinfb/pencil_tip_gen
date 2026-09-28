"""Resumo legivel do que foi gerado."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import TipParams
from .solid import Solid


@dataclass
class Result:
    """Uma ponteira gerada (ou pulada, se ``path`` for None)."""

    text: str
    solid: Solid | None = None
    path: Path | None = None
    preview_path: Path | None = None
    preview_3d_path: Path | None = None
    warnings: tuple[str, ...] = ()
    error: str | None = None
    skipped: bool = False
    preview_only: bool = False

    @property
    def ok(self) -> bool:
        """Deu certo: gravou a malha, ou o preview quando so ele foi pedido."""
        return self.path is not None or (
            self.preview_only and self.preview_path is not None
        )


def all_warnings(solid: Solid) -> list[str]:
    """Junta os avisos do perfil 2D e os da malha 3D."""
    return [*solid.profile.warnings, *solid.warnings]


def describe(result: Result, params: TipParams) -> str:
    """Bloco de texto com as medidas da peca."""
    if result.error:
        return f"{result.text}\n  erro            {result.error}"
    if result.skipped:
        return f"{result.text}\n  pulado          confirmacao negada pelo usuario"

    solid = result.solid
    assert solid is not None
    profile = solid.profile
    width, height, depth = solid.extents
    exposure = profile.text_height - params.section

    lines = [
        result.text,
        f"  fonte           {profile.font_name} (escala {profile.scale:.5f})",
        f"  letras          {profile.text_height:.2f} mm"
        f"  |  faixa do canal {params.section:.2f} mm"
        f"  |  letra acima da faixa {exposure:.2f} mm",
        f"  dimensoes       {width:.2f} x {height:.2f} x {depth:.2f} mm (X x Y x Z)",
        f"  profundidade    base {solid.depth:.2f} mm"
        + (
            f"  +  relevo das letras {solid.relief:.2f} mm"
            if solid.relief
            else (
                "  |  sem relevo: nao ha base (--no-spine com --no-border)"
                if params.relief and not params.has_base
                else "  |  sem relevo (--relief 0)"
            )
        ),
        f"  silhueta        "
        + (
            f"letras + borda de {params.border_width:g} mm"
            if params.enable_border
            else "so as letras"
        )
        + (
            f" + espinha de reforco ({params.section:.2f} mm)"
            if params.enable_spine
            else " (sem espinha)"
        )
        + (
            f", apertadas com {params.letter_overlap:g} mm de sobreposicao"
            if params.should_tighten
            else ", no espacamento natural da fonte"
        ),
        f"  canal           {params.hole_shape} {params.hole_size:g} + "
        f"{params.tolerance:g} mm, chanfro {params.chamfer:g} mm, "
        f"comprimento {profile.hole_length:.2f} mm"
        + (f", tampa a {params.closed_end}" if params.closed_end != "none" else ""),
        f"  parede minima   {params.min_wall_thickness:.2f} mm"
        f"  |  {100 * solid.wall_coverage:.0f}% do canal com parede cheia"
        f"  |  volume {solid.volume_cm3:.2f} cm3"
        f"  |  {len(solid.mesh.faces)} triangulos",
        f"  arquivo         {result.path}"
        if result.path
        else "  arquivo         nao gravado (--preview-only)",
    ]
    if result.preview_path:
        lines.append(f"  preview         {result.preview_path}")
    if result.preview_3d_path:
        lines.append(f"  render 3D       {result.preview_3d_path}")
    lines.extend(f"  aviso           {w}" for w in result.warnings)
    return "\n".join(lines)


def summarize_batch(results: list[Result]) -> str:
    """Tabela final para o modo lote."""
    if len(results) <= 1:
        return ""
    rows = ["", "resumo:"]
    for result in results:
        if result.error:
            status = f"ERRO  {result.error}"
        elif result.skipped:
            status = "PULADO"
        else:
            width, height, depth = result.solid.extents
            destino = result.path or f"{result.preview_path} (so preview)"
            status = f"{width:7.2f} x {height:6.2f} x {depth:6.2f} mm  ->  {destino}"
        flag = "!" if result.warnings else " "
        rows.append(f"  {flag} {result.text:<20} {status}")
    ok = sum(1 for result in results if result.ok)
    verbo = "conferidos" if all(r.preview_only for r in results) else "gerados"
    rows.append(f"  {ok}/{len(results)} {verbo}")
    return "\n".join(rows)
