"""
isodose_engine.py - Motor de Visualizacao de Curvas de Isodose

Uma curva de isodose e a linha que conecta os pontos de mesma dose no mapa 2D
(definicao classica: Niroomand-Rad/TG-55; pratica clinica de TPS). Os niveis
sao tipicamente expressos como percentual de uma dose de referencia (a dose de
prescricao ou a dose maxima/no isocentro), por exemplo 50/75/100/125/150%.

Este modulo:
  1. Recebe um mapa de dose 2D (cGy/Gy) ja reconstruido (dose_map_engine.py).
  2. Define os valores de dose de cada nivel de isodose, a partir de:
       - percentual da dose de PRESCRICAO informada pelo usuario, OU
       - percentual da dose MAXIMA do proprio filme, OU
       - valores ABSOLUTOS (cGy/Gy) informados diretamente.
  3. Renderiza as curvas sobre o mapa de dose (matplotlib.contour), com cores
     clinicas por nivel e estilo de linha continuo ou tracejado.

NADA de atalhos: as curvas sao os contornos reais de iso-nivel do campo escalar
de dose, exatamente como em qualquer TPS. A comparacao quantitativa com o TPS
(coeficiente de Dice/Jaccard entre regioes) sera adicionada em modulo proprio.
"""

import numpy as np

# Cores clinicas convencionais por nivel de isodose (%).
# Frias (azul) nas doses baixas -> quentes (vermelho) nas doses altas,
# convencao comum em planejamento. Niveis fora desta tabela recebem cor
# atribuida automaticamente pela paleta.
CLINICAL_ISODOSE_COLORS = {
    30:  "#2166ac",   # azul
    50:  "#4393c3",   # azul claro
    75:  "#2ca02c",   # verde
    90:  "#bcbd22",   # amarelo-esverdeado
    95:  "#e6c200",   # amarelo
    100: "#d62728",   # vermelho (dose de referencia)
    105: "#e377c2",   # rosa
    110: "#ff7f0e",   # laranja
    125: "#9467bd",   # roxo
    150: "#8c564b",   # marrom
}

# Niveis clinicos padrao (editaveis pelo usuario na interface).
DEFAULT_CLINICAL_LEVELS = [50, 75, 100, 125, 150]


def color_for_level(pct, fallback_index=0):
    """Retorna a cor clinica de um nivel (%). Se nao houver na tabela, gera uma."""
    if pct in CLINICAL_ISODOSE_COLORS:
        return CLINICAL_ISODOSE_COLORS[pct]
    # Cor automatica estavel para niveis nao tabelados.
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    return palette[fallback_index % len(palette)]


def resolve_isodose_values(dose_map, levels, basis="prescription",
                           prescription_dose=None):
    """
    Converte a lista de niveis em valores de dose absolutos (na unidade do mapa).

    Args:
        dose_map: matriz 2D de dose (cGy ou Gy).
        levels: lista de niveis. Se basis e percentual, sao % (ex: [50,75,100]);
                se basis == "absolute", sao valores de dose ja na unidade do mapa.
        basis: "prescription" (% da Rx), "max" (% da dose maxima do filme),
               ou "absolute" (os proprios valores).
        prescription_dose: dose de prescricao (mesma unidade do mapa); obrigatorio
               quando basis == "prescription".

    Returns:
        lista de tuplas (rotulo, valor_de_dose), ordenada por valor crescente.
        O rotulo e o que sera exibido (ex: "100%" ou "1000 cGy").
    """
    pairs = []
    if basis == "absolute":
        for v in levels:
            v = float(v)
            pairs.append((f"{v:g}", v))
    elif basis == "max":
        # Usa o percentil 99 como referencia (evita outliers/artefatos), mesma
        # convencao do dose_map_engine para o modo percentual.
        ref = float(np.nanpercentile(dose_map, 99))
        ref = max(ref, 1e-6)
        for p in levels:
            pairs.append((f"{p:g}%", ref * (float(p) / 100.0)))
    else:  # "prescription"
        if prescription_dose is None:
            raise ValueError("prescription_dose e obrigatorio quando basis='prescription'.")
        ref = max(float(prescription_dose), 1e-6)
        for p in levels:
            pairs.append((f"{p:g}%", ref * (float(p) / 100.0)))

    # Remove niveis fora da faixa de dose presente no mapa (nao ha curva possivel).
    dmin = float(np.nanmin(dose_map))
    dmax = float(np.nanmax(dose_map))
    valid = [(lbl, val) for (lbl, val) in pairs if dmin <= val <= dmax]

    valid.sort(key=lambda x: x[1])
    return valid


