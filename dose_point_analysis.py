"""
dose_point_analysis.py — Análise de Pontos de Dose e Perfis

Dois módulos:
  1. Dose pontual: compara dose do filme vs TPS em coordenadas específicas
  2. Perfil de dose: extrai e compara perfil ao longo de uma linha

Como usar no Streamlit:
  from dose_point_analysis import render_dose_points_ui, render_dose_profile_ui
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy.ndimage import map_coordinates
from scipy.interpolate import RegularGridInterpolator
import streamlit as st
import io


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 1 — DOSE PONTUAL
# ══════════════════════════════════════════════════════════════════════════════

def mm_to_pixel(x_mm, y_mm, res_mm, origin_mm=(0.0, 0.0), shape=None):
    """
    Converte coordenadas em mm para índices de pixel no array de dose.

    O sistema de coordenadas assume:
      - Origem (0,0) no CENTRO do mapa de dose (padrão DICOM/TPS)
      - X positivo → direita
      - Y positivo → cima (invertido em relação ao array: row 0 = topo)

    Args:
        x_mm, y_mm : coordenadas do ponto em mm
        res_mm     : resolução em mm/pixel
        origin_mm  : (x0, y0) da origem do mapa em mm (canto superior esquerdo)
                     Se None, assume centro do array como origem
        shape      : (rows, cols) do array — necessário se origin_mm=None

    Returns:
        (row, col) como floats — pode ser não-inteiro para interpolação
    """
    if origin_mm is None and shape is not None:
        # Origem no centro
        h, w = shape
        x0 = -(w / 2.0) * res_mm
        y0 = -(h / 2.0) * res_mm
    else:
        x0, y0 = origin_mm

    col = (x_mm - x0) / res_mm
    # Y em mm cresce para cima, mas row no array cresce para baixo → inverter
    row = (y_mm - y0) / res_mm
    # Se origem no centro e Y positivo = cima:
    if shape is not None and origin_mm == (0.0, 0.0):
        h, w = shape
        col = (x_mm / res_mm) + w / 2.0
        row = -(y_mm / res_mm) + h / 2.0

    return float(row), float(col)


def read_dose_at_point(dose_map, row, col, method='bilinear'):
    """
    Lê a dose em uma posição (row, col) usando interpolação.

    Args:
        dose_map : np.ndarray 2D de dose
        row, col : posição em pixels (pode ser float)
        method   : 'bilinear' ou 'nearest'

    Returns:
        float: dose interpolada em Gy (ou nan se fora dos limites)
    """
    h, w = dose_map.shape
    if row < 0 or row >= h or col < 0 or col >= w:
        return np.nan

    if method == 'nearest':
        return float(dose_map[int(round(row)), int(round(col))])

    # Bilinear via map_coordinates (ordem 1)
    coords = np.array([[row], [col]])
    result = map_coordinates(dose_map, coords, order=1, mode='nearest')
    return float(result[0])


def compare_dose_points(
    dose_film,
    dose_tps,
    points,
    res_mm,
    origin_mm=(0.0, 0.0),
    tolerance_percent=3.0,
):
    """
    Compara dose filme vs TPS em pontos específicos.

    Args:
        dose_film    : np.ndarray 2D — mapa de dose do filme (Gy)
        dose_tps     : np.ndarray 2D — mapa de dose do TPS (Gy)
        points       : lista de dicts com keys:
                         'name'     : str (ex: 'P1', 'Centro')
                         'x_mm'     : float (coordenada X em mm)
                         'y_mm'     : float (coordenada Y em mm)
                         'dose_tps' : float (dose do TPS em cGy) — opcional,
                                      se None usa dose_tps array
        res_mm       : resolução em mm/pixel
        origin_mm    : origem do sistema de coordenadas
        tolerance_percent : tolerância para aprovação (%)

    Returns:
        pd.DataFrame com resultados
        dict com estatísticas gerais
    """
    results = []

    for pt in points:
        name = pt.get('name', '?')
        x_mm = float(pt.get('x_mm', 0))
        y_mm = float(pt.get('y_mm', 0))
        dose_tps_ref = pt.get('dose_tps', None)  # em cGy

        # Converter mm → pixel
        row, col = mm_to_pixel(x_mm, y_mm, res_mm, origin_mm, dose_film.shape)

        # Ler dose do filme
        dose_film_val = read_dose_at_point(dose_film, row, col) * 100.0  # Gy → cGy

        # Ler dose do TPS array (se não fornecida como valor fixo)
        if dose_tps_ref is None:
            dose_tps_val = read_dose_at_point(dose_tps, row, col) * 100.0
        else:
            dose_tps_val = float(dose_tps_ref)

        # Calcular erro
        if dose_tps_val > 0 and not np.isnan(dose_film_val):
            erro_abs = dose_film_val - dose_tps_val
            erro_pct = 100.0 * erro_abs / dose_tps_val
            aprovado = abs(erro_pct) <= tolerance_percent
        else:
            erro_abs = np.nan
            erro_pct = np.nan
            aprovado = False

        results.append({
            'Ponto': name,
            'X (mm)': x_mm,
            'Y (mm)': y_mm,
            'Pixel (row)': round(row, 1),
            'Pixel (col)': round(col, 1),
            'Dose TPS (cGy)': round(dose_tps_val, 2),
            'Dose Filme (cGy)': round(dose_film_val, 2) if not np.isnan(dose_film_val) else np.nan,
            'Erro Abs (cGy)': round(erro_abs, 2) if not np.isnan(erro_abs) else np.nan,
            'Erro (%)': round(erro_pct, 2) if not np.isnan(erro_pct) else np.nan,
            'Status': '✅ OK' if aprovado else '❌ FAIL',
            '_aprovado': aprovado,
            '_fora': np.isnan(dose_film_val),
        })

    df = pd.DataFrame(results)

    # Estatísticas
    erros = df['Erro (%)'].dropna()
    n_ok = df['_aprovado'].sum()
    n_total = len(df)

    stats = {
        'n_total': n_total,
        'n_ok': int(n_ok),
        'n_fail': int(n_total - n_ok),
        'passing_rate': 100.0 * n_ok / n_total if n_total > 0 else 0.0,
        'erro_medio': float(erros.mean()) if len(erros) > 0 else np.nan,
        'erro_max': float(erros.abs().max()) if len(erros) > 0 else np.nan,
        'erro_std': float(erros.std()) if len(erros) > 0 else np.nan,
    }

    return df, stats


def plot_dose_points_on_map(dose_film, points, res_mm, origin_mm=(0.0, 0.0), results_df=None):
    """
    Plota o mapa de dose do filme com os pontos marcados.

    Returns:
        matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor('#161b22')
    ax.set_facecolor('#161b22')

    # Mapa de dose
    vmax = np.percentile(dose_film[dose_film > 0], 99) if np.any(dose_film > 0) else 1
    im = ax.imshow(
        dose_film * 100,  # Gy → cGy
        cmap='jet',
        vmin=0,
        vmax=vmax * 100,
        aspect='equal',
        origin='upper',
    )
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Dose (cGy)', color='#8b949e', fontsize=9)
    cbar.ax.yaxis.set_tick_params(color='#8b949e', labelcolor='#8b949e')

    # Marcar pontos
    for i, pt in enumerate(points):
        row, col = mm_to_pixel(
            float(pt.get('x_mm', 0)),
            float(pt.get('y_mm', 0)),
            res_mm, origin_mm, dose_film.shape
        )

        # Cor baseada no resultado
        if results_df is not None and i < len(results_df):
            aprovado = results_df.iloc[i]['_aprovado']
            fora = results_df.iloc[i]['_fora']
            color = '#ef4444' if fora else ('#22c55e' if aprovado else '#f59e0b')
        else:
            color = '#60a5fa'

        ax.plot(col, row, 'o', color=color, markersize=8, markeredgecolor='white',
                markeredgewidth=1.5, zorder=5)
        ax.annotate(
            pt.get('name', f'P{i+1}'),
            (col, row),
            textcoords='offset points',
            xytext=(6, 6),
            fontsize=8,
            color='white',
            fontweight='bold',
            zorder=6,
        )

    ax.set_title('Mapa de Dose — Pontos de Verificação', color='#e6edf3', fontsize=11, pad=8)
    ax.tick_params(colors='#484f58', labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor('#30363d')

    # Legenda
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#22c55e', markersize=8, label='OK'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#f59e0b', markersize=8, label='FAIL'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#ef4444', markersize=8, label='Fora do filme'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8,
              facecolor='#1c2230', edgecolor='#30363d', labelcolor='#e6edf3')

    plt.tight_layout()
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 2 — PERFIL DE DOSE
# ══════════════════════════════════════════════════════════════════════════════

