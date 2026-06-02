"""dosemap_view.py - Mapa de dose 2D (aplica a curva de calibracao no filme)."""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


def dosemap_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_dosimetry')}</div>", unsafe_allow_html=True)

    # Precisa de calibracao e filmes
    calib = state.get("calibration_model")
    saved_films = state.get("uploaded_films", [])
    red_means = state.get("film_red_means", {})

    if not calib or not saved_films:
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

    # Reconstruir o modelo de calibracao a partir do estudo
    study = state.get("study", {})
    cal = study.get("calibration")
    if not cal or not cal.get("points"):
        st.warning(t("dm_need_calib"))
        return

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

    # PV do filme zero
    pv_zero = None
    for p in pts:
        if p["dose"] == 0:
            pv_zero = p["pv_red"]
            break
    if pv_zero is None:
        st.warning(t("dm_need_zero"))
        return

    # Detectar filmes
    img = bytes_to_array(saved_films[0]["bytes"], saved_films[0]["name"])
    films, _ = detect_films(img)
    ordered = order_films_by_intensity(films)

    st.markdown(f"**{t('dm_select_film')}**")
    labels = [f"#{f['order']+1}" for f in ordered]
    sel = st.selectbox(t("dm_film"), labels, key="dm_film_sel")
    fidx = labels.index(sel)
    film = ordered[fidx]

    theme_choice = st.radio(t("cal_graph_theme"),
                            [t("cal_theme_dark"), t("cal_theme_light")],
                            horizontal=True, key="dm_theme")
    theme_val = "dark" if theme_choice == t("cal_theme_dark") else "light"

    with st.spinner("..."):
        minr, minc, maxr, maxc = film["bbox"]
        crop = img[minr:maxr, minc:maxc]
        result = compute_dose_map(crop, pv_zero, model_obj)
        png = render_dose_map_png(result["dose_map"], unit, get_lang(), theme_val)

    st.image(png, use_container_width=True)

    c1, c2, c3 = st.columns(3)
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
            _save_dosemap(state, sel, result, unit)
            notify_user_activity(state.get("user", "?"), "Mapa de dose gerado",
                                 f"Filme {sel}, dose media {result['dose_mean']:.0f} {unit}")
            go("dashboard")


def _save_dosemap(state, film_label, result, unit):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        save_module(state, "dosemap", {
            "film": film_label, "unit": unit,
            "dose_min": result["dose_min"], "dose_max": result["dose_max"],
            "dose_mean": result["dose_mean"],
        })
    except Exception:
        pass
