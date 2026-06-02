"""
report_generator.py - Gera o relatorio PDF do estudo (parcial ou total).

Correcoes: fonte DejaVu (acentos), foto dos filmes, grafico da curva, logo.
"""

import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_HERE = os.path.dirname(__file__)
_FONTS = os.path.join(_HERE, "..", "assets", "fonts")

_FONT = "Helvetica"
_FONT_B = "Helvetica-Bold"
try:
    reg = os.path.join(_FONTS, "DejaVuSans.ttf")
    regb = os.path.join(_FONTS, "DejaVuSans-Bold.ttf")
    if os.path.exists(reg) and os.path.exists(regb):
        pdfmetrics.registerFont(TTFont("DejaVu", reg))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", regb))
        _FONT = "DejaVu"
        _FONT_B = "DejaVu-Bold"
except Exception:
    pass


R = {
    "title":        {"pt": "Relatório de Dosimetria com Filme Radiocrômico",
                     "en": "Radiochromic Film Dosimetry Report"},
    "generated":    {"pt": "Gerado em", "en": "Generated on"},
    "responsible":  {"pt": "Responsável", "en": "Responsible"},
    "sec_setup":    {"pt": "1. Configuração do Estudo", "en": "1. Study Setup"},
    "sec_upload":   {"pt": "2. Filmes e Doses", "en": "2. Films and Doses"},
    "sec_calib":    {"pt": "3. Curva de Calibração", "en": "3. Calibration Curve"},
    "study_type":   {"pt": "Tipo de estudo", "en": "Study type"},
    "institution":  {"pt": "Instituição", "en": "Institution"},
    "machine":      {"pt": "Máquina", "en": "Machine"},
    "energy":       {"pt": "Energia", "en": "Energy"},
    "field":        {"pt": "Campo", "en": "Field"},
    "film":         {"pt": "Filme", "en": "Film"},
    "scanner":      {"pt": "Scanner", "en": "Scanner"},
    "channel":      {"pt": "Canal", "en": "Channel"},
    "n_films":      {"pt": "Número de filmes", "en": "Number of films"},
    "recoil":       {"pt": "Recuo da borda", "en": "Edge recoil"},
    "roi":          {"pt": "ROI", "en": "ROI"},
    "film_n":       {"pt": "Filme", "en": "Film"},
    "dose":         {"pt": "Dose", "en": "Dose"},
    "intensity":    {"pt": "Intensidade", "en": "Intensity"},
    "selected":     {"pt": "Selecionado", "en": "Selected"},
    "model":        {"pt": "Modelo", "en": "Model"},
    "formula":      {"pt": "Fórmula", "en": "Formula"},
    "recommended":  {"pt": "Recomendado", "en": "Recommended"},
    "nod":          {"pt": "NOD", "en": "NOD"},
    "pv_red":       {"pt": "PV vermelho", "en": "Red PV"},
    "yes":          {"pt": "Sim", "en": "Yes"},
    "no":           {"pt": "Não", "en": "No"},
    "films_img":    {"pt": "Filmes detectados:", "en": "Detected films:"},
    "field_col":    {"pt": "Campo", "en": "Field"},
    "roi_col":      {"pt": "ROI", "en": "ROI"},
    "field_full":   {"pt": "campo = filme", "en": "field = film"},
    "field_small":  {"pt": "campo < filme", "en": "field < film"},
    "curve_img":    {"pt": "Curva ajustada:", "en": "Fitted curve:"},
    "sec_dosemap":  {"pt": "4. Mapa de Dose", "en": "4. Dose Map"},
    "dm_film":      {"pt": "Filme", "en": "Film"},
    "dm_min":       {"pt": "Dose minima", "en": "Min dose"},
    "dm_mean":      {"pt": "Dose media", "en": "Mean dose"},
    "dm_max":       {"pt": "Dose maxima", "en": "Max dose"},
    "dm_ref_r":     {"pt": "Referencia (100%)", "en": "Reference (100%)"},
    "dm_img":       {"pt": "Distribuicao de dose:", "en": "Dose distribution:"},
    "footer":       {"pt": "Chromis WEB · AAPM TG-218 · Autor: MACIEL, J. O.",
                     "en": "Chromis WEB - AAPM TG-218 - Author: MACIEL, J. O."},
    "none":         {"pt": "(não informado)", "en": "(not provided)"},
}