def extract_dose_profile(dose_map, row_start, col_start, row_end, col_end, n_points=500):
    """
    Extrai perfil de dose ao longo de uma linha entre dois pontos.

    Args:
        dose_map              : np.ndarray 2D
        row_start, col_start  : ponto inicial em pixels
        row_end, col_end      : ponto final em pixels
        n_points              : número de amostras ao longo da linha

    Returns:
        distances_mm : np.ndarray — distâncias em pixels (converter depois)
        doses        : np.ndarray — doses ao longo da linha
    """
    rows = np.linspace(row_start, row_end, n_points)
    cols = np.linspace(col_start, col_end, n_points)

    coords = np.array([rows, cols])
    doses = map_coordinates(dose_map, coords, order=1, mode='nearest')

    # Distância ao longo da linha (em pixels)
    total_px = np.sqrt((row_end - row_start)**2 + (col_end - col_start)**2)
    distances_px = np.linspace(0, total_px, n_points)

    return distances_px, doses


def extract_profile_mm(dose_map, x_start_mm, y_start_mm, x_end_mm, y_end_mm,
                       res_mm, origin_mm=(0.0, 0.0), n_points=500):
    """
    Extrai perfil de dose entre dois pontos em coordenadas mm.

    Returns:
        distances_mm : np.ndarray — distâncias em mm ao longo do perfil
        doses        : np.ndarray — doses (em unidades do dose_map)
    """
    r_start, c_start = mm_to_pixel(x_start_mm, y_start_mm, res_mm, origin_mm, dose_map.shape)
    r_end, c_end = mm_to_pixel(x_end_mm, y_end_mm, res_mm, origin_mm, dose_map.shape)

    distances_px, doses = extract_dose_profile(
        dose_map, r_start, c_start, r_end, c_end, n_points
    )
    distances_mm = distances_px * res_mm

    return distances_mm, doses


