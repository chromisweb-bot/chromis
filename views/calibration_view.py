"""calibration_view.py — Curva de calibracao NOD x Dose com recomendacao."""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


def calibration_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_dosimetry')}</div>", unsafe_allow_html=True)

    # Precisa do upload feito
    red_means = state.get("film_red_means", {})
    doses_map = state.get("film_doses", {})
    unit = state.get("film_unit", "cGy")
    selection = state.get("film_selection", list(red_means.keys()))

    if not red_means or not doses_map:
        st.warning(t("cal_load_first"))
        if st.button(t("cal_go_upload")):
            go("upload")
        return

    # Montar listas alinhadas (so filmes selecionados)
    orders = sorted([o for o in red_means.keys() if o in selection])
    pv_list, dose_list = [], []
    for o in orders:
        pv_list.append(red_means[o])
        dose_list.append(doses_map.get(f"dose_{o}", 0.0))

    # Importar motor
    try:
        from utils.calibration_engine import (
            compute_nod_values, fit_all_models, recommend_model, MODEL_INFO,
        )
    except Exception as e:
        st.error(f"Erro ao carregar o motor de calibracao: {e}")
        return

    # Calcular NOD
    nods, zero_idx = compute_nod_values(pv_list, dose_list)

    # Caso nao haja filme de dose zero -> pedir background
    if nods is None:
        st.warning(t("cal_no_zero"))
        st.markdown("**Opcoes:**")
        st.markdown("- Volte ao Upload e digite dose 0 no filme nao irradiado, OU")
        st.markdown("- Faca o upload de um filme de background abaixo:")
        bg = st.file_uploader("Filme de background (dose 0)", type=["tif","tiff","png","jpg","jpeg"],
                              key="calib_bg")
        if bg is not None:
            st.info("Background recebido. (Integracao do background avulso na proxima etapa.)")
        return

    with st.expander(t("protocol_title")):
        st.markdown(t("protocol_items"))

    # ===== Selecao de pontos do ajuste (incluir/excluir) =====    # O NOD e calculado com TODOS os filmes (o PV0 do filme zero continua
    # valido); a exclusao remove apenas o PAR (NOD, dose) do ajuste.
    sug = None
    try:
        from utils.calibration_engine import suggest_outlier
        sug = suggest_outlier(nods, dose_list)
    except Exception:
        sug = None
    if sug is not None:
        st.warning(t("cal_outlier_sug").format(
            film=f"#{orders[sug['index']]+1}", dose=f"{sug['dose']:.0f}",
            res=f"{sug['residual']:+.0f}"))

    with st.expander(t("cal_point_selection"), expanded=(sug is not None)):
        st.caption(t("cal_point_selection_hint"))
        include = []
        ncols = 5
        cols = st.columns(ncols)
        for i, o in enumerate(orders):
            with cols[i % ncols]:
                mark = " ⚠" if (sug is not None and i == sug["index"]) else ""
                inc = st.checkbox(f"#{o+1} · {dose_list[i]:.0f}{mark}",
                                  value=True, key=f"cal_inc_{o}")
                include.append(inc)

    fit_nods = [n for n, k in zip(nods, include) if k]
    fit_doses = [d for d, k in zip(dose_list, include) if k]
    fit_orders = [o for o, k in zip(orders, include) if k]
    n_excl = len(orders) - len(fit_orders)
    if len(fit_nods) < 4:
        st.error(t("cal_too_few_points"))
        return
    if n_excl:
        st.info(t("cal_excluded_info").format(n=n_excl))

    # ===== Verificacao de qualidade dos pontos (sanidade) =====
    try:
        from utils.calibration_engine import check_calibration_quality
        qc_warns = check_calibration_quality(fit_doses, fit_nods, lang=get_lang())
        for wmsg in qc_warns:
            st.warning(f"⚠ {wmsg}")
    except Exception:
        pass

    # ===== Ajustar todos os modelos =====
    with st.spinner("Ajustando modelos..."):
        results = fit_all_models(fit_nods, fit_doses)

    if not results:
        st.error(t("cal_no_fit"))
        return

    rec = recommend_model(results, fit_doses, unit=unit)

    # ===== Recomendacao inteligente =====
    rec_model = rec["recommended"]
    st.markdown(f"""
    <div style="background:rgba(35,134,54,0.10);border:0.5px solid {COLORS['green']};
                border-radius:10px;padding:16px;margin-bottom:16px">
      <div style="font-size:14px;color:{COLORS['green_light']};font-weight:600;margin-bottom:8px">
        <i class="ti ti-bulb"></i> {t("cal_recommend")} {MODEL_INFO[rec_model]['nome']}</div>
      <div style="font-size:12px;color:{COLORS['text_sec']};font-family:monospace;margin-bottom:10px">
        {MODEL_INFO[rec_model]['formula']}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"**{t('cal_why')}**")
    for reason in rec["reasons"]:
        st.markdown(f"- {reason}")

    # ===== Escolha do modelo (pre-selecionado no recomendado) =====
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)

    model_names = [r["model"] for r in results]
    labels = [f"{MODEL_INFO[m]['nome']} (R²={next(r['r_squared'] for r in results if r['model']==m):.4f})"
              for m in model_names]
    default_idx = model_names.index(rec_model) if rec_model in model_names else 0

    col_sel, col_plot = st.columns([1, 1.6])
    with col_sel:
        st.markdown(f"**{t('cal_choose_model')}**")
        chosen_label = st.radio("modelo", labels, index=default_idx,
                                label_visibility="collapsed", key="calib_model")
        chosen_model = model_names[labels.index(chosen_label)]
        chosen_result = next(r for r in results if r["model"] == chosen_model)

        st.markdown(f"<div style='background:{COLORS['bg_card']};border:0.5px solid "
                    f"{COLORS['border_soft']};border-radius:8px;padding:12px;margin-top:10px'>"
                    f"<div style='font-size:11px;color:{COLORS['text_muted']}'>R² do ajuste</div>"
                    f"<div style='font-size:22px;color:{COLORS['green_light']};"
                    f"font-family:monospace'>{chosen_result['r_squared']:.4f}</div>"
                    f"<div style='font-size:11px;color:{COLORS['text_muted']};margin-top:6px'>RMSE</div>"
                    f"<div style='font-size:16px;color:{COLORS['amber']};"
                    f"font-family:monospace'>{chosen_result['rmse']:.2f} {unit}</div></div>",
                    unsafe_allow_html=True)

    with col_plot:
        graph_theme = st.radio(
            t("cal_graph_theme"),
            [t("cal_theme_dark"), t("cal_theme_light")],
            horizontal=True, key="calib_graph_theme",
        )
        theme_val = "dark" if graph_theme == t("cal_theme_dark") else "light"
        state["calib_graph_theme_val"] = theme_val
        try:
            from utils.curve_plot import make_calibration_plot
            png = make_calibration_plot(fit_nods, fit_doses, chosen_result["model_obj"],
                                        unit, fit_orders, theme=theme_val, lang=get_lang())
            st.image(png, use_container_width=True)
        except Exception as e:
            st.caption(f"(Grafico indisponivel: {e})")

    # ===== Tabela de pontos =====
    with st.expander(t("cal_see_points")):
        st.markdown("| Filme | Dose | PV vermelho | NOD | |")
        st.markdown("|---|---|---|---|---|")
        rows = ""
        for o, pv, dose, nod, inc in zip(orders, pv_list, dose_list, nods, include):
            tag = "" if inc else t("cal_excluded_tag")
            rows += f"| #{o+1} | {dose:.0f} {unit} | {pv:.1f} | {nod:.4f} | {tag} |\n"
        st.markdown(rows)

    # ===== Salvar =====
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"<div style='font-size:12px;color:{COLORS['green_light']};padding-top:8px'>"
                    f"<i class='ti ti-circle-check'></i> Curva pronta para o Mapa de Dose e o Relatorio</div>",
                    unsafe_allow_html=True)
    with c2:
        if st.button(t("cal_save"), use_container_width=True, type="primary"):
            state["done"]["calibration"] = True
            state["calibration_model"] = {
                "model_type": chosen_model,
                "r_squared": chosen_result["r_squared"],
                "rmse": chosen_result["rmse"],
            }
            # Gerar imagem da curva para o relatorio
            try:
                from utils.curve_plot import make_calibration_plot
                curve_png = make_calibration_plot(fit_nods, fit_doses,
                                                  chosen_result["model_obj"], unit, fit_orders,
                                                  theme=state.get("calib_graph_theme_val","dark"),
                                                  lang=get_lang())
                state["calibration_curve_png"] = curve_png
            except Exception:
                pass
            _save_calibration(state, chosen_model, chosen_result, rec_model,
                              fit_nods, fit_doses, fit_orders,
                              [p for p, k in zip(pv_list, include) if k],
                              unit, MODEL_INFO)
            notify_user_activity(state.get("user", "?"), "Calibracao concluida",
                                 f"Modelo {MODEL_INFO[chosen_model]['nome']}, "
                                 f"R2={chosen_result['r_squared']:.4f}")
            go("dashboard")


def _plot_calibration(nods, doses, result, unit, MODEL_INFO, orders):
    """Desenha o grafico NOD x Dose com os pontos e a curva ajustada."""
    import numpy as np
    try:
        from calibration import predict_dose
    except Exception:
        predict_dose = None

    # Gerar curva suave
    nod_arr = np.asarray(nods)
    nmin, nmax = float(nod_arr.min()), float(nod_arr.max())
    xs = np.linspace(nmin, max(nmax, nmin + 1e-3), 100)
    ys = None
    if predict_dose is not None:
        try:
            ys = predict_dose(result["model_obj"], xs)
        except Exception:
            ys = None

    # SVG simples do grafico
    W, H = 380, 280
    pad = 42
    dmax = max(doses) if max(doses) > 0 else 1
    def px(n): return pad + (n - nmin) / (nmax - nmin + 1e-9) * (W - 2*pad)
    def py(d): return H - pad - (d / dmax) * (H - 2*pad)

    pts_curve = ""
    if ys is not None:
        pts_curve = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys)
                             if np.isfinite(y))

    pts_data = ""
    for n, d, o in zip(nods, doses, orders):
        cx, cy = px(n), py(d)
        pts_data += (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{COLORS["green_light"]}" '
                     f'stroke="{COLORS["bg_card"]}" stroke-width="1.5"/>')
        pts_data += (f'<text x="{cx+6:.1f}" y="{cy-6:.1f}" fill="{COLORS["text_muted"]}" '
                     f'font-size="8">#{o+1}</text>')

    svg = f'''<svg viewBox="0 0 {W} {H}" style="width:100%;background:{COLORS['bg_card']};
              border:0.5px solid {COLORS['border_soft']};border-radius:10px">
      <line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="{COLORS['border']}" stroke-width="1"/>
      <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="{COLORS['border']}" stroke-width="1"/>
      <text x="{W/2}" y="{H-8}" fill="{COLORS['text_muted']}" font-size="10" text-anchor="middle">NOD</text>
      <text x="14" y="{H/2}" fill="{COLORS['text_muted']}" font-size="10" text-anchor="middle"
            transform="rotate(-90 14 {H/2})">Dose ({unit})</text>
      {'<polyline points="' + pts_curve + f'" fill="none" stroke="{COLORS["blue_light"]}" stroke-width="2"/>' if pts_curve else ''}
      {pts_data}
    </svg>'''
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:10px;color:{COLORS['text_sec']};margin-top:4px'>"
                f"<span style='color:{COLORS['green_light']}'>&#9679;</span> Pontos medidos &nbsp;"
                f"<span style='color:{COLORS['blue_light']}'>&#9472;</span> Curva ajustada</div>",
                unsafe_allow_html=True)


def _save_calibration(state, model_type, result, recommended, nods, doses,
                      orders, pv_list, unit, MODEL_INFO):
    """Salva a calibracao no estudo central."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        points = []
        for o, pv, d, nod in zip(orders, pv_list, doses, nods):
            points.append({"film": o + 1, "dose": float(d),
                           "pv_red": float(pv), "nod": float(nod)})
        save_module(state, "calibration", {
            "model_type": model_type,
            "model_name": MODEL_INFO[model_type]["nome"],
            "formula": MODEL_INFO[model_type]["formula"],
            "recommended": recommended,
            "recommended_name": MODEL_INFO[recommended]["nome"],
            "r_squared": result["r_squared"],
            "rmse": result["rmse"],
            "unit": unit,
            "n_points": len(points),
            "points": points,
        })
    except Exception:
        pass
