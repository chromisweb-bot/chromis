"""
app.py — Chromis WEB · aplicativo principal

Rodar com:  streamlit run app.py

Estrutura de navegação por estado (st.session_state["page"]):
  login → dashboard → <módulo>

O dashboard agrupa os módulos por etapa e bloqueia os que têm
pré-requisitos não cumpridos (ver MODULE_DEPS).
"""

import streamlit as st

from i18n import t, get_lang, set_lang
from theme import (
    inject_theme, COLORS, render_logo_svg,
    render_language_toggle, card_open, badge,
)
from auth import (
    register_user, verify_login,
    notify_registration_request, notify_user_activity,
)

# Telas dos módulos (cada uma em seu arquivo, dentro de views/)
from views import (
    setup_view, tps_view, upload_view, point_view, symmetry_view,
    isocenter_view, calibration_view, dosemap_view, isodose_view,
    gamma_view, report_view,
)

# ──────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ──────────────────────────────────────────────────────────────────────────
# Ícone da página (favicon): usa a logo do software (assets/icon.png).
# Se a imagem não for encontrada, cai no emoji 🎯 para não quebrar.
try:
    from pathlib import Path as _Path
    from PIL import Image as _Image
    _PAGE_ICON = _Image.open(_Path(__file__).parent / "assets" / "icon.png")
except Exception:
    _PAGE_ICON = "🎯"

