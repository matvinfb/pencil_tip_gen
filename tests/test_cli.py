"""Interface de linha de comando, ponta a ponta."""

from __future__ import annotations

import pytest
from dataclasses import MISSING, fields

from click.testing import CliRunner

from pencil_tip_gen.cli import main, read_names
from pencil_tip_gen.config import TipParams


@pytest.fixture
def run(font_path, tmp_path):
    runner = CliRunner()

    def invoke(*args, **kwargs):
        base = ["--font-path", str(font_path), "-o", str(tmp_path)]
        return runner.invoke(main, base + list(args), **kwargs)

    return invoke


def test_gera_um_stl(run, tmp_path):
    result = run("-n", "ALICE")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "alice.stl").is_file()
    assert "dimensoes" in result.output


def test_modo_silencioso_so_imprime_o_caminho(run, tmp_path):
    result = run("-n", "ALICE", "--quiet")
    assert result.exit_code == 0
    assert result.output.strip() == str(tmp_path / "alice.stl")


def test_lote_gera_um_arquivo_por_nome(run, tmp_path):
    lista = tmp_path / "nomes.txt"
    lista.write_text("# comentario\nALICE\n\nZoe\n", encoding="utf-8")
    result = run("-f", str(lista), "--yes")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "alice.stl").is_file()
    assert (tmp_path / "zoe.stl").is_file()
    assert "2/2 gerados" in result.output


def test_preview_gera_svg_ao_lado(run, tmp_path):
    assert run("-n", "ALICE", "--preview").exit_code == 0
    assert (tmp_path / "alice.svg").is_file()


def test_formato_e_respeitado(run, tmp_path):
    assert run("-n", "ALICE", "--format", "3mf").exit_code == 0
    assert (tmp_path / "alice.3mf").is_file()


def test_preview_only_gera_svg_sem_malha(run, tmp_path):
    result = run("-n", "ALICE", "--preview-only")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "alice.svg").is_file()
    assert not (tmp_path / "alice.stl").exists()
    assert "nao gravado" in result.output
    assert "dimensoes" in result.output, "as medidas ainda sao mostradas"


def test_preview_only_nao_pergunta_em_nome_longo(run, tmp_path):
    """Quem confere antes de gerar quer ver o exagero, nao responder prompt."""
    result = run("-n", "MARIA EDUARDA", "--preview-only")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "maria_eduarda.svg").is_file()
    assert "passa do limite" in result.output


def test_preview_only_repete_sem_overwrite(run, tmp_path):
    assert run("-n", "ALICE").exit_code == 0
    # A malha ja existe, mas conferir de novo nao esbarra no --overwrite.
    assert run("-n", "ALICE", "--preview-only").exit_code == 0
    assert (tmp_path / "alice.svg").is_file()


def test_preview_only_ignora_o_formato_da_malha(run, tmp_path):
    assert run("-n", "ALICE", "--preview-only", "--format", "3mf").exit_code == 0
    assert (tmp_path / "alice.svg").is_file()
    assert not (tmp_path / "alice.3mf").exists()


def test_preview_only_em_lote(run, tmp_path):
    lista = tmp_path / "nomes.txt"
    lista.write_text("ALICE\nZoe\n", encoding="utf-8")
    result = run("-f", str(lista), "--preview-only")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "alice.svg").is_file()
    assert (tmp_path / "zoe.svg").is_file()
    assert not list(tmp_path.glob("*.stl"))
    assert "2/2 conferidos" in result.output


def test_preview_only_quiet_imprime_o_svg(run, tmp_path):
    result = run("-n", "ALICE", "--preview-only", "--quiet")
    assert result.output.strip() == str(tmp_path / "alice.svg")


def test_no_spine_gera_peca_mais_leve(run, tmp_path):
    assert run("-n", "ALICE", "--preview-only").exit_code == 0
    com = (tmp_path / "alice.svg").read_text(encoding="utf-8")
    assert run("-n", "ALICE", "--no-spine", "--preview-only").exit_code == 0
    sem = (tmp_path / "alice.svg").read_text(encoding="utf-8")
    assert "sem espinha" in sem and "sem espinha" not in com


