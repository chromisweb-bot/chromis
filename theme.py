"""
theme.py — Tema escuro e componentes visuais do Chromis WEB.

Centraliza:
  - Paleta de cores (constantes COLORS)
  - CSS global (inject_theme)
  - Componentes HTML reutilizáveis (logo, topbar, language toggle, etc.)
"""

import base64
from pathlib import Path
import streamlit as st
from i18n import t, get_lang, set_lang

# ──────────────────────────────────────────────────────────────────────────
# CARREGAMENTO DAS LOGOS (cache em base64 para embutir no HTML)
# ──────────────────────────────────────────────────────────────────────────
_ASSETS = Path(__file__).parent / "assets"

@st.cache_data
def _img_b64(filename: str) -> str:
    """Lê uma imagem da pasta assets e retorna como data-URI base64."""
    path = _ASSETS / filename
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def logo_full() -> str:
    """Data-URI da logo completa (fundo transparente) — para login/dashboard."""
    return _img_b64("logo_full.png")


def icon_only() -> str:
    """Data-URI do ícone do C (fundo transparente) — para topbar/sidebar."""
    return _img_b64("icon.png")


# ──────────────────────────────────────────────────────────────────────────
# PALETA DE CORES — referência única, usada em todo o app
# ──────────────────────────────────────────────────────────────────────────
COLORS = {
    "bg_deep":     "#0b0e14",
    "bg_card":     "#11161e",
    "bg_surface":  "#161d28",
    "bg_hover":    "#1c2230",
    "border":      "#2d333b",
    "border_soft": "#1c2128",
    "text":        "#e6edf3",
    "text_sec":    "#8b949e",
    "text_muted":  "#6e7681",
    "text_dim":    "#484f58",
    "blue":        "#1f6feb",
    "blue_light":  "#58a6ff",
    "green":       "#238636",
    "green_light": "#3fb950",
    "green_soft":  "#7ee787",
    "amber":       "#d29922",
    "amber_light": "#fbbf24",
    "red":         "#da3633",
    "red_light":   "#f85149",
    "purple":      "#8957e5",
    "purple_light":"#a371f7",
    "teal":        "#1d9e75",
    "teal_light":  "#5dcaa5",
}


def inject_theme():
    """Injeta o CSS global. Chamar logo após st.set_page_config()."""
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');

    html, body, [class*="css"] {{ font-family: 'DM Sans', -apple-system, sans-serif !important; }}
    .stApp {{ background-color: {COLORS['bg_deep']} !important; }}

    /* Esconde elementos padrão do Streamlit para visual mais limpo */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
    .block-container {{ padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1100px; }}

    /* Tipografia */
    h1, h2, h3, h4 {{ color: {COLORS['text']} !important; font-family: 'DM Sans', sans-serif !important; letter-spacing: -0.3px; }}

    /* Inputs */
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea {{
        background: {COLORS['bg_deep']} !important;
        border: 0.5px solid {COLORS['border']} !important;
        border-radius: 8px !important;
        color: {COLORS['text']} !important;
    }}
    [data-testid="stTextInput"] input:focus {{ border-color: {COLORS['blue']} !important; }}

    /* Selectbox */
    [data-testid="stSelectbox"] > div > div {{
        background: {COLORS['bg_deep']} !important;
        border: 0.5px solid {COLORS['border']} !important;
        border-radius: 8px !important;
    }}

    /* Botões */
    .stButton > button {{
        background: {COLORS['green']} !important;
        border: none !important; border-radius: 8px !important;
        color: white !important; font-weight: 500 !important;
        font-family: 'DM Sans', sans-serif !important;
        transition: opacity 0.15s !important;
    }}
    .stButton > button:hover {{ opacity: 0.88 !important; }}
    .stButton > button:focus {{ box-shadow: none !important; }}

    /* Sliders */
    [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{ background: {COLORS['blue']} !important; }}

    /* Métricas */
    [data-testid="stMetric"] {{
        background: {COLORS['bg_surface']} !important;
        border: 0.5px solid {COLORS['border_soft']} !important;
        border-radius: 10px !important; padding: 12px !important;
    }}
    [data-testid="stMetricValue"] {{ font-family: 'Space Mono', monospace !important; }}

    /* Tabs */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{ border-bottom: 0.5px solid {COLORS['border']} !important; gap: 0 !important; }}
    [data-testid="stTabs"] [aria-selected="true"] {{ color: {COLORS['green_light']} !important; }}

    /* Scrollbar */
    ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
    ::-webkit-scrollbar-thumb {{ background: {COLORS['border']}; border-radius: 3px; }}

    /* File uploader */
    [data-testid="stFileUploader"] {{
        background: {COLORS['bg_surface']} !important;
        border: 1px dashed {COLORS['border']} !important;
        border-radius: 10px !important;
    }}

    /* Esconde o label vazio que cria espaço */
    .element-container:has(.stMarkdown:empty) {{ display: none; }}
    </style>
    """, unsafe_allow_html=True)


def render_logo_svg(size: int = 32, show_text: bool = True, web_gradient: bool = True) -> str:
    """
    Retorna o <img> da logo Chromis WEB usando os arquivos reais.
    - show_text=True  → logo completa (ícone + Chromis WEB)
    - show_text=False → só o ícone do C
    Os parâmetros web_gradient/size_text são mantidos por compatibilidade.
    """
    if show_text:
        src = logo_full()
        return f'<img src="{src}" style="height:{size}px;vertical-align:middle" alt="Chromis WEB"/>'
    else:
        src = icon_only()
        return f'<img src="{src}" style="height:{size}px;width:{size}px;object-fit:contain;vertical-align:middle" alt="Chromis"/>'


def render_language_toggle():
    """
    Renderiza o seletor PT/EN. Usa botões reais do Streamlit para funcionar.
    Coloca no canto superior via colunas.
    """
    lang = get_lang()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("PT", key="lang_pt", use_container_width=True,
                     type="primary" if lang == "pt" else "secondary"):
            set_lang("pt"); st.rerun()
    with c2:
        if st.button("EN", key="lang_en", use_container_width=True,
                     type="primary" if lang == "en" else "secondary"):
            set_lang("en"); st.rerun()


def card_open(border_color: str = None, padding: str = "16px") -> str:
    """Retorna a abertura de um card (use com st.markdown unsafe_allow_html)."""
    bc = f"border-left: 2px solid {border_color};" if border_color else ""
    return (f'<div style="background:{COLORS["bg_card"]};border:0.5px solid '
            f'{COLORS["border_soft"]};{bc}border-radius:10px;padding:{padding}">')


def badge(text: str, color: str = "blue") -> str:
    """Retorna um badge colorido inline."""
    cmap = {
        "blue":   (COLORS["blue_light"], "rgba(31,111,235,0.12)"),
        "green":  (COLORS["green_light"], "rgba(35,134,54,0.12)"),
        "amber":  (COLORS["amber_light"], "rgba(210,153,34,0.12)"),
        "red":    (COLORS["red_light"], "rgba(218,54,51,0.12)"),
        "purple": (COLORS["purple_light"], "rgba(137,87,229,0.12)"),
        "teal":   (COLORS["teal_light"], "rgba(29,158,117,0.12)"),
    }
    fg, bg = cmap.get(color, cmap["blue"])
    return (f'<span style="font-size:11px;padding:2px 9px;border-radius:10px;'
            f'background:{bg};color:{fg};font-family:Space Mono,monospace">{text}</span>')