def render_isodose_png(dose_map, levels, basis="prescription",
                       prescription_dose=None, level_pcts=None,
                       unit="cGy", lang="pt", theme="dark",
                       linestyle="solid", colormap="jet",
                       show_background=True, title=None,
                       smooth_sigma=0.0):
    """
    Renderiza as curvas de isodose sobre o mapa de dose. Retorna bytes PNG.

    smooth_sigma: desvio-padrao (em pixels) de um filtro gaussiano aplicado
      APENAS para extrair as curvas, reduzindo o ruido de alta frequencia que
      deixa as isodoses rendilhadas (comum em mapas de dose de grade grossa
      interpolada). 0 = sem suavizacao. Um valor pequeno (0.5-1.5) limpa as
      curvas sem deslocar as bordas de forma perceptivel. O heatmap de fundo
      continua mostrando o dado ORIGINAL (a suavizacao nao altera a dose).
    """
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as _np

    if theme == "dark":
        bg, fg = "#0d1117", "#e6edf3"
    else:
        bg, fg = "#ffffff", "#1e293b"

    if title is None:
        title = "Curvas de Isodose" if lang == "pt" else "Isodose Curves"

    ls = "--" if linestyle in ("dashed", "--", "tracejada") else "-"

    pairs = resolve_isodose_values(dose_map, levels, basis, prescription_dose)

    # Mapa usado para EXTRAIR as curvas (opcionalmente suavizado).
    dose_for_contour = dose_map
    if smooth_sigma and smooth_sigma > 0:
        try:
            from scipy.ndimage import gaussian_filter
            dose_for_contour = gaussian_filter(dose_map, sigma=float(smooth_sigma))
        except Exception:
            dose_for_contour = dose_map

    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=100)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    # Fundo: heatmap do mapa de dose ORIGINAL (sem suavizar), com a paleta.
    if show_background:
        im = ax.imshow(dose_map, cmap=colormap, origin="upper")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(f"Dose ({unit})", color=fg)
        cbar.ax.yaxis.set_tick_params(color=fg)
        plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=fg)

    # Curvas de isodose: um contorno por nivel, com a cor clinica do nivel.
    handles, labels = [], []
    for idx, (lbl, val) in enumerate(pairs):
        if level_pcts is not None and idx < len(level_pcts):
            try:
                pct_int = int(round(float(level_pcts[idx])))
            except Exception:
                pct_int = None
            color = color_for_level(pct_int, idx) if pct_int is not None else color_for_level(-1, idx)
        elif basis in ("prescription", "max"):
            try:
                pct_int = int(round(float(levels[idx])))
                color = color_for_level(pct_int, idx)
            except Exception:
                color = color_for_level(-1, idx)
        else:
            color = color_for_level(-1, idx)

        ax.contour(dose_for_contour, levels=[val], colors=[color],
                   linewidths=1.8, linestyles=ls, origin="upper")
        from matplotlib.lines import Line2D
        handles.append(Line2D([0], [0], color=color, lw=1.8, linestyle=ls))
        labels.append(f"{lbl}  ({val:.0f} {unit})")

    ax.set_title(title, color=fg, fontsize=12, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])

    if handles:
        leg = ax.legend(handles, labels, loc="upper right", fontsize=8,
                        framealpha=0.85, facecolor=bg, edgecolor=fg,
                        labelcolor=fg, title="Isodoses")
        if leg and leg.get_title():
            leg.get_title().set_color(fg)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()


def isodose_summary(dose_map, levels, basis="prescription",
                    prescription_dose=None, res_mm=None):
    """
    Resumo textual: para cada nivel, o valor de dose e a area contida
    (pixels com dose >= valor), opcionalmente convertida para cm^2.

    Args:
        res_mm: mm/pixel; se informado, calcula area em cm^2.

    Returns:
        lista de dicts: {label, dose_value, n_pixels, area_cm2 (ou None)}.
    """
    pairs = resolve_isodose_values(dose_map, levels, basis, prescription_dose)
    out = []
    for lbl, val in pairs:
        mask = dose_map >= val
        n_px = int(np.count_nonzero(mask))
        area_cm2 = None
        if res_mm:
            area_cm2 = n_px * (float(res_mm) / 10.0) ** 2  # (mm->cm)^2
        out.append({
            "label": lbl,
            "dose_value": float(val),
            "n_pixels": n_px,
            "area_cm2": area_cm2,
        })
    return out
