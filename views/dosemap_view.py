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
    known_dose = None   # dose irradiada conhecida (opcional, p/ upload)
    known_unit = "cGy"

    if source == t("dm_source_upload"):
        st.caption(t("dm_upload_hint"))
        up = st.file_uploader(t("dm_upload"), type=["tif", "tiff", "png", "jpg", "jpeg"],
                              key="dm_upload_widget")
        if up is not None:
            measure_img = bytes_to_array(up.getvalue(), up.name)

        # Dose com que o filme foi irradiado (importante para validacao)
        cda, cdb = st.columns([2, 1])
        with cda:
            known_dose = st.number_input(t("dm_known_dose"), min_value=0.0,
                                         value=0.0, step=1.0, key="dm_known_dose_val")
        with cdb:
            known_unit = st.radio(t("up_unit"), ["cGy", "Gy"], horizontal=True,
                                  key="dm_known_unit")
        st.caption(t("dm_known_dose_hint"))
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

    # Fonte do background (PV0). Se o filme de medida foi escaneado em condicoes
    # diferentes da calibracao, usar uma regiao NAO irradiada do proprio filme
    # como referencia reduz o erro sistematico (boa pratica da literatura).
    bg_mode = st.radio(t("dm_bg_source"),
                       [t("dm_bg_calib"), t("dm_bg_film")],
                       key="dm_bg_source")
    use_film_bg = bg_mode == t("dm_bg_film")

    with st.spinner("..."):
        import numpy as np
        minr, minc, maxr, maxc = film["bbox"]
        crop = measure_img[minr:maxr, minc:maxc]

        pv_zero_use = pv_zero
        if use_film_bg:
            # Estimar PV0 dos cantos do filme (regioes tipicamente nao irradiadas).
            # Usa o canal vermelho; pega o valor mais CLARO (maior PV = menor dose).
            from utils.dose_map_engine import _red_channel
            red = _red_channel(crop)
            h, w = red.shape
            cs = max(4, int(min(h, w) * 0.12))  # tamanho do canto
            corners = [red[:cs, :cs], red[:cs, -cs:], red[-cs:, :cs], red[-cs:, -cs:]]
            corner_meds = [float(np.median(c)) for c in corners]
            # o canto menos irradiado = maior PV (filme mais claro)
            pv_zero_use = max(corner_meds)

        result = compute_dose_map(crop, pv_zero_use, model_obj,
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

    # Comparacao com a dose irradiada conhecida (se informada no upload)
    known_cgy = None
    if known_dose and known_dose > 0:
        known_cgy = known_dose * 100.0 if known_unit == "Gy" else known_dose
        import numpy as np
        from scipy.ndimage import median_filter
        dm_abs = result["dose_map"]
        # Medir no PLATO do campo irradiado (regiao de dose plena).
        # Boas praticas (literatura): medir em AREA, nao pixel; suavizar ruido.
        # 1) suavizar o mapa com mediana (reduz ruido de scanner)
        dm_smooth = median_filter(dm_abs, size=5)
        # 2) identificar o plato: pixels >= percentil 95 (regiao de dose plena)
        valid = dm_smooth[np.isfinite(dm_smooth)]
        if valid.size:
            thr = np.nanpercentile(dm_smooth, 95)
            # 3) tomar a regiao de dose plena e medir a MEDIANA (robusta a outliers)
            plateau = dm_smooth[dm_smooth >= thr]
            measured = float(np.nanmedian(plateau)) if plateau.size else float(np.nanmedian(dm_smooth))
        else:
            measured = 0.0
        diff_pct = (measured - known_cgy) / known_cgy * 100.0 if known_cgy else 0.0
        st.markdown(f"**{t('dm_validation')}**")
        v1, v2, v3 = st.columns(3)
        v1.metric(t("dm_irradiated"), f"{known_cgy:.0f} cGy")
        v2.metric(t("dm_measured_center"), f"{measured:.0f} cGy")
        v3.metric(t("dm_difference"), f"{diff_pct:+.1f}%")
        st.caption(t("dm_diff_hint"))
        # Aviso interpretativo conforme a magnitude do erro
        ad = abs(diff_pct)
        if ad <= 3:
            st.success(t("dm_diff_great"))
        elif ad <= 5:
            st.info(t("dm_diff_ok"))
        else:
            st.warning(t("dm_diff_check"))
        central = measured

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    cc1, cc2 = st.columns([3, 1])
    with cc2:
        if st.button(t("cal_save"), use_container_width=True, type="primary"):
            state["done"]["dosemap"] = True
            state["dosemap_png"] = png
            state["dosemap_is_percent"] = is_percent
            _save_dosemap(state, sel, result, unit, is_percent, known_cgy)
            notify_user_activity(state.get("user", "?"), "Mapa de dose gerado",
                                 f"Filme {sel}")
            go("dashboard")


def _save_dosemap(state, film_label, result, unit, is_percent, known_cgy=None):
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
        if known_cgy:
            data["known_dose_cgy"] = known_cgy
        save_module(state, "dosemap", data)
    except Exception:
        pass
