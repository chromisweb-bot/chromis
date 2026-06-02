"""symmetry_view.py — Tela do módulo (interface pronta; cálculo em integração)."""
import streamlit as st
from i18n import t
from theme import COLORS
from auth import notify_user_activity


def symmetry_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"QA · {t('group_qa')}</div>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:rgba(210,153,34,0.08);border:0.5px solid {COLORS['amber']};
                border-radius:9px;padding:13px;margin-bottom:16px;font-size:12px;color:{COLORS['amber_light']}">
      <i class="ti ti-tool" style="margin-right:6px"></i>{t('wip_msg')}
    </div>""", unsafe_allow_html=True)

    col_main, col_side = st.columns([2, 1])
    with col_main:
        st.markdown(f"<div style='background:{COLORS['bg_card']};border:0.5px solid {COLORS['border_soft']};"
                    f"border-radius:10px;padding:14px;min-height:300px;display:flex;align-items:center;"
                    f"justify-content:center;color:{COLORS['text_muted']};font-size:13px'>"
                    f"Área de visualização — {t('mod_symmetry')}</div>", unsafe_allow_html=True)
    with col_side:
        st.markdown(f"**{t('mod_symmetry')}**")
        st.caption("Os controles e métricas aparecem aqui.")
