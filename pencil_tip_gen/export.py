"""Gravacao dos arquivos de malha e nomes de arquivo."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import trimesh

from .config import OutputOptions

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\
<Default Extension="rels" \
ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\
<Default Extension="model" \
ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships \
xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\
<Relationship Target="/3D/3dmodel.model" Id="rel0" \
Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>"""

_MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


class ExportError(ValueError):
    """Falha ao gravar o arquivo de saida."""


def slugify(text: str) -> str:
    """Nome de arquivo seguro a partir do nome impresso ('Ana Julia' -> 'ana_julia')."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "ponteira"


def output_path(text: str, options: OutputOptions) -> Path:
    return options.output_dir / f"{slugify(text)}.{options.fmt}"


def preview_path(text: str, options: OutputOptions) -> Path:
    """Caminho do SVG, que nao depende do formato escolhido para a malha."""
    return options.output_dir / f"{slugify(text)}.svg"


def preview3d_path(text: str, options: OutputOptions) -> Path:
    """Caminho do PNG com o render 3D."""
    return options.output_dir / f"{slugify(text)}_3d.png"


def write_3mf(mesh: trimesh.Trimesh, path: Path, name: str) -> None:
    """Escritor 3MF minimo: zip com os tres arquivos exigidos pelo nucleo do formato.

    O exportador do trimesh depende do networkx (grafo de cena) para algo que
    aqui e sempre uma malha unica, entao vale mais gravar o pacote direto -- e
    assim a unidade fica declarada em milimetros, que e o que o fatiador le.
    """
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    verts_xml = "".join(
        f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}"/>' for x, y, z in vertices
    )
    tris_xml = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces
    )
    safe_name = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{_MODEL_NS}">'
        '<metadata name="Application">pencil_tip_gen</metadata>'
        f'<metadata name="Title">{safe_name}</metadata>'
        '<resources>'
        '<object id="1" type="model"><mesh>'
        f"<vertices>{verts_xml}</vertices>"
        f"<triangles>{tris_xml}</triangles>"
        "</mesh></object></resources>"
        '<build><item objectid="1"/></build></model>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _RELS)
        archive.writestr("3D/3dmodel.model", model)


def export_mesh(mesh: trimesh.Trimesh, text: str, options: OutputOptions) -> Path:
    """Grava a malha no formato pedido e devolve o caminho final."""
    path = output_path(text, options)
    if path.exists() and not options.overwrite:
        raise ExportError(f"{path} ja existe (use --overwrite para sobrescrever)")
    path.parent.mkdir(parents=True, exist_ok=True)
    if options.fmt == "3mf":
        write_3mf(mesh, path, text)
        return path
    data = mesh.export(file_type=options.fmt)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    return path
