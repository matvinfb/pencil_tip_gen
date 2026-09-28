"""Gravacao dos arquivos e preview."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

import pytest
import trimesh

from pencil_tip_gen.config import OutputOptions
from pencil_tip_gen.export import (
    ExportError,
    export_mesh,
    output_path,
    preview3d_path,
    preview_path,
    slugify,
)
from pencil_tip_gen.preview import render_preview
from pencil_tip_gen.profile2d import build_profile
from pencil_tip_gen.solid import build_solid

MODEL_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


@pytest.fixture(scope="module")
def solid(font_path):
    from pencil_tip_gen.config import TipParams

    params = TipParams(font_path=font_path)
    return build_solid(build_profile("Zoe", params), params), params


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("ALICE", "alice"),
        ("Ana Julia", "ana_julia"),
        ("Jose Antonio", "jose_antonio"),
        ("Joao", "joao"),
        ("!!!", "ponteira"),
    ],
)
def test_slug(texto, esperado):
    assert slugify(texto) == esperado


def test_acentos_viram_ascii():
    assert slugify("João") == "joao"
    assert slugify("Zoé") == "zoe"


@pytest.mark.parametrize("fmt", ["stl", "obj"])
def test_malha_exportada_pode_ser_relida(solid, tmp_path, fmt):
    mesh, _ = solid
    options = OutputOptions(output_dir=tmp_path, fmt=fmt)
    path = export_mesh(mesh.mesh, "Zoe", options)
    assert path == output_path("Zoe", options)
    relida = trimesh.load(path, force="mesh")
    assert relida.is_watertight
    assert relida.volume == pytest.approx(mesh.mesh.volume, rel=1e-6)


def test_3mf_tem_a_estrutura_do_formato(solid, tmp_path):
    mesh, _ = solid
    options = OutputOptions(output_dir=tmp_path, fmt="3mf")
    path = export_mesh(mesh.mesh, "Zoe", options)
    with zipfile.ZipFile(path) as archive:
        nomes = set(archive.namelist())
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} == nomes
        for nome in nomes:
            ET.fromstring(archive.read(nome))  # todos sao XML valido
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
    assert root.get("unit") == "millimeter"
    assert len(root.find(f".//{MODEL_NS}vertices")) == len(mesh.mesh.vertices)
    assert len(root.find(f".//{MODEL_NS}triangles")) == len(mesh.mesh.faces)


def test_nao_sobrescreve_sem_permissao(solid, tmp_path):
    mesh, _ = solid
    options = OutputOptions(output_dir=tmp_path, fmt="stl")
    export_mesh(mesh.mesh, "Zoe", options)
    with pytest.raises(ExportError, match="ja existe"):
        export_mesh(mesh.mesh, "Zoe", options)
    export_mesh(mesh.mesh, "Zoe", OutputOptions(output_dir=tmp_path, overwrite=True))


@pytest.mark.parametrize("fmt", ["stl", "obj", "3mf"])
def test_caminho_do_preview_nao_depende_do_formato(tmp_path, fmt):
    options = OutputOptions(output_dir=tmp_path, fmt=fmt)
    assert preview_path("Ana Júlia", options) == tmp_path / "ana_julia.svg"
    assert output_path("Ana Júlia", options).suffix == f".{fmt}"


def test_caminho_do_render_3d(tmp_path):
    options = OutputOptions(output_dir=tmp_path, fmt="3mf")
    assert preview3d_path("Ana Júlia", options) == tmp_path / "ana_julia_3d.png"


def test_preview_e_svg_valido(solid, tmp_path):
    mesh, params = solid
    path = render_preview(mesh, params, "Zoe", tmp_path / "zoe.svg")
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    assert root.get("width").endswith("mm"), "o preview sai na escala 1:1"
    assert "Zoe" in path.read_text(encoding="utf-8")
