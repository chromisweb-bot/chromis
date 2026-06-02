"""curve_plot.py - Grafico da curva de calibracao (PNG) com tema e idioma."""
import io
import numpy as np

# Textos do grafico por idioma
_TXT = {
    "title": {"pt": "Curva de Calibracao", "en": "Calibration Curve"},
    "xlabel": {"pt": "NOD (densidade optica liquida)", "en": "NOD (net optical density)"},
    "ylabel": {"pt": "Dose", "en": "Dose"},
    "fitted": {"pt": "Curva ajustada", "en": "Fitted curve"},
    "measured": {"pt": "Pontos medidos", "en": "Measured points"},
}


def make_calibration_plot(nods, doses, model_obj, unit="cGy", orders=None,
                          theme="dark", lang="pt"):
    """
    Gera PNG do grafico NOD x Dose. theme: 'dark' ou 'light'. lang: 'pt'/'en'.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nods = np.asarray(nods, dtype=float)
    doses = np.asarray(doses, dtype=float)

    # Cores por tema
    if theme == "dark":
        bg = "#0d1117"; fg = "#e6edf3"; grid = "#30363d"
        curve_c = "#58a6ff"; point_c = "#3fb950"; title_c = "#3fb950"
    else:
        bg = "#ffffff"; fg = "#1e293b"; grid = "#dddddd"
        curve_c = "#1f6feb"; point_c = "#2e9e5b"; title_c = "#1a7f4e"

    def tr(k):
        return _TXT[k][lang]

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from calibration import predict_dose
        xs = np.linspace(float(nods.min()), float(nods.max()), 100)
        ys = predict_dose(model_obj, xs)
        ax.plot(xs, ys, "-", color=curve_c, linewidth=2, label=tr("fitted"), zorder=1)
    except Exception:
        pass

    ax.scatter(nods, doses, color=point_c, s=55, zorder=3,
               edgecolors=bg, linewidths=1.2, label=tr("measured"))

    for i, (n, d) in enumerate(zip(nods, doses)):
        lbl = "#%d" % (orders[i] + 1 if orders else i + 1)
        ax.annotate(f"{lbl}\n{d:.0f} {unit}", (n, d),
                    textcoords="offset points", xytext=(8, 6),
                    fontsize=8, color=fg)

    ax.set_xlabel(tr("xlabel"), fontsize=10, color=fg)
    ax.set_ylabel(f"{tr('ylabel')} ({unit})", fontsize=10, color=fg)
    ax.set_title(tr("title"), fontsize=11, color=title_c, fontweight="bold")
    ax.grid(True, alpha=0.25, linestyle="--", color=grid)
    ax.tick_params(colors=fg)
    for spine in ax.spines.values():
        spine.set_color(grid)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    leg = ax.legend(fontsize=8, loc="upper left", facecolor=bg, edgecolor=grid)
    for txt in leg.get_texts():
        txt.set_color(fg)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
