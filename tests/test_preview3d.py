"""Render 3D: camera, rasterizador com z-buffer e escrita do PNG."""

from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest
import trimesh

from pencil_tip_gen.config import TipParams
from pencil_tip_gen.preview3d import (
    BACKGROUND,
    _camera,
    _downsample,
    _rasterize,
    _visible_triangles,
    render_preview_3d,
    write_png,
)
from pencil_tip_gen.profile2d import build_profile
from pencil_tip_gen.solid import build_solid


def read_png(path):
    """Le de volta um PNG RGB simples, so para conferir o que foi gravado."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\x0a"
    pos, pixels, header = 8, b"", None
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        esperado = zlib.crc32(kind + payload) & 0xFFFFFFFF
        obtido = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])[0]
        assert obtido == esperado, f"CRC errado no bloco {kind}"
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            pixels += payload
        pos += 12 + length
    width, height, bits, color_type = header[0], header[1], header[2], header[3]
    assert (bits, color_type) == (8, 2), "RGB de 8 bits"
    raw = zlib.decompress(pixels)
    linha = width * 3 + 1
    assert len(raw) == linha * height
    imagem = np.frombuffer(raw, np.uint8).reshape(height, linha)
    assert (imagem[:, 0] == 0).all(), "todas as linhas sem filtro"
    return imagem[:, 1:].reshape(height, width, 3)


def test_camera_da_eixos_ortonormais():
    for elev, azim in [(0, 0), (26, -40), (-30, 100), (89, 15)]:
        eye, right, up = _camera(elev, azim)
        for vetor in (eye, right, up):
            assert np.linalg.norm(vetor) == pytest.approx(1.0)
        assert eye @ right == pytest.approx(0, abs=1e-9)
        assert eye @ up == pytest.approx(0, abs=1e-9)
        assert right @ up == pytest.approx(0, abs=1e-9)


def test_faces_de_costas_sao_descartadas():
    """Num cubo fechado, exatamente metade das faces olha para a camera."""
    cubo = trimesh.creation.box((10, 10, 10))
    triangulos, _, _, _ = _visible_triangles(cubo, 26.0, -40.0)
    assert len(triangulos) == len(cubo.faces) // 2


def test_zbuffer_desenha_o_que_esta_na_frente():
    """Dois triangulos sobrepostos: vence o mais perto, nao o desenhado por ultimo."""
    fundo = np.array([[(0, 0), (10, 0), (0, 10)]], dtype=float)
    frente = fundo.copy()
    triangulos = np.vstack([fundo, frente])
    profundidades = np.array([[0, 0, 0], [5, 5, 5]], dtype=float)
    cores = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    # O de tras vem por ultimo na lista e mesmo assim nao aparece.
    imagem = _rasterize(
        triangulos[::-1], profundidades[::-1], cores[::-1],
        12, 12, np.array([0.0, 0.0]), 1.0,
    )
    pintado = imagem[~np.all(imagem == np.array(BACKGROUND, np.float32), axis=-1)]
    assert len(pintado) > 0
    assert np.allclose(pintado, [0.0, 1.0, 0.0]), "o triangulo da frente venceu"


def test_downsample_tira_a_media_dos_blocos():
    imagem = np.zeros((4, 4, 3), dtype=np.float32)
    imagem[0, 0] = 1.0
    reduzida = _downsample(imagem, 2)
    assert reduzida.shape == (2, 2, 3)
    assert reduzida[0, 0, 0] == pytest.approx(0.25)


def test_png_gravado_pode_ser_lido_de_volta(tmp_path):
    imagem = np.zeros((3, 5, 3), dtype=np.float32)
    imagem[1, 2] = (1.0, 0.5, 0.0)
    caminho = write_png(tmp_path / "x.png", imagem)
    lida = read_png(caminho)
    assert lida.shape == (3, 5, 3)
    assert tuple(lida[1, 2]) == (255, 128, 0)
    assert tuple(lida[0, 0]) == (0, 0, 0)


def test_render_da_peca_sai_com_a_peca_desenhada(font_path, tmp_path):
    params = TipParams(font_path=font_path)
    solid = build_solid(build_profile("ALICE", params), params)
    caminho = render_preview_3d(solid, tmp_path / "alice_3d.png", width=300)
    imagem = read_png(caminho)
    assert imagem.shape[1] == 300
    fundo = np.array(np.array(BACKGROUND) * 255 + 0.5, dtype=np.uint8)
    pintados = ~np.all(np.abs(imagem.astype(int) - fundo) <= 1, axis=-1)
    fracao = pintados.mean()
    assert 0.05 < fracao < 0.95, f"so {fracao:.0%} da imagem tem peca"


def test_render_sem_espinha_tambem_funciona(font_path, tmp_path):
    params = TipParams(font_path=font_path, enable_spine=False)
    solid = build_solid(build_profile("ALICE", params), params)
    caminho = render_preview_3d(solid, tmp_path / "s.png", width=240)
    assert read_png(caminho).shape[1] == 240
