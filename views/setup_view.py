"""setup_view.py — Tela de Setup do Estudo (com persistência)."""

import streamlit as st
from i18n import t
from theme import COLORS
from auth import notify_user_activity


def setup_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"Etapa 1 · {t('group_config')}</div>", unsafe_allow_html=True)

    # "Gaveta" persistente — guarda os valores entre navegacoes.
    d = state.setdefault("setup_data", {
        "study_type": t("setup_clinical"),
        "institution": "",
        "responsible": state.get("user", ""),
        "machine": "",
        "manufacturer": "",
        "energy": "6 MV",
        "field": "5 x 5",
        "film_model": "EBT3",
        "film_lot": "",
        "scanner_model": "",
        "dpi": 72,
        "channel": t("setup_channel_red"),
    })

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"**{t('setup_study_type')}**")
        study_options = [t("setup_clinical"), t("setup_academic")]
        study_idx = study_options.index(d["study_type"]) if d["study_type"] in study_options else 0
        d["study_type"] = st.radio(
            t("setup_study_type"), study_options, index=study_idx,
            horizontal=True, label_visibility="collapsed", key="w_study_type",
        )
        inst_label = t("setup_institution") if d["study_type"] == t("setup_clinical") else t("setup_university")
        d["institution"] = st.text_input(inst_label, value=d["institution"], key="w_institution")
        d["responsible"] = st.text_input(t("setup_responsible"), value=d["responsible"], key="w_responsible")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        st.markdown(f"**{t('setup_machine_sec')}**")
        c1, c2 = st.columns(2)
        d["machine"] = c1.text_input(t("setup_machine"), value=d["machine"], key="w_machine")
        d["manufacturer"] = c2.text_input(t("setup_manufacturer"), value=d["manufacturer"], key="w_manufacturer")
        c3, c4 = st.columns(2)
        d["energy"] = c3.text_input(t("setup_energy"), value=d["energy"], key="w_energy")
        d["field"] = c4.text_input(t("setup_field"), value=d["field"], key="w_field")

    with col_b:
        st.markdown(f"**{t('setup_film_sec')}**")
        c5, c6 = st.columns(2)
        film_opts = ["EBT3", "EBT4"]
        film_idx = film_opts.index(d["film_model"]) if d["film_model"] in film_opts else 0
        d["film_model"] = c5.selectbox(t("setup_film_model"), film_opts, index=film_idx, key="w_film_model")
        d["film_lot"] = c6.text_input(t("setup_film_lot"), value=d["film_lot"], key="w_film_lot")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        st.markdown(f"**{t('setup_scanner_sec')}**")
        c7, c8 = st.columns(2)
        d["scanner_model"] = c7.text_input(t("setup_scanner_model"), value=d["scanner_model"], key="w_scanner_model")
        d["dpi"] = c8.number_input(t("setup_dpi"), min_value=25, max_value=1200,
                                   value=int(d["dpi"]), key="w_dpi")
        chan_opts = [t("setup_channel_red"), t("setup_channel_green"), t("setup_channel_blue")]
        chan_idx = chan_opts.index(d["channel"]) if d["channel"] in chan_opts else 0
        d["channel"] = st.selectbox(t("setup_channel"), chan_opts, index=chan_idx, key="w_channel")

        st.markdown(f"""
        <div style="background:rgba(35,134,54,0.08);border:0.5px solid {COLORS['green']};
                    border-radius:9px;padding:11px;margin-top:14px;font-size:11px;color:{COLORS['green_soft']}">
          <i class="ti ti-info-circle" style="margin-right:6px"></i>{t('setup_report_note')}
        </div>""", unsafe_allow_html=True)

    if state["done"].get("setup"):
        st.markdown(f"<div style='font-size:11px;color:{COLORS['green_light']};margin-top:8px'>"
                    f"<i class='ti ti-circle-check'></i> Setup salvo - os dados foram preservados.</div>",
                    unsafe_allow_html=True)

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:18px 0'>",
                unsafe_allow_html=True)

    cc1, cc2, cc3 = st.columns([3, 1, 1])
    with cc2:
        if st.button(t("setup_save_draft"), use_container_width=True):
            state["setup_data"] = d
            _save_setup(state, d)
            st.success("Rascunho salvo.")
    with cc3:
        if st.button(t("setup_save_continue"), use_container_width=True, type="primary"):
            state["setup_data"] = d
            state["done"]["setup"] = True
            _save_setup(state, d)
            notify_user_activity(
                state.get("user", "?"),
                "Setup concluido",
                f"{d['study_type']} - {d['institution']}",
            )
            go("dashboard")


def _save_setup(state, d):
    """Salva os dados do setup no estudo central (para o relatorio)."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        save_module(state, "setup", dict(d))
    except Exception:
        pass
