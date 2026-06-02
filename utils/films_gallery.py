"""films_gallery.py - Galeria de filmes numerados com legenda, usando PIL.

Reescrito para usar PIL (Pillow) em vez de matplotlib, porque o overlay PIL
ja funciona no app (visao geral). Mais robusto no Streamlit Cloud.
"""
import io
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_TXT = {
    "film": {"pt": "Filme", "en": "Film"},
    "recoil": {"pt": "recuo", "en": "recoil"},
    "roi": {"pt": "ROI", "en": "ROI"},
    "field_full": {"pt": "campo = filme", "en": "field = film"},
    "field_smaller": {"pt": "campo < filme", "en": "field < film"},
    "legend_film": {"pt": "Filme", "en": "Film"},
    "legend_recoil": {"pt": "Recuo", "en": "Recoil"},
    "legend_roi": {"pt": "ROI", "en": "ROI"},
}

C_FILM = (63, 185, 80)      # verde - contorno do filme
C_RECOIL = (210, 153, 34)   # ambar - recuo
C_ROI = (248, 81, 73)       # vermelho - ROI


def _load_font(size):
    """Tenta carregar uma fonte TTF; cai no default se nao achar."""
    import os
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, "..", "assets", "fonts", "DejaVuSans.ttf"),
        os.path.join(here, "..", "assets", "fonts", "DejaVuSans-Bold.ttf"),
    ]
    for c in candidates:
        try:
            if os.path.exists(c):
                return ImageFont.truetype(c, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _to_rgb(image):
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


def make_films_gallery(image_rgb, ordered_films, doses_map=None, unit="cGy",
                       lang="pt", theme="light", roi_info=None):
    """
    Monta UMA imagem (PNG bytes) com todos os filmes recortados, numerados,
    com titulo (dose), contornos (recuo ambar, ROI vermelho) e legenda. Usa PIL.
    """
    def tr(k):
        return _TXT[k][lang]

    pil_full = _to_rgb(image_rgb)
    n = len(ordered_films)
    if n == 0:
        return None

    # Tamanho de cada celula (mais largura para a legenda caber)
    cell_w, cell_h = 300, 250
    pad = 16
    img_max_h = 150
    title_h = 26

    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols

    bg = (255, 255, 255) if theme == "light" else (13, 17, 23)
    fg = (30, 41, 59) if theme == "light" else (230, 237, 243)
    sub = (71, 85, 105) if theme == "light" else (139, 148, 158)

    legend_band = 30  # faixa para a legenda de cores no rodape
    canvas_w = ncols * cell_w + (ncols + 1) * pad
    canvas_h = nrows * cell_h + (nrows + 1) * pad + legend_band
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)
    draw = ImageDraw.Draw(canvas)

    f_title = _load_font(15)
    f_legend = _load_font(11)

    for i, film in enumerate(ordered_films):
        row = i // ncols
        col = i % ncols
        x0 = pad + col * (cell_w + pad)
        y0 = pad + row * (cell_h + pad)

        order = film.get("order", i)

        # Titulo
        dose_txt = ""
        if doses_map is not None:
            dv = doses_map.get(f"dose_{order}")
            if dv is not None:
                dose_txt = f" - {dv:.0f} {unit}"
        title = f"{tr('film')} #{order+1}{dose_txt}"
        if f_title:
            draw.text((x0, y0), title, fill=fg, font=f_title)

        # Recorte do filme
        minr, minc, maxr, maxc = film["bbox"]
        crop = pil_full.crop((minc, minr, maxc, maxr))
        cw, ch = crop.size
        ratio = min(cell_w / cw, img_max_h / ch)
        new_w, new_h = max(1, int(cw * ratio)), max(1, int(ch * ratio))
        crop = crop.resize((new_w, new_h), Image.LANCZOS)

        img_x = x0 + (cell_w - new_w) // 2
        img_y = y0 + title_h
        canvas.paste(crop, (img_x, img_y))

        # Contorno verde do filme
        draw.rectangle([img_x, img_y, img_x + new_w, img_y + new_h],
                       outline=C_FILM, width=3)

        # Contornos internos: recuo (ambar tracejado) e ROI (vermelho)
        ri = (roi_info or {}).get(order, {})
        # Recuo: ~10% para dentro (representativo)
        rec_in = int(min(new_w, new_h) * 0.10)
        draw.rectangle([img_x + rec_in, img_y + rec_in,
                        img_x + new_w - rec_in, img_y + new_h - rec_in],
                       outline=C_RECOIL, width=2)
        # ROI: ~30% central (representativo)
        roi_mx = int(new_w * 0.30)
        roi_my = int(new_h * 0.22)
        draw.rectangle([img_x + roi_mx, img_y + roi_my,
                        img_x + new_w - roi_mx, img_y + new_h - roi_my],
                       outline=C_ROI, width=2)

        # Legenda de texto (recuo, ROI, campo) - quebrada em 2 linhas se preciso
        parts = []
        if ri.get("recoil_mm") is not None:
            parts.append(f"{tr('recoil')} {ri['recoil_mm']}mm")
        if ri.get("roi_mode"):
            parts.append(f"{tr('roi')} {ri['roi_mode']}")
        if ri.get("field_type"):
            parts.append(tr("field_full") if ri["field_type"] == "full"
                         else tr("field_smaller"))
        if parts and f_legend:
            line1 = " - ".join(parts[:2])
            line2 = parts[2] if len(parts) > 2 else ""
            ly = img_y + new_h + 6
            draw.text((img_x, ly), line1, fill=sub, font=f_legend)
            if line2:
                draw.text((img_x, ly + 15), line2, fill=sub, font=f_legend)

    # Legenda de cores no rodape
    if f_legend:
        ly = canvas_h - legend_band + 8
        lx = pad
        items = [
            (C_FILM, tr("legend_film")),
            (C_RECOIL, tr("legend_recoil")),
            (C_ROI, tr("legend_roi")),
        ]
        for color, label in items:
            draw.rectangle([lx, ly, lx + 12, ly + 12], fill=color)
            draw.text((lx + 18, ly), label, fill=sub, font=f_legend)
            lx += 30 + len(label) * 7

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
