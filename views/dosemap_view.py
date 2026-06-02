"""dosemap_view.py — Tela do módulo (interface pronta; cálculo em integração)."""
import streamlit as st
from i18n import t
from theme import COLORS
from auth import notify_user_activity


def dosemap_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"Análise · {t('group_dosimetry')}</div>", unsafe_allow_html=True)

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
                    f"Área de visualização — {t('mod_dosemap')}</div>", unsafe_allow_html=True)
    with col_side:
        st.markdown(f"**{t('mod_dosemap')}**")
        st.caption("Os controles e métricas aparecem aqui.")

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:18px 0'>",
                unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button(t("continue"), use_container_width=True, type="primary"):
            state["done"]["dosemap"] = True
            notify_user_activity(state.get("user", "?"), "dosemap_view concluído")
            go("dashboard")
