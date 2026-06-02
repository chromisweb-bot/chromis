"""report_view.py — Geracao do relatorio PDF (parcial ou total, PT/EN)."""
import os
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_report_generated, notify_user_activity


def report_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_output')}</div>", unsafe_allow_html=True)

    # Carregar o estudo
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import init_study, completed_modules
        from utils.report_generator import generate_report
    except Exception as e:
        st.error(f"Erro ao carregar o gerador de relatorio: {e}")
        return

    study = init_study(state)
    done = completed_modules(state)

    # Mapa de modulos disponiveis para o relatorio (os que geram secao)
    reportable = {
        "setup": t("mod_setup"),
        "upload": t("mod_upload"),
        "calibration": t("mod_calibration"),
    }
    available = [m for m in reportable if m in done]

    if not available:
        st.warning(t("rep_none_done"))
        return

    col_a, col_b = st.columns([1.1, 1])

    with col_a:
        st.markdown(f"**{t('rep_lang')}**")
        lang_choice = st.radio("lang", ["Portugues (PT-BR)", "English (EN-US)"],
                               label_visibility="collapsed", horizontal=True, key="rep_lang")
        report_lang = "pt" if lang_choice.startswith("Port") else "en"

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(f"**{t('rep_type')}**")
        full = st.checkbox(t("rep_full"),
                           value=True, key="rep_full")

        selected_modules = None
        if full:
            selected_modules = available
            st.caption(f"Incluindo: {', '.join(reportable[m] for m in available)}")
        else:
            st.caption(t("rep_choose_mods"))
            chosen = []
            for m in available:
                if st.checkbox(reportable[m], value=True, key=f"rep_mod_{m}"):
                    chosen.append(m)
            selected_modules = chosen

    with col_b:
        st.markdown(f"**{t('rep_available')}**")
        for m in reportable:
            if m in available:
                st.markdown(f"<div style='font-size:12px;color:{COLORS['green_light']};padding:3px 0'>"
                            f"<i class='ti ti-circle-check'></i> {reportable[m]}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='font-size:12px;color:{COLORS['text_dim']};padding:3px 0'>"
                            f"<i class='ti ti-circle'></i> {reportable[m]} (pendente)</div>",
                            unsafe_allow_html=True)

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)

    if st.button(t("rep_generate"), use_container_width=True, type="primary"):
        if not selected_modules:
            st.error(t("rep_select_one"))
            return
        with st.spinner(t("rep_generating")):
            logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_full.png")
            # Regenerar a curva no idioma do relatorio (mantendo o tema escolhido)
            curve_for_report = state.get("calibration_curve_png")
            calib = study.get("calibration")
            if calib and calib.get("points"):
                try:
                    from utils.curve_plot import make_calibration_plot
                    from calibration import CalibrationData, fit_calibration
                    pts = calib["points"]
                    nods_r = [p["nod"] for p in pts]
                    doses_r = [p["dose"] for p in pts]
                    orders_r = [p["film"]-1 for p in pts]
                    mt = calib.get("model_type", "devic")
                    mobj = fit_calibration(CalibrationData(nod=__import__("numpy").array(nods_r),
                                                           dose=__import__("numpy").array(doses_r)),
                                           model_type=mt)
                    curve_for_report = make_calibration_plot(
                        nods_r, doses_r, mobj, calib.get("unit","cGy"), orders_r,
                        theme=state.get("calib_graph_theme_val","dark"), lang=report_lang)
                except Exception:
                    pass
            # Regenerar a galeria de filmes no idioma do relatorio
            gallery_for_report = state.get("films_gallery_png")
            up_data = study.get("upload")
            saved_films = state.get("uploaded_films", [])
            if up_data and saved_films:
                try:
                    from utils.image_bridge import bytes_to_array
                    from utils.film_detection import detect_films, order_films_by_intensity
                    from utils.films_gallery import make_films_gallery
                    _img = bytes_to_array(saved_films[0]["bytes"], saved_films[0]["name"])
                    _films, _ = detect_films(_img)
                    _ordered = order_films_by_intensity(_films)
                    gallery_for_report = make_films_gallery(
                        _img, _ordered, state.get("film_doses", {}),
                        up_data.get("unit", "cGy"), lang=report_lang, theme="light",
                        roi_info=state.get("film_roi_info"))
                except Exception as e:
                    st.warning(f"Aviso: nao foi possivel regenerar a galeria de filmes ({e}). "
                               f"Usando a versao salva.")

            try:
                pdf_bytes = generate_report(study, lang=report_lang,
                                            selected_modules=selected_modules,
                                            logo_path=logo_path,
                                            films_image=gallery_for_report or state.get("films_overview_png"),
                                            curve_image=curve_for_report)
            except Exception as e:
                st.error(f"Erro ao gerar o PDF: {e}")
                return

        st.success(t("rep_generated"))
        fname = f"chromis_relatorio_{report_lang}.pdf"
        st.download_button(t("rep_download"), data=pdf_bytes, file_name=fname,
                           mime="application/pdf", use_container_width=True)

        # Notificar admin com o relatorio anexado
        try:
            notify_report_generated(state.get("user", "?"), pdf_bytes, fname,
                                     summary=f"Modulos: {', '.join(selected_modules)}")
        except Exception:
            pass
        notify_user_activity(state.get("user", "?"), "Relatorio gerado",
                             f"Idioma: {report_lang}, modulos: {len(selected_modules)}")