st.set_page_config(
    page_title="Chromis WEB",
    page_icon=_PAGE_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_theme()

# ──────────────────────────────────────────────────────────────────────────
# ESTADO INICIAL
# ──────────────────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "lang": "pt",
        "page": "login",
        "user": None,
        "auth_mode": "login",  # 'login' ou 'register'
        # flags de conclusão de cada módulo (controlam o bloqueio)
        "done": {
            "setup": False, "tps": False, "upload": False,
            "calibration": False, "dosemap": False,
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ──────────────────────────────────────────────────────────────────────────
# DEFINIÇÃO DOS MÓDULOS E DEPENDÊNCIAS
# id: (chave_i18n_nome, chave_i18n_desc, icone, cor, grupo, [pré-requisitos])
# ──────────────────────────────────────────────────────────────────────────
MODULES = {
    "setup":       ("mod_setup", "mod_setup_desc", "ti-settings", "amber", "config", []),
    "tps":         ("mod_tps", "mod_tps_desc", "ti-file-import", "teal", "config", ["setup"]),
    "upload":      ("mod_upload", "mod_upload_desc", "ti-photo-up", "blue", "config", ["setup"]),
    "point":       ("mod_point", "mod_point_desc", "ti-map-pin", "purple", "qa", ["upload", "tps"]),
    "symmetry":    ("mod_symmetry", "mod_symmetry_desc", "ti-border-corners", "purple", "qa", ["upload"]),
    "isocenter":   ("mod_isocenter", "mod_isocenter_desc", "ti-crosshair", "teal", "qa", []),
    "calibration": ("mod_calibration", "mod_calibration_desc", "ti-chart-dots", "blue", "dosimetry", ["upload"]),
    "dosemap":     ("mod_dosemap", "mod_dosemap_desc", "ti-map", "green", "dosimetry", ["calibration"]),
    "isodose":     ("mod_isodose", "mod_isodose_desc", "ti-contour", "purple", "dosimetry", ["dosemap"]),
    "gamma":       ("mod_gamma", "mod_gamma_desc", "ti-grid-dots", "amber", "dosimetry", ["dosemap"]),
    "report":      ("mod_report", "mod_report_desc", "ti-file-text", "green", "output", []),
}

GROUPS = [
    ("config",    "group_config"),
    ("qa",        "group_qa"),
    ("dosimetry", "group_dosimetry"),
    ("output",    "group_output"),
]

# Mapeia id do módulo → função de view
VIEW_FUNCS = {
    "setup": setup_view, "tps": tps_view, "upload": upload_view,
    "point": point_view, "symmetry": symmetry_view, "isocenter": isocenter_view,
    "calibration": calibration_view, "dosemap": dosemap_view,
    "isodose": isodose_view, "gamma": gamma_view, "report": report_view,
}


def is_unlocked(module_id: str) -> bool:
    """Retorna True se todos os pré-requisitos do módulo foram concluídos."""
    deps = MODULES[module_id][5]
    return all(st.session_state["done"].get(d, False) for d in deps)


def go(page: str):
    """Navega para uma página."""
    st.session_state["page"] = page
    st.rerun()


# ──────────────────────────────────────────────────────────────────────────
# TELA: LOGIN
# ──────────────────────────────────────────────────────────────────────────
def render_login():
    # Tabler icons + seletor de idioma no topo
    st.markdown(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/tabler-icons.min.css">',
        unsafe_allow_html=True,
    )
    top_l, top_r = st.columns([4, 1])
    with top_r:
        render_language_toggle()

    # Centralizar o card de login
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(f"""
        <div style="background:{COLORS['bg_card']};border:0.5px solid {COLORS['border']};
                    border-radius:16px;padding:32px 32px 26px;margin-top:30px;text-align:center">
          <div style="background:#000;border-radius:14px;padding:18px;margin-bottom:14px">
            {render_logo_svg(size=180, show_text=True)}
          </div>
          <div style="font-size:11px;color:{COLORS['text_muted']}">{t('tagline')} · EBT3/EBT4 · TG-218</div>
        </div>
        """, unsafe_allow_html=True)

        mode = st.session_state.get("auth_mode", "login")

        if mode == "login":
            # ===== LOGIN =====
            st.text_input(t("login_user"), placeholder="usuario@hospital.com", key="login_user_input")
            st.text_input(t("login_password"), type="password", key="login_pwd_input")

            if st.button(t("login_button"), use_container_width=True, type="primary"):
                email = st.session_state.get("login_user_input", "")
                pwd = st.session_state.get("login_pwd_input", "")
                ok, msg, user = verify_login(email, pwd)
                if ok:
                    st.session_state["user"] = user.get("name", email)
                    notify_user_activity(st.session_state["user"], "Login realizado")
                    go("dashboard")
                else:
                    st.error(msg)

            st.markdown(
                f'<div style="text-align:center;margin:10px 0;color:{COLORS["text_dim"]};font-size:11px">{t("login_or")}</div>',
                unsafe_allow_html=True,
            )
            if st.button("Fazer cadastro / Sign up", use_container_width=True):
                st.session_state["auth_mode"] = "register"
                st.rerun()

            # Acesso rápido como visitante (temporário, enquanto o cadastro
            # com banco de dados não está ativo)
            if st.button("Continuar como visitante / Continue as guest",
                         use_container_width=True):
                st.session_state["user"] = "Visitante"
                go("dashboard")

        else:
            # ===== CADASTRO =====
            st.markdown("**Fazer cadastro / Sign up**")
            st.text_input("Nome / Name", key="reg_name")
            st.text_input("E-mail", key="reg_email")
            st.text_input(t("login_password"), type="password", key="reg_pwd")

            if st.button("Enviar cadastro / Submit", use_container_width=True, type="primary"):
                name = st.session_state.get("reg_name", "").strip()
                email = st.session_state.get("reg_email", "").strip()
                pwd = st.session_state.get("reg_pwd", "")
                if not name or not email or not pwd:
                    st.error("Preencha todos os campos.")
                else:
                    ok, msg = register_user(name, email, pwd, method="email")
                    if ok:
                        notify_registration_request(name, email, "email")
                        st.success(msg)
                    else:
                        st.warning(msg)

            st.markdown(
                f'<div style="text-align:center;margin:8px 0;color:{COLORS["text_dim"]};font-size:11px">{t("login_or")}</div>',
                unsafe_allow_html=True,
            )
            # Cadastro com Google (estrutura pronta — requer config OAuth)
            if st.button("Cadastrar com Google / Sign up with Google", use_container_width=True):
                st.info("Login com Google requer configuração OAuth — veça o GUIA_CONFIGURACAO.md")

            if st.button(f"← {t('back')}", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()

        st.markdown(
            f'<div style="text-align:center;margin-top:22px;font-size:11px;color:{COLORS["text_dim"]}">{t("login_footer")}</div>',
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────
# TELA: DASHBOARD
# ──────────────────────────────────────────────────────────────────────────
def render_dashboard():
    st.markdown(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/tabler-icons.min.css">',
        unsafe_allow_html=True,
    )

    # Topbar
    c_logo, c_spacer, c_lang, c_logout = st.columns([3, 3, 1.2, 1])
    with c_logo:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;padding-top:2px">'
            f'<span style="background:#000;border-radius:10px;padding:8px 12px;display:inline-block">'
            f'{render_logo_svg(size=72, show_text=True)}</span></div>',
            unsafe_allow_html=True,
        )
    with c_lang:
        render_language_toggle()
    with c_logout:
        if st.button(t("logout"), use_container_width=True):
            st.session_state["user"] = None
            go("login")

    st.markdown(f"<div style='color:{COLORS['text_sec']};font-size:13px;margin:4px 0 18px'>"
                f"<span style='width:7px;height:7px;border-radius:50%;background:{COLORS['green_light']};"
                f"display:inline-block;margin-right:6px'></span>{st.session_state['user']}</div>",
                unsafe_allow_html=True)

    # Aviso de setup pendente
    if not st.session_state["done"]["setup"]:
        wa, wb = st.columns([5, 1])
        with wa:
            st.markdown(f"""
            <div style="background:{COLORS['bg_card']};border:0.5px solid {COLORS['border_soft']};
                        border-left:2px solid {COLORS['amber']};border-radius:10px;padding:13px 16px">
              <div style="font-size:13px;color:{COLORS['text']};font-weight:500">
                <i class="ti ti-alert-triangle" style="color:{COLORS['amber']};margin-right:6px"></i>{t('dash_setup_warn_title')}</div>
              <div style="font-size:11px;color:{COLORS['text_sec']};margin-top:2px">{t('dash_setup_warn_desc')}</div>
            </div>""", unsafe_allow_html=True)
        with wb:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            if st.button(t("dash_start_setup"), use_container_width=True, type="primary"):
                go("setup")

    st.markdown(f"<h2 style='text-align:center;margin:24px 0 18px'>{t('dash_welcome')}</h2>",
                unsafe_allow_html=True)

    # Renderizar grupos
    for group_id, group_label_key in GROUPS:
        mods = [mid for mid, m in MODULES.items() if m[4] == group_id]
        if not mods:
            continue
        st.markdown(
            f"<div style='font-size:10px;color:{COLORS['text_dim']};font-family:Space Mono,monospace;"
            f"letter-spacing:0.5px;margin:18px 0 8px'>{t(group_label_key).upper()}</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(mods))
        for col, mid in zip(cols, mods):
            with col:
                render_module_card(mid)


def render_module_card(module_id: str):
    name_key, desc_key, icon, color, _, deps = MODULES[module_id]
    unlocked = is_unlocked(module_id)
    done = st.session_state["done"].get(module_id, False)
    color_hex = COLORS.get(color, COLORS["blue"])

    # Card visual
    if not unlocked:
        # Bloqueado
        dep_label = t("requires_calib") if "calibration" in deps else (
            t("requires_dosemap") if "dosemap" in deps else t("locked"))
        st.markdown(f"""
        <div style="background:{COLORS['bg_deep']};border:0.5px solid {COLORS['border_soft']};
                    border-left:2px solid {COLORS['border']};border-radius:10px;padding:14px;opacity:0.55;min-height:118px">
          <i class="ti ti-lock" style="color:{COLORS['text_muted']};font-size:19px"></i>
          <div style="font-size:12px;color:{COLORS['text_sec']};font-weight:500;margin-top:8px">{t(name_key)}</div>
          <div style="font-size:10px;color:{COLORS['text_dim']};margin-top:2px">{dep_label}</div>
        </div>""", unsafe_allow_html=True)
    else:
        check = (f'<i class="ti ti-circle-check" style="color:{COLORS["green_light"]};'
                 f'font-size:15px;float:right"></i>') if done else ""
        st.markdown(f"""
        <div style="background:{COLORS['bg_card']};border:0.5px solid {COLORS['border_soft']};
                    border-top:2px solid {color_hex};border-radius:10px;padding:14px;min-height:118px">
          {check}
          <i class="ti {icon}" style="color:{color_hex};font-size:19px"></i>
          <div style="font-size:12px;color:{COLORS['text']};font-weight:500;margin-top:8px">{t(name_key)}</div>
          <div style="font-size:10px;color:{COLORS['text_sec']};margin-top:2px;line-height:1.4">{t(desc_key)}</div>
        </div>""", unsafe_allow_html=True)
        if st.button(t("continue"), key=f"open_{module_id}", use_container_width=True):
            go(module_id)


# ──────────────────────────────────────────────────────────────────────────
# CABEÇALHO COMUM DAS TELAS DE MÓDULO
# ──────────────────────────────────────────────────────────────────────────
def render_module_header(module_id: str):
    """Topbar com botão voltar + título do módulo (usado nas views)."""
    st.markdown(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/tabler-icons.min.css">',
        unsafe_allow_html=True,
    )
    name_key, _, icon, color, group_id, _ = MODULES[module_id]
    color_hex = COLORS.get(color, COLORS["blue"])
    group_key = next((gk for gid, gk in GROUPS if gid == group_id), "")

    c_back, c_title, c_lang = st.columns([1, 5, 1.5])
    with c_back:
        if st.button(f"← {t('back')}", use_container_width=True):
            go("dashboard")
    with c_title:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:9px;padding-top:6px">'
            f'<i class="ti {icon}" style="color:{color_hex};font-size:18px"></i>'
            f'<span style="font-size:16px;color:{COLORS["text"]};font-weight:500">{t(name_key)}</span>'
            f'<span style="font-size:11px;color:{COLORS["text_muted"]};margin-left:6px">· {t(group_key)}</span></div>',
            unsafe_allow_html=True,
        )
    with c_lang:
        render_language_toggle()
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:8px 0 16px'>",
                unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# ROTEAMENTO
# ──────────────────────────────────────────────────────────────────────────
page = st.session_state["page"]

if page == "login":
    render_login()
elif page == "dashboard":
    render_dashboard()
elif page in VIEW_FUNCS:
    render_module_header(page)
    # Cada view recebe um contexto com helpers e estado
    VIEW_FUNCS[page](st.session_state, go)
else:
    st.session_state["page"] = "login"
    st.rerun()