def _tr(key, lang):
    return R.get(key, {}).get(lang, key)


def generate_report(study, lang="pt", selected_modules=None,
                    logo_path=None, films_image=None, curve_image=None,
                    dosemap_image=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=16*mm, bottomMargin=16*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=styles["Title"], fontName=_FONT_B,
                             fontSize=15, spaceAfter=4)
    h_sec = ParagraphStyle("s", parent=styles["Heading2"], fontName=_FONT_B,
                           fontSize=12, textColor=colors.HexColor("#1a7f4e"),
                           spaceBefore=12, spaceAfter=6)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontName=_FONT,
                           fontSize=8, textColor=colors.grey)
    cap = ParagraphStyle("cap", parent=styles["Normal"], fontName=_FONT,
                         fontSize=8, textColor=colors.HexColor("#1a7f4e"), spaceAfter=3)

    story = []

    if logo_path and os.path.exists(logo_path):
        try:
            img = RLImage(logo_path, width=40*mm, height=40*mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 6))
        except Exception:
            pass

    story.append(Paragraph(_tr("title", lang), h_title))
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(_tr("generated", lang) + ": " + now, small))
    story.append(Spacer(1, 8))

    def want(mod):
        if selected_modules is None:
            return study.get(mod) is not None
        return mod in selected_modules and study.get(mod) is not None

    none_txt = _tr("none", lang)

    if want("setup"):
        s = study["setup"]
        story.append(Paragraph(_tr("sec_setup", lang), h_sec))
        rows = [
            [_tr("study_type", lang), str(s.get("study_type", none_txt))],
            [_tr("institution", lang), str(s.get("institution") or none_txt)],
            [_tr("responsible", lang), str(s.get("responsible") or none_txt)],
            [_tr("machine", lang), str(s.get("machine") or none_txt) + " (" + str(s.get("manufacturer") or "-") + ")"],
            [_tr("energy", lang), str(s.get("energy") or none_txt)],
            [_tr("field", lang), str(s.get("field") or none_txt)],
            [_tr("film", lang), str(s.get("film_model", "-")) + " (lote " + str(s.get("film_lot") or "-") + ")"],
            [_tr("scanner", lang), str(s.get("scanner_model") or none_txt) + " - " + str(s.get("dpi", "-")) + " DPI"],
            [_tr("channel", lang), str(s.get("channel") or none_txt)],
        ]
        story.append(_make_table(rows))

    if want("upload"):
        u = study["upload"]
        story.append(Paragraph(_tr("sec_upload", lang), h_sec))
        info = [
            [_tr("n_films", lang), str(u.get("n_films", "-"))],
            [_tr("recoil", lang), str(u.get("recoil_mm", "-")) + " mm"],
            [_tr("roi", lang), str(u.get("roi_mode", "-"))],
        ]
        story.append(_make_table(info))
        story.append(Spacer(1, 6))

        if films_image:
            try:
                story.append(Paragraph(_tr("films_img", lang), cap))
                fimg = _fit_image(films_image, 150*mm, 70*mm)
                fimg.hAlign = "CENTER"
                story.append(fimg)
                story.append(Spacer(1, 6))
            except Exception:
                pass

        unit = u.get("unit", "cGy")
        header = [_tr("film_n", lang), _tr("dose", lang) + " (" + unit + ")",
                  _tr("intensity", lang), _tr("field_col", lang),
                  _tr("roi_col", lang), _tr("selected", lang)]
        data = [header]
        for f in u.get("films", []):
            ft = f.get("field_type", "")
            field_txt = (_tr("field_full", lang) if ft == "full"
                         else (_tr("field_small", lang) if ft == "smaller" else "-"))
            data.append([
                "#" + str(f["order"]+1), "%.0f" % f["dose"], "%.3f" % f["intensity"],
                field_txt, f.get("roi_mode", "-"),
                _tr("yes", lang) if f.get("selected") else _tr("no", lang),
            ])
        story.append(_make_data_table(data))

    if want("calibration"):
        c = study["calibration"]
        story.append(Paragraph(_tr("sec_calib", lang), h_sec))
        info = [
            [_tr("model", lang), str(c.get("model_name", "-"))],
            [_tr("formula", lang), str(c.get("formula", "-"))],
            [_tr("recommended", lang), str(c.get("recommended_name", "-"))],
            ["R2", "%.4f" % c.get("r_squared", 0)],
            ["RMSE", "%.2f %s" % (c.get("rmse", 0), c.get("unit", "cGy"))],
        ]
        story.append(_make_table(info))
        story.append(Spacer(1, 6))

        if curve_image:
            try:
                story.append(Paragraph(_tr("curve_img", lang), cap))
                cimg = _fit_image(curve_image, 140*mm, 85*mm)
                cimg.hAlign = "CENTER"
                story.append(cimg)
                story.append(Spacer(1, 6))
            except Exception:
                pass

        unit = c.get("unit", "cGy")
        header = [_tr("film_n", lang), _tr("dose", lang) + " (" + unit + ")",
                  _tr("pv_red", lang), _tr("nod", lang)]
        data = [header]
        for p in c.get("points", []):
            data.append(["#" + str(p["film"]), "%.0f" % p["dose"],
                         "%.1f" % p["pv_red"], "%.4f" % p["nod"]])
        story.append(_make_data_table(data))

    # ===== Mapa de Dose =====
    if want("dosemap"):
        dm = study["dosemap"]
        story.append(Paragraph(_tr("sec_dosemap", lang), h_sec))
        unit = dm.get("unit", "cGy")
        if dm.get("is_percent"):
            info = [
                [_tr("dm_film", lang), str(dm.get("film", "-"))],
                [_tr("dm_ref_r", lang), "%.0f %s" % (dm.get("ref_dose", 0), unit)],
                [_tr("dm_min", lang), "%.0f %%" % dm.get("pct_min", 0)],
                [_tr("dm_mean", lang), "%.0f %%" % dm.get("pct_mean", 0)],
                [_tr("dm_max", lang), "%.0f %%" % dm.get("pct_max", 0)],
            ]
        else:
            info = [
                [_tr("dm_film", lang), str(dm.get("film", "-"))],
                [_tr("dm_min", lang), "%.0f %s" % (dm.get("dose_min", 0), unit)],
                [_tr("dm_mean", lang), "%.0f %s" % (dm.get("dose_mean", 0), unit)],
                [_tr("dm_max", lang), "%.0f %s" % (dm.get("dose_max", 0), unit)],
            ]
        story.append(_make_table(info))
        story.append(Spacer(1, 6))
        if dosemap_image:
            try:
                story.append(Paragraph(_tr("dm_img", lang), cap))
                dimg = _fit_image(dosemap_image, 130*mm, 110*mm)
                dimg.hAlign = "CENTER"
                story.append(dimg)
            except Exception:
                pass

    story.append(Spacer(1, 18))
    story.append(Paragraph(_tr("footer", lang), small))

    doc.build(story)
    return buf.getvalue()


def _fit_image(img_bytes, max_w, max_h):
    from PIL import Image as PILImage
    with PILImage.open(io.BytesIO(img_bytes)) as im:
        w, h = im.size
    ratio = min(max_w / w, max_h / h)
    return RLImage(io.BytesIO(img_bytes), width=w * ratio, height=h * ratio)


def _make_table(rows):
    t = Table(rows, colWidths=[55*mm, 110*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
    ]))
    return t


def _make_data_table(data):
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_B),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a7f4e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t
