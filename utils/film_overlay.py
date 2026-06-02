"""
film_overlay.py — Desenha contornos, recuo e ROI sobre a imagem dos filmes,
usando as cores do tema do Chromis WEB.

Gera imagens PNG (bytes) prontas para exibir no Streamlit, sem depender de
matplotlib em runtime — usa PIL diretamente para ser leve.
"""

import io
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Cores do tema (mesmas do theme.py)
C_FILM = (63, 185, 80)      # verde — contorno do filme
C_FIELD = (88, 166, 255)    # azul — campo (quando menor que o filme)
C_RECOIL = (210, 153, 34)   # ambar — recuo da borda
C_ROI = (248, 81, 73)       # vermelho — ROI
C_TEXT = (230, 237, 243)    # texto claro


def _to_display_rgb(image: np.ndarray) -> Image.Image:
    """Converte array (qualquer dtype) para PIL RGB 8-bit para exibicao."""
    img = np.asarray(image)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    if img.dtype == np.uint16:
        img = (img / 256).astype(np.uint8)
    elif img.dtype != np.uint8:
        arr = img.astype(np.float64)
        if arr.max() > 0:
            arr = arr / arr.max() * 255
        img = arr.astype(np.uint8)
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    return Image.fromarray(img, "RGB")


def draw_overview(image: np.ndarray, ordered_films: list) -> bytes:
    """
    Desenha a imagem completa com todos os filmes contornados e numerados
    na ordem (claro -> escuro). Retorna PNG em bytes.
    """
    pil = _to_display_rgb(image).convert("RGB")
    draw = ImageDraw.Draw(pil)

    for f in ordered_films:
        minr, minc, maxr, maxc = f["bbox"]
        draw.rectangle([minc, minr, maxc, maxr], outline=C_FILM, width=3)
        label = f"#{f.get('order', 0) + 1}"
        # fundo do texto
        ty = max(0, minr - 16)
        draw.rectangle([minc, ty, minc + 28, ty + 15], fill=(13, 17, 23))
        draw.text((minc + 3, ty + 2), label, fill=C_FILM)

    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def draw_single_film(image: np.ndarray, film: dict, field_res: dict,
                     roi: dict) -> bytes:
    """
    Desenha UM filme recortado com: contorno do campo (se menor), recuo e ROI.
    Retorna PNG em bytes.
    """
    minr, minc, maxr, maxc = film["bbox"]
    crop = np.asarray(image)[minr:maxr, minc:maxc]
    pil = _to_display_rgb(crop).convert("RGB")

    # Ampliar para visualizacao melhor (filmes pequenos)
    scale = max(1, int(300 / max(pil.width, 1)))
    if scale > 1:
        pil = pil.resize((pil.width * scale, pil.height * scale), Image.NEAREST)
    draw = ImageDraw.Draw(pil)

    def sc(v):
        return v * scale

    # Campo (se menor que o filme) — azul
    if field_res["field_type"] == "smaller" and field_res["field_bbox"]:
        fb = field_res["field_bbox"]
        draw.rectangle([sc(fb[1]), sc(fb[0]), sc(fb[3]), sc(fb[2])],
                       outline=C_FIELD, width=2)

    # Recuo (area util) — ambar tracejado (simulado com linhas curtas)
    u = roi["usable_bbox"]
    _dashed_rect(draw, sc(u[1]), sc(u[0]), sc(u[3]), sc(u[2]), C_RECOIL, width=2)

    # ROI — vermelho
    r = roi["roi_bbox"]
    draw.rectangle([sc(r[1]), sc(r[0]), sc(r[3]), sc(r[2])],
                   outline=C_ROI, width=3)

    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def _dashed_rect(draw, x0, y0, x1, y1, color, width=2, dash=6, gap=4):
    """Desenha um retangulo tracejado."""
    # topo e base
    x = x0
    while x < x1:
        draw.line([x, y0, min(x + dash, x1), y0], fill=color, width=width)
        draw.line([x, y1, min(x + dash, x1), y1], fill=color, width=width)
        x += dash + gap
    # laterais
    y = y0
    while y < y1:
        draw.line([x0, y, x0, min(y + dash, y1)], fill=color, width=width)
        draw.line([x1, y, x1, min(y + dash, y1)], fill=color, width=width)
        y += dash + gap
