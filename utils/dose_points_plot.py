"""dose_points_plot.py - Mapa de dose do TPS com os pontos do filme sobrepostos.

Renderiza, em alta qualidade, a fatia de dose que contem os pontos marcados no
filme (ex: DMAX6MV, I41...), com cada ponto plotado em sua posicao fisica real
(X,Y em mm) e rotulado com nome e dose. Usa coordenadas fisicas (extent), de
modo que os pontos caem exatamente sobre o mapa.
"""
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render_dose_map_with_points(dose_2d_cgy, geometry, points_in_slice,
                                lang="pt", theme="dark", colormap="jet",
                                title=None, smooth_sigma=0.0,
                                show_isodoses=True, level_pcts=(50, 75, 100),
                                label_points=True, dpi=160):
    """
    dose_2d_cgy: matriz 2D de dose (cGy) da fatia escolhida.
    geometry: dict com origin_mm [ox,oy,oz] e pixel_spacing_mm [row_sp, col_sp].
    points_in_slice: lista de dicts com name, x_mm, y_mm, tps_dose_gy (ou dose).
    Retorna bytes PNG de alta qualidade.
    """
    if theme == "dark":
        bg, fg, edge = "#0d1117", "#e6edf3", "white"
    else:
        bg, fg, edge = "#ffffff", "#1e293b", "black"

    if title is None:
        title = "Mapa de dose com pontos" if lang == "pt" else "Dose map with points"

    ox, oy = geometry["origin_mm"][0], geometry["origin_mm"][1]
    row_sp, col_sp = geometry["pixel_spacing_mm"][0], geometry["pixel_spacing_mm"][1]
    rows, cols = dose_2d_cgy.shape

    # Extensao fisica real (mm): X = colunas, Y = linhas
    x_min = ox
    x_max = ox + cols * col_sp
    y_min = oy
    y_max = oy + rows * row_sp

    dmax = float(np.nanmax(dose_2d_cgy)) if dose_2d_cgy.size else 1.0

    fig, ax = plt.subplots(figsize=(8, 7), dpi=dpi)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    # extent: [esquerda, direita, baixo, cima]. origin='upper' + y_max..y_min
    # mantem a orientacao anatomica (Y cresce para baixo no paciente).
    im = ax.imshow(dose_2d_cgy, cmap=colormap, aspect="equal",
                   extent=[x_min, x_max, y_max, y_min],
                   vmin=0, vmax=dmax)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Dose (cGy)", color=fg)
    cbar.ax.yaxis.set_tick_params(color=fg)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=fg)

    # Isodoses (extraidas de mapa opcionalmente suavizado)
    if show_isodoses and dmax > 0:
        dose_for_contour = dose_2d_cgy
        if smooth_sigma and smooth_sigma > 0:
            try:
                from scipy.ndimage import gaussian_filter
                dose_for_contour = gaussian_filter(dose_2d_cgy, sigma=float(smooth_sigma))
            except Exception:
                pass
        levels = [p/100.0*dmax for p in level_pcts if 0 < p/100.0*dmax < dmax]
        if levels:
            cs = ax.contour(dose_for_contour, levels=levels, colors=edge,
                            linewidths=1.0, alpha=0.7,
                            extent=[x_min, x_max, y_max, y_min], origin="upper")
            try:
                ax.clabel(cs, inline=True, fontsize=7,
                          fmt=lambda v: f"{v/dmax*100:.0f}%")
            except Exception:
                pass

    # Pontos do filme sobre o mapa
    if points_in_slice:
        cmap_pts = plt.cm.tab20(np.linspace(0, 1, 20))
        for idx, p in enumerate(points_in_slice):
            x, y = p.get("x_mm"), p.get("y_mm")
            if x is None or y is None:
                continue
            nm = p.get("name", "?")
            # nao plota o contorno do corpo ("patient")
            if str(nm).lower() == "patient":
                continue
            dose_val = p.get("tps_dose_gy")
            cor = cmap_pts[idx % 20]
            ax.plot(x, y, "o", color=cor, markersize=7,
                    markeredgecolor=edge, markeredgewidth=1.2, zorder=10)
            if label_points:
                lbl = nm
                if dose_val is not None:
                    lbl = f"{nm}\n{dose_val*100:.0f}"
                ax.annotate(lbl, (x, y), textcoords="offset points",
                            xytext=(6, 5), fontsize=6.5, color=fg,
                            fontweight="bold", zorder=11,
                            bbox=dict(boxstyle="round,pad=0.2",
                                      facecolor=bg, edgecolor=cor, alpha=0.85))

    ax.set_title(title, color=fg, fontsize=13, fontweight="bold")
    ax.set_xlabel("X (mm)", color=fg, fontsize=10)
    ax.set_ylabel("Y (mm)", color=fg, fontsize=10)
    ax.tick_params(colors=fg, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(fg)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