def compute_penumbra(distances_mm, doses, high_pct=80.0, low_pct=20.0):
    """
    Calcula a penumbra (distância entre high_pct% e low_pct% da dose máxima).
    Retorna penumbra em mm para as bordas esquerda e direita.
    """
    doses_norm = doses / np.max(doses) * 100.0

    # Borda esquerda (primeira transição de cima para baixo ou baixo para cima)
    penumbra_left = None
    penumbra_right = None

    try:
        # Encontrar posição do high_pct e low_pct à esquerda
        mid = len(distances_mm) // 2

        # Lado esquerdo
        left_doses = doses_norm[:mid]
        left_dists = distances_mm[:mid]
        idx_high_l = np.argmin(np.abs(left_doses - high_pct))
        idx_low_l = np.argmin(np.abs(left_doses - low_pct))
        penumbra_left = abs(left_dists[idx_high_l] - left_dists[idx_low_l])

        # Lado direito
        right_doses = doses_norm[mid:]
        right_dists = distances_mm[mid:]
        idx_high_r = np.argmin(np.abs(right_doses - high_pct))
        idx_low_r = np.argmin(np.abs(right_doses - low_pct))
        penumbra_right = abs(right_dists[idx_high_r] - right_dists[idx_low_r])
    except Exception:
        pass

    return penumbra_left, penumbra_right


def compute_field_size(distances_mm, doses, threshold_pct=50.0):
    """
    Calcula o tamanho do campo (FWHM) a partir do perfil.
    threshold_pct: percentual da dose máxima para definir a borda (padrão 50%)
    Returns: field_size_mm, left_edge_mm, right_edge_mm
    """
    doses_norm = doses / np.max(doses) * 100.0
    threshold = threshold_pct

    try:
        # Encontrar as bordas por interpolação linear
        left_edge = None
        right_edge = None

        for i in range(len(doses_norm) - 1):
            if doses_norm[i] < threshold <= doses_norm[i + 1]:
                # Interpolação linear
                frac = (threshold - doses_norm[i]) / (doses_norm[i + 1] - doses_norm[i])
                left_edge = distances_mm[i] + frac * (distances_mm[i + 1] - distances_mm[i])
            if doses_norm[i] >= threshold > doses_norm[i + 1]:
                frac = (doses_norm[i] - threshold) / (doses_norm[i] - doses_norm[i + 1])
                right_edge = distances_mm[i] + frac * (distances_mm[i + 1] - distances_mm[i])

        if left_edge is not None and right_edge is not None:
            return right_edge - left_edge, left_edge, right_edge
    except Exception:
        pass

    return None, None, None


