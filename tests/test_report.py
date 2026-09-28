"""Estados do resultado e o resumo do lote."""

from __future__ import annotations

from pathlib import Path

from pencil_tip_gen.report import Result, summarize_batch


def test_resultado_com_malha_conta_como_ok():
    assert Result(text="A", path=Path("a.stl")).ok


def test_preview_only_conta_como_ok():
    assert Result(text="A", preview_path=Path("a.svg"), preview_only=True).ok


def test_preview_sem_malha_fora_do_modo_preview_nao_conta():
    assert not Result(text="A", preview_path=Path("a.svg")).ok


def test_erro_e_pulado_nao_contam():
    assert not Result(text="A", error="falhou").ok
    assert not Result(text="A", skipped=True).ok


def test_resumo_vazio_para_um_nome_so():
    assert summarize_batch([Result(text="A", path=Path("a.stl"))]) == ""