def test_no_spine_avisa_sobre_a_parede(run):
    result = run("-n", "ALICE", "--no-spine", "--preview-only")
    assert result.exit_code == 0
    assert "sem espinha" in result.output
    assert "% do canal com parede cheia" in result.output


def test_preview_3d_gera_png(run, tmp_path):
    result = run("-n", "ALICE", "--preview-3d", "--preview-only")
    assert result.exit_code == 0, result.output
    png = tmp_path / "alice_3d.png"
    assert png.is_file()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "render 3D" in result.output


def test_preview_3d_e_independente_do_preview_2d(run, tmp_path):
    assert run("-n", "ALICE", "--preview-3d").exit_code == 0
    assert (tmp_path / "alice_3d.png").is_file()
    assert (tmp_path / "alice.stl").is_file()
    assert not (tmp_path / "alice.svg").exists(), "--preview-3d nao implica --preview"


def test_nome_longo_pede_confirmacao(run):
    result = run("-n", "MARIA EDUARDA", input="n\n")
    assert result.exit_code == 0
    assert "passa do limite" in result.output
    assert "PULADO" in result.output or "pulado" in result.output


def test_nome_longo_confirmado_gera(run, tmp_path):
    result = run("-n", "MARIA EDUARDA", input="y\n")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "maria_eduarda.stl").is_file()


def test_yes_dispensa_o_prompt(run, tmp_path):
    result = run("-n", "MARIA EDUARDA", "--yes")
    assert result.exit_code == 0
    assert (tmp_path / "maria_eduarda.stl").is_file()


def test_strict_falha_em_vez_de_perguntar(run):
    result = run("-n", "MARIA EDUARDA", "--strict")
    assert result.exit_code == 1
    assert "passa do limite" in result.output


def test_sem_nome_e_erro_de_uso(run):
    result = run()
    assert result.exit_code == 2
    assert "pelo menos um --name" in result.output


def test_glifo_ausente_interrompe(run):
    result = run("-n", "日本")
    assert result.exit_code == 1
    assert "glifo" in result.output


def test_continue_on_error_segue_o_lote(run, tmp_path):
    lista = tmp_path / "nomes.txt"
    lista.write_text("日本\nALICE\n", encoding="utf-8")
    result = run("-f", str(lista), "--continue-on-error")
    assert result.exit_code == 1
    assert (tmp_path / "alice.stl").is_file()
    assert "1/2 gerados" in result.output


def test_nao_sobrescreve_sem_flag(run):
    assert run("-n", "ALICE").exit_code == 0
    assert run("-n", "ALICE").exit_code == 1
    assert run("-n", "ALICE", "--overwrite").exit_code == 0


def test_parametro_invalido_e_erro_de_uso(run):
    result = run("-n", "ALICE", "--min-wall-thickness", "0")
    assert result.exit_code == 2
    assert "--min-wall-thickness" in result.output


def test_read_names_junta_flag_e_arquivo(tmp_path):
    lista = tmp_path / "nomes.txt"
    lista.write_text("# ignorar\nBruno\n\n  Zoe  \n", encoding="utf-8")
    assert read_names(("ALICE", " "), lista) == ["ALICE", "Bruno", "Zoe"]


def test_read_names_sem_arquivo():
    assert read_names(("ALICE",), None) == ["ALICE"]


def test_defaults_da_cli_batem_com_os_do_tipparams():
    """Trava contra divergencia silenciosa entre as duas listas de padroes.

    Sao ~25 parametros declarados duas vezes -- no dataclass e nas flags. Quando
    os dois discordam, quem usa a CLI ve um comportamento e quem importa o
    pacote (ou escreve teste) ve outro, e nada acusa.
    """
    padroes = {
        campo.name: campo.default
        for campo in fields(TipParams)
        if campo.default is not MISSING
    }
    conferidos = 0
    for parametro in main.params:
        if parametro.name not in padroes:
            continue
        conferidos += 1
        assert parametro.default == padroes[parametro.name], (
            f"--{parametro.name.replace('_', '-')}: CLI={parametro.default!r} "
            f"mas TipParams={padroes[parametro.name]!r}"
        )
    assert conferidos > 20, "quase nenhum parametro foi conferido"
