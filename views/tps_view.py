"""tps_view.py — Tela de Planejamento do TPS (Monaco)."""
import streamlit as st
from i18n import t
from theme import COLORS
from auth import notify_user_activity


def tps_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"Etapa 2 · {t('group_config')} · Monaco</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**{t('mod_tps')}**")
        st.caption("Exporte do Monaco e carregue aqui")
        st.file_uploader("RT Dose (.dcm)", type=["dcm"], key="tps_rtdose")
        st.file_uploader("Isodoses — RT Structure (.dcm)", type=["dcm"], key="tps_rtstruct")
        st.file_uploader("Pontos de dose (.csv) — opcional", type=["csv", "txt"], key="tps_points")

    with col_b:
        st.markdown("**Pré-visualização do plano**")
        if st.session_state.get("tps_rtdose"):
            st.info("Pré-visualização será exibida após a integração do parser DICOM.")
        else:
            st.markdown(f"<div style='background:{COLORS['bg_surface']};border-radius:8px;"
                        f"padding:40px;text-align:center;color:{COLORS['text_muted']};font-size:12px'>"
                        f"Carregue o RT Dose para visualizar</div>", unsafe_allow_html=True)

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:18px 0'>",
                unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button(t("continue"), use_container_width=True, type="primary"):
            state["done"]["tps"] = True
            notify_user_activity(state.get("user", "?"), "Planejamento TPS carregado")
            go("dashboard")
