"""dosemap_view.py - Mapa de dose 2D (aplica a curva de calibracao no filme)."""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


def dosemap_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_dosimetry')}</div>", unsafe_allow_html=True)

    # Precisa de calibracao
    study = state.get("study", {})
    cal = study.get("calibration")
    if not cal or not cal.get("points"):
        st.warning(t("dm_need_calib"))
        if st.button(t("cal_go_upload")):
            go("calibration")
        return

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
        from utils.image_bridge import bytes_to_array
        from utils.film_detection import detect_films, order_films_by_intensity
        from utils.dose_map_engine import compute_dose_map, render_dose_map_png
        from calibration import CalibrationData, fit_calibration
        import numpy as np
    except Exception as e:
        st.error(f"Erro ao carregar motores: {e}")
        return

    # Reconstruir o modelo de calibracao
    pts = cal["points"]
    nods = np.array([p["nod"] for p in pts])
    doses = np.array([p["dose"] for p in pts])
    model_type = cal.get("model_type", "devic")
    unit = cal.get("unit", "cGy")
    try:
        model_obj = fit_calibration(CalibrationData(nod=nods, dose=doses), model_type=model_type)
    except Exception as e:
        st.error(f"Erro ao reconstruir a curva: {e}")
        return

    # PV do filme zero (background)
    pv_zero = None
    for p in pts:
        if p["dose"] == 0:
            pv_zero = p["pv_red"]
            break
    if pv_zero is None:
        st.warning(t("dm_need_zero"))
        return

    # ===== Escolha da fonte do filme de medida =====
    st.markdown(f"**{t('dm_source')}**")
    source = st.radio(
        t("dm_source_q"),
        [t("dm_source_upload"), t("dm_source_calib")],
        key="dm_source",
    )

    measure_img = None  # imagem completa onde detectar o filme

    if source == t("dm_source_upload"):
        st.caption(t("dm_upload_hint"))
        up = st.file_uploader(t("dm_upload"), type=["tif", "tiff", "png", "jpg", "jpeg"],
                              key="dm_upload_widget")
        if up is not None:
            measure_img = bytes_to_array(up.getvalue(), up.name)
    else:
        saved_films = state.get("uploaded_films", [])
        if not saved_films:
            st.warning(t("dm_no_calib_films"))
            return
        measure_img = bytes_to_array(saved_films[0]["bytes"], saved_films[0]["name"])

    if measure_img is None:
        st.info(t("dm_waiting_film"))
        return

    # Detectar filmes na imagem de medida
    films, _ = detect_films(measure_img)
    ordered = order_films_by_intensity(films)
    if not ordered:
        st.warning(t("up_load_first"))
        return

    # Se houver mais de um filme, deixa escolher qual analisar
    if len(ordered) > 1:
        st.markdown(f"**{t('dm_select_film')}**")
        labels = [f"#{f['order']+1}" for f in ordered]
        sel = st.selectbox(t("dm_film"), labels, key="dm_film_sel")
        film = ordered[labels.index(sel)]
    else:
        film = ordered[0]
        sel = "#1"

    # ===== Opcoes de exibicao =====
    col1, col2 = st.columns(2)
    with col1:
        display_mode = st.radio(t("dm_display"),
                                [t("dm_percent"), t("dm_absolute")],
                                key="dm_display")
    with col2:
        theme_choice = st.radio(t("cal_graph_theme"),
                                [t("cal_theme_dark"), t("cal_theme_light")],
                                horizontal=True, key="dm_theme")
    theme_val = "dark" if theme_choice == t("cal_theme_dark") else "light"
    is_percent = display_mode == t("dm_percent")

    with st.spinner("..."):
        minr, minc, maxr, maxc = film["bbox"]
        crop = measure_img[minr:maxr, minc:maxc]
        result = compute_dose_map(crop, pv_zero, model_obj,
                                  normalize="max" if is_percent else None)
        if is_percent:
            png = render_dose_map_png(result["dose_map_pct"], unit, get_lang(),
                                      theme_val, percent=True)
        else:
            png = render_dose_map_png(result["dose_map"], unit, get_lang(), theme_val)

    st.image(png, use_container_width=True)

    # Metricas
    c1, c2, c3 = st.columns(3)
    if is_percent:
        c1.metric(t("dm_dose_min"), f"{result['pct_min']:.0f}%")
        c2.metric(t("dm_dose_mean"), f"{result['pct_mean']:.0f}%")
        c3.metric(t("dm_dose_max"), f"{result['pct_max']:.0f}%")
        st.caption(f"{t('dm_ref')}: {result['ref_dose']:.0f} {unit} (P99)")
    else:
        c1.metric(t("dm_dose_min"), f"{result['dose_min']:.0f} {unit}")
        c2.metric(t("dm_dose_mean"), f"{result['dose_mean']:.0f} {unit}")
        c3.metric(t("dm_dose_max"), f"{result['dose_max']:.0f} {unit}")

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    cc1, cc2 = st.columns([3, 1])
    with cc2:
        if st.button(t("cal_save"), use_container_width=True, type="primary"):
            state["done"]["dosemap"] = True
            state["dosemap_png"] = png
            state["dosemap_is_percent"] = is_percent
            _save_dosemap(state, sel, result, unit, is_percent)
            notify_user_activity(state.get("user", "?"), "Mapa de dose gerado",
                                 f"Filme {sel}")
            go("dashboard")


def _save_dosemap(state, film_label, result, unit, is_percent):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        data = {"film": film_label, "unit": unit, "is_percent": is_percent,
                "dose_min": result["dose_min"], "dose_max": result["dose_max"],
                "dose_mean": result["dose_mean"]}
        if is_percent:
            data.update({"ref_dose": result.get("ref_dose"),
                         "pct_min": result.get("pct_min"),
                         "pct_mean": result.get("pct_mean"),
                         "pct_max": result.get("pct_max")})
        save_module(state, "dosemap", data)
    except Exception:
        pass