def plot_dose_profiles(
    distances_film, doses_film,
    distances_tps=None, doses_tps=None,
    profile_label="Perfil",
    res_mm=1.0,
    show_penumbra=True,
    show_field_size=True,
    dose_unit="cGy",
):
    """
    Plota perfil de dose do filme vs TPS.

    Returns:
        matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#161b22')
    ax.set_facecolor('#0d1117')

    # Converter unidade
    scale = 100.0 if dose_unit == "cGy" else 1.0

    doses_film_plot = doses_film * scale
    doses_film_norm = doses_film_plot / np.max(doses_film_plot) * 100

    # Perfil do filme
    ax.plot(distances_film, doses_film_norm, color='#3b82f6', linewidth=2,
            label='Filme (Chromis)', zorder=3)

    # Perfil do TPS (se fornecido)
    if distances_tps is not None and doses_tps is not None:
        doses_tps_plot = doses_tps * scale
        doses_tps_norm = doses_tps_plot / np.max(doses_tps_plot) * 100
        ax.plot(distances_tps, doses_tps_norm, color='#f59e0b', linewidth=2,
                linestyle='--', label='TPS (Monaco)', zorder=3)

    # Linhas de referência
    ax.axhline(y=100, color='#484f58', linewidth=0.8, linestyle=':', alpha=0.7)
    ax.axhline(y=50, color='#484f58', linewidth=0.8, linestyle=':', alpha=0.7)
    ax.axhline(y=80, color='#484f58', linewidth=0.5, linestyle=':', alpha=0.5)
    ax.axhline(y=20, color='#484f58', linewidth=0.5, linestyle=':', alpha=0.5)

    ax.text(distances_film[-1] * 0.98, 101.5, '100%', color='#484f58', fontsize=8, ha='right')
    ax.text(distances_film[-1] * 0.98, 51.5, '50%', color='#484f58', fontsize=8, ha='right')
    ax.text(distances_film[-1] * 0.98, 81.5, '80%', color='#484f58', fontsize=8, ha='right')
    ax.text(distances_film[-1] * 0.98, 21.5, '20%', color='#484f58', fontsize=8, ha='right')

    # Tamanho do campo
    if show_field_size:
        fs, left_e, right_e = compute_field_size(distances_film, doses_film_norm)
        if fs is not None:
            ax.axvline(x=left_e, color='#22c55e', linewidth=1.2, linestyle='--', alpha=0.8)
            ax.axvline(x=right_e, color='#22c55e', linewidth=1.2, linestyle='--', alpha=0.8)
            ax.annotate(
                f'Campo: {fs:.1f} mm',
                xy=((left_e + right_e) / 2, 55),
                ha='center', fontsize=9, color='#22c55e',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#161b22', edgecolor='#22c55e', alpha=0.9)
            )

    # Penumbra
    if show_penumbra:
        p_left, p_right = compute_penumbra(distances_film, doses_film_norm)
        if p_left is not None:
            ax.annotate(
                f'Pen. esq: {p_left:.1f} mm',
                xy=(distances_film[len(distances_film)//6], 50),
                fontsize=8, color='#a855f7',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='#161b22', edgecolor='#a855f7', alpha=0.8)
            )
        if p_right is not None:
            ax.annotate(
                f'Pen. dir: {p_right:.1f} mm',
                xy=(distances_film[5*len(distances_film)//6], 50),
                fontsize=8, color='#a855f7',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='#161b22', edgecolor='#a855f7', alpha=0.8)
            )

    ax.set_xlabel('Distância (mm)', color='#8b949e', fontsize=10)
    ax.set_ylabel('Dose Relativa (%)', color='#8b949e', fontsize=10)
    ax.set_title(f'Perfil de Dose — {profile_label}', color='#e6edf3', fontsize=11, pad=8)
    ax.set_ylim(-5, 115)
    ax.tick_params(colors='#484f58', labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor('#30363d')

    ax.legend(facecolor='#1c2230', edgecolor='#30363d', labelcolor='#e6edf3', fontsize=9)
    ax.grid(True, color='#21262d', linewidth=0.5, alpha=0.7)

    plt.tight_layout()
    return fig


def plot_profile_line_on_map(dose_map, x_start_mm, y_start_mm, x_end_mm, y_end_mm,
                              res_mm, origin_mm=(0.0, 0.0)):
    """
    Plota o mapa de dose com a linha do perfil desenhada sobre ele.
    """
    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor('#161b22')
    ax.set_facecolor('#161b22')

    vmax = np.percentile(dose_map[dose_map > 0], 99) if np.any(dose_map > 0) else 1
    ax.imshow(dose_map * 100, cmap='jet', vmin=0, vmax=vmax * 100, aspect='equal', origin='upper')

    r_start, c_start = mm_to_pixel(x_start_mm, y_start_mm, res_mm, origin_mm, dose_map.shape)
    r_end, c_end = mm_to_pixel(x_end_mm, y_end_mm, res_mm, origin_mm, dose_map.shape)

    ax.plot([c_start, c_end], [r_start, r_end], color='white', linewidth=2, zorder=5)
    ax.plot(c_start, r_start, 'o', color='#22c55e', markersize=8, zorder=6)
    ax.plot(c_end, r_end, 's', color='#f59e0b', markersize=8, zorder=6)
    ax.annotate('A', (c_start, r_start), textcoords='offset points', xytext=(5, 5),
                color='#22c55e', fontweight='bold', fontsize=9)
    ax.annotate('B', (c_end, r_end), textcoords='offset points', xytext=(5, 5),
                color='#f59e0b', fontweight='bold', fontsize=9)

    ax.set_title('Linha do Perfil A→B', color='#e6edf3', fontsize=10)
    ax.tick_params(colors='#484f58', labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor('#30363d')

    plt.tight_layout()
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# PARTE 3 — INTERFACES STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════

def render_dose_points_ui(dose_film, dose_tps, res_mm, section_key="dp"):
    """
    Interface completa de Dose Pontual para o Streamlit.

    Como usar no seu app:
        from dose_point_analysis import render_dose_points_ui
        render_dose_points_ui(dose_film, dose_tps, res_mm)
    """
    st.subheader("📍 Dose Pontual — Comparação por Coordenadas")

    st.info(
        "Informe as coordenadas dos pontos de dose do TPS (exportadas do Monaco). "
        "A origem (0, 0) é o centro do campo. X positivo = direita, Y positivo = cima."
    )

    # ── Método de entrada ──────────────────────────────────────────────────
    metodo = st.radio(
        "Como deseja informar os pontos?",
        ["Digitar manualmente", "Carregar CSV"],
        horizontal=True,
        key=f"metodo_{section_key}"
    )

    points = []

    if metodo == "Digitar manualmente":
        n_pts = st.number_input("Número de pontos", min_value=1, max_value=20, value=5,
                                key=f"npts_{section_key}")

        st.markdown("**Coordenadas dos pontos** (X e Y em mm, Dose TPS em cGy):")
        cols_header = st.columns([1.5, 1.2, 1.2, 1.5])
        cols_header[0].markdown("**Nome**")
        cols_header[1].markdown("**X (mm)**")
        cols_header[2].markdown("**Y (mm)**")
        cols_header[3].markdown("**Dose TPS (cGy)**")

        for i in range(int(n_pts)):
            cols = st.columns([1.5, 1.2, 1.2, 1.5])
            nome = cols[0].text_input("", value=f"P{i+1}", key=f"nome_{section_key}_{i}",
                                      label_visibility="collapsed")
            x = cols[1].number_input("", value=0.0, step=0.5, format="%.1f",
                                     key=f"x_{section_key}_{i}", label_visibility="collapsed")
            y = cols[2].number_input("", value=0.0, step=0.5, format="%.1f",
                                     key=f"y_{section_key}_{i}", label_visibility="collapsed")
            dose = cols[3].number_input("", value=100.0, step=0.1, format="%.2f",
                                        key=f"d_{section_key}_{i}", label_visibility="collapsed")
            points.append({'name': nome, 'x_mm': x, 'y_mm': y, 'dose_tps': dose})

    else:  # CSV
        st.markdown("""
        **Formato do CSV** (separado por vírgula ou ponto-e-vírgula):
        ```
        nome,x_mm,y_mm,dose_tps_cgy
        Centro,0,0,100.0
        P1,10,0,98.5
        P2,-10,0,98.3
        ```
        """)
        csv_file = st.file_uploader("Carregar CSV com pontos", type=['csv'],
                                    key=f"csv_{section_key}")
        if csv_file:
            try:
                df_csv = pd.read_csv(csv_file, sep=None, engine='python')
                df_csv.columns = [c.strip().lower() for c in df_csv.columns]

                # Aceitar variações de nome de coluna
                col_map = {}
                for col in df_csv.columns:
                    if 'nome' in col or 'name' in col or 'ponto' in col:
                        col_map['name'] = col
                    elif col in ('x', 'x_mm', 'x(mm)'):
                        col_map['x_mm'] = col
                    elif col in ('y', 'y_mm', 'y(mm)'):
                        col_map['y_mm'] = col
                    elif 'dose' in col or 'tps' in col:
                        col_map['dose_tps'] = col

                for _, row_csv in df_csv.iterrows():
                    points.append({
                        'name': str(row_csv.get(col_map.get('name', df_csv.columns[0]), '?')),
                        'x_mm': float(row_csv.get(col_map.get('x_mm', 0), 0)),
                        'y_mm': float(row_csv.get(col_map.get('y_mm', 0), 0)),
                        'dose_tps': float(row_csv.get(col_map.get('dose_tps', 0), 0)),
                    })
                st.success(f"✅ {len(points)} pontos carregados do CSV.")
            except Exception as e:
                st.error(f"Erro ao ler CSV: {e}")

    # ── Tolerância ─────────────────────────────────────────────────────────
    tolerancia = st.slider("Tolerância (%)", min_value=1.0, max_value=5.0, value=3.0, step=0.5,
                           key=f"tol_{section_key}")

    # ── Calcular ───────────────────────────────────────────────────────────
    if st.button("📊 Calcular Dose Pontual", type="primary", key=f"btn_{section_key}"):
        if not points:
            st.warning("Adicione pelo menos um ponto.")
            return

        with st.spinner("Calculando..."):
            origin = (0.0, 0.0)
            df_results, stats = compare_dose_points(
                dose_film, dose_tps, points, res_mm,
                origin_mm=origin,
                tolerance_percent=tolerancia,
            )

        # ── Métricas gerais ────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Passing Rate", f"{stats['passing_rate']:.1f}%",
                    delta=f"{stats['n_ok']}/{stats['n_total']} pontos")
        col2.metric("Erro Médio", f"{stats['erro_medio']:.2f}%")
        col3.metric("Erro Máx", f"{stats['erro_max']:.2f}%")
        col4.metric("Desvio Padrão", f"{stats['erro_std']:.2f}%")

        # ── Tabela ─────────────────────────────────────────────────────────
        st.markdown("**Resultados por Ponto:**")
        display_cols = ['Ponto', 'X (mm)', 'Y (mm)', 'Dose TPS (cGy)',
                        'Dose Filme (cGy)', 'Erro Abs (cGy)', 'Erro (%)', 'Status']
        st.dataframe(
            df_results[display_cols],
            use_container_width=True,
            hide_index=True,
        )

        # ── Gráfico no mapa ────────────────────────────────────────────────
        col_map, col_bar = st.columns([2, 1])
        with col_map:
            fig_map = plot_dose_points_on_map(dose_film, points, res_mm,
                                              results_df=df_results)
            st.pyplot(fig_map, use_container_width=True)
            plt.close(fig_map)

        with col_bar:
            # Gráfico de barras dos erros
            fig_bar, ax_bar = plt.subplots(figsize=(4, 4))
            fig_bar.patch.set_facecolor('#161b22')
            ax_bar.set_facecolor('#0d1117')

            erros = df_results['Erro (%)'].dropna()
            nomes = df_results.loc[df_results['Erro (%)'].notna(), 'Ponto']
            cores = ['#22c55e' if abs(e) <= tolerancia else '#ef4444' for e in erros]

            bars = ax_bar.barh(range(len(erros)), erros, color=cores, height=0.6)
            ax_bar.axvline(x=tolerancia, color='#f59e0b', linewidth=1.5,
                           linestyle='--', label=f'+{tolerancia}%')
            ax_bar.axvline(x=-tolerancia, color='#f59e0b', linewidth=1.5, linestyle='--')
            ax_bar.axvline(x=0, color='#484f58', linewidth=1)
            ax_bar.set_yticks(range(len(nomes)))
            ax_bar.set_yticklabels(nomes, fontsize=8, color='#8b949e')
            ax_bar.set_xlabel('Erro (%)', color='#8b949e', fontsize=9)
            ax_bar.set_title('Erro por Ponto', color='#e6edf3', fontsize=10)
            ax_bar.tick_params(colors='#484f58', labelsize=8)
            for spine in ax_bar.spines.values():
                spine.set_edgecolor('#30363d')
            ax_bar.legend(facecolor='#1c2230', edgecolor='#30363d',
                          labelcolor='#e6edf3', fontsize=8)
            plt.tight_layout()
            st.pyplot(fig_bar, use_container_width=True)
            plt.close(fig_bar)

        # ── Download ───────────────────────────────────────────────────────
        csv_out = df_results[display_cols].to_csv(index=False)
        st.download_button(
            "📥 Download Resultados (CSV)",
            csv_out,
            "dose_pontual.csv",
            "text/csv",
        )

        # Salvar no session_state para o relatório
        st.session_state['dose_points_result'] = {
            'df': df_results,
            'stats': stats,
            'points': points,
        }


def render_dose_profile_ui(dose_film, dose_tps, res_mm, section_key="prof"):
    """
    Interface completa de Perfil de Dose para o Streamlit.

    Como usar no seu app:
        from dose_point_analysis import render_dose_profile_ui
        render_dose_profile_ui(dose_film, dose_tps, res_mm)
    """
    st.subheader("📈 Perfil de Dose — Comparação Filme vs TPS")

    h, w = dose_film.shape
    extent_x = w * res_mm / 2
    extent_y = h * res_mm / 2

    st.info(
        f"Defina dois pontos A e B para extrair o perfil. "
        f"O mapa tem {w * res_mm:.0f} × {h * res_mm:.0f} mm "
        f"(de -{extent_x:.0f} a +{extent_x:.0f} mm em X, "
        f"de -{extent_y:.0f} a +{extent_y:.0f} mm em Y)."
    )

    # ── Tipo de perfil ─────────────────────────────────────────────────────
    tipo_perfil = st.radio(
        "Tipo de perfil",
        ["Horizontal (Crossline)", "Vertical (Inline)", "Diagonal (livre)"],
        horizontal=True,
        key=f"tipo_{section_key}"
    )

    col1, col2 = st.columns(2)

    if tipo_perfil == "Horizontal (Crossline)":
        with col1:
            y_mm = st.number_input("Posição Y (mm)", value=0.0, step=1.0,
                                   min_value=-extent_y, max_value=extent_y,
                                   key=f"y_cross_{section_key}")
        x_start_mm = -extent_x * 0.9
        x_end_mm = extent_x * 0.9
        y_start_mm = y_mm
        y_end_mm = y_mm
        label = f"Crossline Y={y_mm:.0f}mm"

    elif tipo_perfil == "Vertical (Inline)":
        with col1:
            x_mm = st.number_input("Posição X (mm)", value=0.0, step=1.0,
                                   min_value=-extent_x, max_value=extent_x,
                                   key=f"x_inline_{section_key}")
        x_start_mm = x_mm
        x_end_mm = x_mm
        y_start_mm = extent_y * 0.9
        y_end_mm = -extent_y * 0.9
        label = f"Inline X={x_mm:.0f}mm"

    else:  # Diagonal
        with col1:
            st.markdown("**Ponto A (início)**")
            x_start_mm = st.number_input("A — X (mm)", value=-extent_x * 0.8, step=1.0,
                                         key=f"xa_{section_key}")
            y_start_mm = st.number_input("A — Y (mm)", value=0.0, step=1.0,
                                         key=f"ya_{section_key}")
        with col2:
            st.markdown("**Ponto B (fim)**")
            x_end_mm = st.number_input("B — X (mm)", value=extent_x * 0.8, step=1.0,
                                       key=f"xb_{section_key}")
            y_end_mm = st.number_input("B — Y (mm)", value=0.0, step=1.0,
                                       key=f"yb_{section_key}")
        label = f"Diagonal A({x_start_mm:.0f},{y_start_mm:.0f})→B({x_end_mm:.0f},{y_end_mm:.0f})"

    n_pts = st.slider("Resolução do perfil (pontos)", 200, 1000, 500, 50,
                      key=f"npts_{section_key}")

    # ── Calcular ───────────────────────────────────────────────────────────
    if st.button("📈 Extrair Perfil", type="primary", key=f"btn_{section_key}"):
        with st.spinner("Extraindo perfil..."):
            origin = (0.0, 0.0)

            dist_film, dose_prof_film = extract_profile_mm(
                dose_film, x_start_mm, y_start_mm, x_end_mm, y_end_mm,
                res_mm, origin, n_pts
            )
            dist_tps, dose_prof_tps = extract_profile_mm(
                dose_tps, x_start_mm, y_start_mm, x_end_mm, y_end_mm,
                res_mm, origin, n_pts
            )

        # ── Visualização ──────────────────────────────────────────────────
        col_mapa, col_perf = st.columns([1, 2])

        with col_mapa:
            fig_line = plot_profile_line_on_map(
                dose_film, x_start_mm, y_start_mm, x_end_mm, y_end_mm,
                res_mm, origin
            )
            st.pyplot(fig_line, use_container_width=True)
            plt.close(fig_line)

        with col_perf:
            fig_prof = plot_dose_profiles(
                dist_film, dose_prof_film,
                dist_tps, dose_prof_tps,
                profile_label=label,
                res_mm=res_mm,
            )
            st.pyplot(fig_prof, use_container_width=True)
            plt.close(fig_prof)

        # ── Métricas do perfil ────────────────────────────────────────────
        doses_norm = dose_prof_film / np.max(dose_prof_film) * 100

        fs, left_e, right_e = compute_field_size(dist_film, doses_norm)
        p_left, p_right = compute_penumbra(dist_film, doses_norm)

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Tamanho do Campo (50%)",
                      f"{fs:.1f} mm" if fs else "N/A",
                      delta=f"Esperado: {abs(x_end_mm - x_start_mm) * 0.9:.0f} mm" if tipo_perfil != "Diagonal (livre)" else None)
        col_m2.metric("Penumbra Esq (80-20%)", f"{p_left:.1f} mm" if p_left else "N/A")
        col_m3.metric("Penumbra Dir (80-20%)", f"{p_right:.1f} mm" if p_right else "N/A")

        # Diferença máxima entre perfis
        if len(dose_prof_film) == len(dose_prof_tps):
            film_n = dose_prof_film / np.max(dose_prof_film) * 100
            tps_n = dose_prof_tps / np.max(dose_prof_tps) * 100
            diff_max = np.max(np.abs(film_n - tps_n))
            col_m4.metric("Diferença Máx Filme vs TPS", f"{diff_max:.1f}%")

        # ── Comparação TPS: campo size ─────────────────────────────────────
        if dose_tps is not None:
            doses_tps_norm = dose_prof_tps / np.max(dose_prof_tps) * 100
            fs_tps, _, _ = compute_field_size(dist_tps, doses_tps_norm)
            if fs and fs_tps:
                diff_campo = abs(fs - fs_tps)
                if diff_campo <= 2.0:
                    st.success(f"✅ Tamanho do campo: Filme = {fs:.1f} mm | TPS = {fs_tps:.1f} mm | Diferença = {diff_campo:.1f} mm")
                else:
                    st.warning(f"⚠️ Tamanho do campo: Filme = {fs:.1f} mm | TPS = {fs_tps:.1f} mm | Diferença = {diff_campo:.1f} mm")

        # ── Download do perfil ─────────────────────────────────────────────
        df_prof = pd.DataFrame({
            'distancia_mm': dist_film,
            'dose_filme_gy': dose_prof_film,
            'dose_filme_rel': dose_prof_film / np.max(dose_prof_film) * 100,
            'dose_tps_gy': dose_prof_tps,
            'dose_tps_rel': dose_prof_tps / np.max(dose_prof_tps) * 100,
        })
        st.download_button(
            "📥 Download Perfil (CSV)",
            df_prof.to_csv(index=False),
            f"perfil_{label.replace(' ', '_')}.csv",
            "text/csv",
        )

        # Salvar para relatório
        st.session_state['dose_profile_result'] = {
            'label': label,
            'dist_film': dist_film,
            'doses_film': dose_prof_film,
            'dist_tps': dist_tps,
            'doses_tps': dose_prof_tps,
            'field_size_film': fs,
            'field_size_tps': fs_tps if dose_tps is not None else None,
            'penumbra_left': p_left,
            'penumbra_right': p_right,
        }
