"""
admin_panel.py — Painel administrativo (aprovação de cadastros).

Acesse com:  streamlit run admin_panel.py

Protegido por uma senha de admin definida em st.secrets:
    [admin]
    password = "sua-senha-aqui"

Aqui você vê os cadastros pendentes e aprova/recusa cada um.
Ao aprovar/recusar, o usuário poderá (ou não) fazer login no app principal.
"""

import streamlit as st
from theme import inject_theme, COLORS
from auth.accounts import list_pending, approve_user, reject_user, _load_users

st.set_page_config(page_title="Chromis WEB · Admin", page_icon="🔐", layout="centered")
inject_theme()

st.markdown(f"<h2 style='color:{COLORS['text']}'>🔐 Painel Administrativo — Chromis WEB</h2>",
            unsafe_allow_html=True)


def _check_admin():
    try:
        admin_pwd = st.secrets["admin"]["password"]
    except Exception:
        st.error("Senha de admin não configurada nos secrets. Veja GUIA_CONFIGURACAO.md")
        return False
    pwd = st.text_input("Senha de administrador", type="password")
    if not pwd:
        return False
    if pwd != admin_pwd:
        st.error("Senha incorreta.")
        return False
    return True


if _check_admin():
    st.success("Acesso autorizado.")

    pending = list_pending()
    st.markdown(f"### Cadastros pendentes ({len(pending)})")

    if not pending:
        st.info("Nenhum cadastro pendente.")
    else:
        for u in pending:
            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{u['name']}**  \n{u['email']}  \n_{u.get('method', 'email')} · {u.get('created_at', '')[:16]}_")
                if c2.button("✅ Aprovar", key=f"ap_{u['email']}"):
                    approve_user(u["email"])
                    st.rerun()
                if c3.button("❌ Recusar", key=f"rj_{u['email']}"):
                    reject_user(u["email"])
                    st.rerun()
                st.divider()

    # Lista geral
    with st.expander("Todos os usuários"):
        users = _load_users()
        for email, u in users.items():
            st.markdown(f"- **{u['name']}** ({email}) — `{u['status']}`")
