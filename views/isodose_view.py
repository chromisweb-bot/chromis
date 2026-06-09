"""isodose_view.py - Visualizacao de curvas de isodose do filme.

Reaproveita o mapa de dose absoluto ja reconstruido no modulo Mapa de Dose
(salvo em state["dosemap_array"]). Sobre esse mapa, desenha as curvas de
isodose nos niveis escolhidos pelo usuario, com cores clinicas, estilo de
linha (continuo/tracejado) e paleta de cores do fundo selecionaveis.
"""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


# Paletas de cores oferecidas para o fundo (heatmap).
_COLORMAPS = ["jet", "turbo", "viridis", "inferno", "plasma", "magma", "hot", "rainbow"]


def isodose_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_dosimetry')}</div>", unsafe_allow_html=True)

    # Depende do mapa de dose
    dose_map = state.get("dosemap_array")
    if dose_map is None:
        st.warning(t("iso_need_dosemap"))
        if st.button(t("iso_go_dosemap")):
            go("dosemap")
        return

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from isodose_engine import (
            render_isodose_png, isodose_summary, DEFAULT_CLINICAL_LEVELS,
            LEVELS_10_TO_150, resolve_isodose_values,
        )
        import numpy as np
    except Exception as e:
        st.error(f"Erro ao carregar o motor de isodose: {e}")
        return

    unit = state.get("dosemap_unit", "cGy")

    # ===== Base dos niveis =====
    st.markdown(f"**{t('iso_basis')}**")
    basis_choice = st.radio(
        t("iso_basis_q"),
        [t("iso_basis_rx"), t("iso_basis_max"), t("iso_basis_abs")],
        key="iso_basis",
    )
    if basis_choice == t("iso_basis_rx"):
        basis = "prescription"
    elif basis_choice == t("iso_basis_max"):
        basis = "max"
    else:
        basis = "absolute"

    prescription_dose = None
    if basis == "prescription":
        prescription_dose = st.number_input(
            f"{t('iso_rx_dose')} ({unit})", min_value=0.0, value=float(
                round(float(np.nanpercentile(dose_map, 99)))),
            step=1.0, key="iso_rx",
        )
        if not prescription_dose or prescription_dose <= 0:
            st.info(t("iso_need_rx"))
            return

    # ===== Niveis de isodose =====
    if basis == "absolute":
        default_levels_str = ", ".join(str(int(round(np.nanpercentile(dose_map, p))))
                                       for p in [30, 50, 75, 90, 100])
        help_txt = t("iso_levels_abs_hint").format(unit=unit)
    else:
        default_levels_str = ", ".join(str(x) for x in DEFAULT_CLINICAL_LEVELS)
        help_txt = t("iso_levels_pct_hint")

    # Presets rapidos (so para modos percentuais)
    if basis in ("prescription", "max"):
        st.caption(t("iso_presets"))
        pc1, pc2, pc3 = st.columns(3)
        if pc1.button(t("iso_preset_clinical"), use_container_width=True, key="iso_p1"):
            st.session_state["iso_levels"] = ", ".join(str(x) for x in DEFAULT_CLINICAL_LEVELS)
        if pc2.button("10 → 150", use_container_width=True, key="iso_p2"):
            st.session_state["iso_levels"] = ", ".join(str(x) for x in LEVELS_10_TO_150)
        if pc3.button(t("iso_preset_main"), use_container_width=True, key="iso_p3"):
            st.session_state["iso_levels"] = "50, 100"

    levels_str = st.text_input(t("iso_levels"), value=default_levels_str,
                               help=help_txt, key="iso_levels")
    try:
        levels = [float(x.strip()) for x in levels_str.split(",") if x.strip()]
    except Exception:
        st.error(t("iso_levels_err"))
        return
    if not levels:
        st.info(t("iso_levels_empty"))
        return

    # ===== Estilo e aparencia =====
    col1, col2, col3 = st.columns(3)
    with col1:
        line_choice = st.radio(t("iso_linestyle"),
                               [t("iso_solid"), t("iso_dashed")],
                               key="iso_line")
        linestyle = "solid" if line_choice == t("iso_solid") else "dashed"
    with col2:
        cmap = st.selectbox(t("iso_colormap"), _COLORMAPS, index=0, key="iso_cmap")
    with col3:
        theme_choice = st.radio(t("cal_graph_theme"),
                                [t("cal_theme_dark"), t("cal_theme_light")],
                                key="iso_theme")
        theme_val = "dark" if theme_choice == t("cal_theme_dark") else "light"

    show_bg = st.checkbox(t("iso_show_bg"), value=True, key="iso_show_bg")
    label_curves = st.checkbox(t("tps_iso_label_pct"), value=False, key="iso_label_pct")

    # Suavizacao para limpar curvas ruidosas (mapas de grade grossa interpolada).
    smooth = st.slider(t("iso_smooth"), min_value=0.0, max_value=3.0,
                       value=0.0, step=0.5, key="iso_smooth",
                       help=t("iso_smooth_hint"))

    # ===== Render =====
    # Verifica se ha pelo menos um nivel dentro da faixa de dose do mapa
    try:
        pairs = resolve_isodose_values(dose_map, levels, basis, prescription_dose)
    except Exception as e:
        st.error(str(e))
        return
    if not pairs:
        st.warning(t("iso_no_levels_in_range"))
        return

    with st.spinner("..."):
        png = render_isodose_png(
            dose_map, levels, basis=basis, prescription_dose=prescription_dose,
            level_pcts=levels if basis in ("prescription", "max") else None,
            unit=unit, lang=get_lang(), theme=theme_val,
            linestyle=linestyle, colormap=cmap, show_background=show_bg,
            smooth_sigma=smooth, label_on_curves=label_curves,
        )

    st.image(png, use_container_width=True)

    # ===== Resumo de areas por nivel =====
    res_mm = state.get("upload_params", {}).get("res_mm")
    summ = isodose_summary(dose_map, levels, basis=basis,
                           prescription_dose=prescription_dose, res_mm=res_mm)
    if summ:
        st.markdown(f"**{t('iso_summary')}**")
        for s in summ:
            if s["area_cm2"] is not None:
                st.caption(f"{s['label']} ({s['dose_value']:.0f} {unit}): "
                           f"{s['area_cm2']:.2f} cm²")
            else:
                st.caption(f"{s['label']} ({s['dose_value']:.0f} {unit}): "
                           f"{s['n_pixels']} px")

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    cc1, cc2 = st.columns([3, 1])
    with cc2:
        if st.button(t("cal_save"), use_container_width=True, type="primary"):
            state["done"]["isodose"] = True
            state["isodose_png"] = png
            _save_isodose(state, levels, basis, prescription_dose, unit, summ)
            notify_user_activity(state.get("user", "?"), "Isodose gerada", "")
            go("dashboard")


def _save_isodose(state, levels, basis, prescription_dose, unit, summ):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        data = {
            "levels": levels,
            "basis": basis,
            "prescription_dose": prescription_dose,
            "unit": unit,
            "areas": [{"label": s["label"], "dose_value": s["dose_value"],
                       "area_cm2": s["area_cm2"]} for s in summ],
        }
        save_module(state, "isodose", data)
    except Exception:
        pass
