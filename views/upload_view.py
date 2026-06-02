"""upload_view.py - Upload, deteccao, ordenacao e ROI dos filmes (N filmes)."""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS


def upload_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_config')}</div>", unsafe_allow_html=True)

    saved = state.setdefault("uploaded_films", [])

    files = st.file_uploader(
        t("mod_upload"), type=["tif", "tiff", "png", "jpg", "jpeg"],
        accept_multiple_files=True, key="upload_films_widget",
    )
    if files:
        novos = [{"name": f.name, "bytes": f.getvalue()} for f in files]
        state["uploaded_films"] = novos
        saved = novos

    if not saved:
        st.info(t("up_load_first"))
        return

    # Persistencia: ler valores salvos no state (sobrevive a navegacao)
    up = state.setdefault("upload_params", {
        "recoil": 3, "roi_size": "2 x 2 cm", "roi_pct": 40,
        "dpi": int(state.get("setup_data", {}).get("dpi", 72)), "unit": "cGy",
    })

    # ===== Controles de parametros =====
    st.markdown(f"**{t('up_params')}**")
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        recoil = st.selectbox(t("up_recoil"), [2, 3, 4, 5],
                              index=[2, 3, 4, 5].index(up["recoil"]),
                              format_func=lambda x: f"{x} mm", key="up_recoil")
    with cc2:
        roi_opts = ["2 x 2 cm", "2,5 x 2,5 cm"]
        roi_size = st.selectbox(t("up_roi_size"), roi_opts,
                                index=roi_opts.index(up["roi_size"]) if up["roi_size"] in roi_opts else 0,
                                key="up_roi_size")
    with cc3:
        dpi = st.number_input(t("up_dpi"), 25, 1200, value=int(up["dpi"]), key="up_dpi")
    with cc4:
        unit = st.radio(t("up_unit"), ["cGy", "Gy"], horizontal=True,
                        index=0 if up["unit"] == "cGy" else 1, key="up_unit")

    # Persistir escolhas IMEDIATAMENTE no state
    up.update({"recoil": recoil, "roi_size": roi_size, "dpi": int(dpi), "unit": unit})
    state["upload_params"] = up

    # Converter "2,5 x 2,5 cm" -> 2.5
    roi_size_cm = 2.5 if roi_size.startswith("2,5") else 2.0

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:14px 0'>",
                unsafe_allow_html=True)

    # ===== Motores =====
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
        from utils.image_bridge import bytes_to_array
        from utils.film_detection import detect_films, order_films_by_intensity, _to_gray
        from utils.field_detection import analyze_film_field, compute_roi
        from utils.film_overlay import draw_overview, draw_single_film
        from utils.calibration_engine import red_channel_mean_in_roi
    except Exception as e:
        st.error(f"Erro ao carregar os motores: {e}")
        return

    img = bytes_to_array(saved[0]["bytes"], saved[0]["name"])

    with st.spinner("..."):
        try:
            films, debug = detect_films(img)
            ordered = order_films_by_intensity(films)
        except Exception as e:
            st.error(f"Erro na deteccao: {e}")
            return

    if not ordered:
        st.warning(t("up_load_first"))
        return

    st.success(f"{len(ordered)} {t('up_n_detected')}")

    st.markdown(f"**{t('up_overview')}**")
    st.image(draw_overview(img, ordered), use_container_width=True)

    _lf = t("up_legend_film"); _lc = t("up_legend_field")
    _lr = t("up_legend_recoil"); _lroi = t("up_legend_roi")
    st.markdown(f"""
    <div style="display:flex;gap:18px;font-size:11px;color:{COLORS['text_sec']};margin:8px 0">
      <span><span style="color:{COLORS['green_light']}">&#9632;</span> {_lf}</span>
      <span><span style="color:{COLORS['blue_light']}">&#9632;</span> {_lc}</span>
      <span><span style="color:{COLORS['amber']}">&#9632;</span> {_lr}</span>
      <span><span style="color:{COLORS['red_light']}">&#9632;</span> {_lroi}</span>
    </div>""", unsafe_allow_html=True)

    # ===== Cada filme + dose =====
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:14px 0'>",
                unsafe_allow_html=True)
    st.markdown(f"**{t('up_individual')}**")

    gray = _to_gray(img)
    doses = state.setdefault("film_doses", {})
    red_means_store = {}
    roi_info_store = {}

    for f in ordered:
        minr, minc, maxr, maxc = f["bbox"]
        crop_gray = gray[minr:maxr, minc:maxc]
        fr = analyze_film_field(crop_gray, f["mask"])
        roi = compute_roi(crop_gray.shape, fr["field_bbox"],
                          edge_recoil_mm=float(recoil), dpi=int(dpi),
                          roi_size_cm=roi_size_cm)
        roi_info_store[f["order"]] = {
            "field_type": fr["field_type"], "roi_mode": roi.get("roi_mode", ""),
            "recoil_mm": recoil,
        }

        try:
            red_means_store[f["order"]] = red_channel_mean_in_roi(img, f["bbox"], roi["roi_bbox"])
        except Exception:
            pass

        col_img, col_info = st.columns([1, 2])
        with col_img:
            st.image(draw_single_film(img, f, fr, roi), use_container_width=True)
        with col_info:
            field_txt = (t("up_field_full") if fr["field_type"] == "full"
                         else t("up_field_smaller"))
            st.markdown(f"**{t('up_legend_film')} #{f['order']+1}** — {field_txt}")
            st.caption(f"{t('up_mean_int')}: {f['mean_intensity_gray']:.3f} · "
                       f"{t('up_legend_recoil')} {recoil} mm · ROI {roi.get('roi_mode','')}")
            key = f"dose_{f['order']}"
            doses[key] = st.number_input(
                f"{t('up_dose_of')} #{f['order']+1} ({unit})",
                min_value=0.0, value=float(doses.get(key, 0.0)),
                step=1.0 if unit == "cGy" else 0.1, key=f"w_{key}",
            )

    state["film_red_means"] = red_means_store
    state["film_roi_info"] = roi_info_store

    # ===== Selecao =====
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:14px 0'>",
                unsafe_allow_html=True)
    st.markdown(f"**{t('up_sel_curve')}**")

    modo = st.radio(t("up_sel_how"), [t("up_sel_all"), t("up_sel_group")], key="up_sel_mode")
    selected = []
    if modo == t("up_sel_all"):
        selected = [f["order"] for f in ordered]
        st.caption(f"{len(ordered)} - {t('up_sel_all_used')}")
    else:
        st.caption(t("up_sel_mark"))
        cols = st.columns(len(ordered))
        for col, f in zip(cols, ordered):
            with col:
                dl = doses.get(f"dose_{f['order']}", 0)
                if st.checkbox(f"#{f['order']+1} ({dl:.0f})", value=True, key=f"sel_{f['order']}"):
                    selected.append(f["order"])
        st.caption(f"{len(selected)}/{len(ordered)} {t('up_sel_count')}")

    # ===== Botoes Salvar e Continuar =====
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:14px 0'>",
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3, 1, 1])
    with c2:
        save_clicked = st.button(t("setup_save_draft"), use_container_width=True)
    with c3:
        cont_clicked = st.button(t("continue"), use_container_width=True, type="primary")

    if save_clicked or cont_clicked:
        if not selected:
            st.error(t("up_sel_one"))
        else:
            state["film_doses"] = doses
            state["film_unit"] = unit
            state["film_selection"] = selected
            state["done"]["upload"] = True
            _ov = draw_overview(img, ordered)
            try:
                from utils.films_gallery import make_films_gallery
                _gallery = make_films_gallery(img, ordered, doses, unit,
                                              lang=get_lang(), theme="light",
                                              roi_info=roi_info_store)
            except Exception:
                _gallery = None
            _save_upload(state, ordered, doses, unit, selected, recoil,
                         roi.get("roi_mode", ""), int(dpi), _ov, _gallery, roi_info_store)
            if save_clicked:
                st.success("Salvo! / Saved!")
            if cont_clicked:
                go("dashboard")


def _save_upload(state, ordered, doses, unit, selected, recoil, roi_mode, dpi,
                 overview_png=None, gallery_png=None, roi_info=None):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        films_info = []
        for f in ordered:
            ri = (roi_info or {}).get(f["order"], {})
            films_info.append({
                "order": f["order"],
                "intensity": f["mean_intensity_gray"],
                "dose": doses.get(f"dose_{f['order']}", 0.0),
                "selected": f["order"] in selected,
                "field_type": ri.get("field_type", ""),
                "roi_mode": ri.get("roi_mode", ""),
            })
        save_module(state, "upload", {
            "n_films": len(ordered),
            "unit": unit,
            "recoil_mm": recoil,
            "roi_mode": roi_mode,
            "dpi": dpi,
            "films": films_info,
            "n_selected": len(selected),
        })
        if overview_png is not None:
            state["films_overview_png"] = overview_png
        if gallery_png is not None:
            state["films_gallery_png"] = gallery_png
    except Exception:
        pass
