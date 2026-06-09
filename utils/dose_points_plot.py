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


def render_dose_profiles(dose_volume_gy, geometry, ref_point, points=None,
                         lang="pt", theme="dark", dpi=150):
    """
    Gera os 3 perfis de dose (horizontal X, vertical Y, profundidade Z) que
    passam por um ponto de referencia (ex: DMAX), com os demais pontos marcados.

    dose_volume_gy: volume 3D (n_slices, rows, cols) em Gy.
    geometry: origin_mm, pixel_spacing_mm [row_sp,col_sp], grid_frame_offset.
    ref_point: dict com x_mm,y_mm,z_mm (ponto de referencia, ex: DMAX).
    points: lista de pontos para marcar nos perfis (opcional).
    Retorna bytes PNG.
    """
    vol = dose_volume_gy
    if vol.ndim == 2:
        vol = vol[np.newaxis, :, :]
    nk, ni, nj = vol.shape

    ox, oy, oz = geometry["origin_mm"]
    row_sp, col_sp = geometry["pixel_spacing_mm"][0], geometry["pixel_spacing_mm"][1]
    gfov = list(geometry.get("grid_frame_offset", [0.0]))
    spacing_z = (gfov[1]-gfov[0]) if len(gfov) > 1 else max(row_sp, 1.0)

    # indices do ponto de referencia
    jx = int(round((ref_point["x_mm"]-ox)/col_sp)); jx = max(0, min(jx, nj-1))
    iy = int(round((ref_point["y_mm"]-oy)/row_sp)); iy = max(0, min(iy, ni-1))
    kz = int(round((ref_point["z_mm"]-oz)/spacing_z)) if spacing_z else 0
    kz = max(0, min(kz, nk-1))

    if theme == "dark":
        bg, fg = "#0d1117", "#e6edf3"
    else:
        bg, fg = "#ffffff", "#1e293b"

    fig, axes = plt.subplots(1, 3, figsize=(18, 5), dpi=dpi)
    fig.patch.set_facecolor(bg)

    refname = ref_point.get("name", "ref")

    # Perfil X (horizontal): varia coluna j, fixa i=iy, k=kz
    perfil_x = vol[kz, iy, :]
    x_coords = [ox + j*col_sp for j in range(nj)]
    axes[0].plot(x_coords, perfil_x, color="#4da3ff", lw=1.6)
    axes[0].axvline(ref_point["x_mm"], color="#ff5555", ls="--", alpha=0.7)
    axes[0].set_title(f"Perfil Horizontal (Y={ref_point['y_mm']:.1f} mm)" if lang=="pt"
                      else f"Horizontal profile (Y={ref_point['y_mm']:.1f} mm)",
                      color=fg, fontsize=11)
    axes[0].set_xlabel("X (mm)", color=fg); axes[0].set_ylabel("Dose (Gy)", color=fg)

    # Perfil Y (vertical): varia linha i, fixa j=jx, k=kz
    perfil_y = vol[kz, :, jx]
    y_coords = [oy + i*row_sp for i in range(ni)]
    axes[1].plot(y_coords, perfil_y, color="#5fd35f", lw=1.6)
    axes[1].axvline(ref_point["y_mm"], color="#ff5555", ls="--", alpha=0.7)
    axes[1].set_title(f"Perfil Vertical (X={ref_point['x_mm']:.1f} mm)" if lang=="pt"
                      else f"Vertical profile (X={ref_point['x_mm']:.1f} mm)",
                      color=fg, fontsize=11)
    axes[1].set_xlabel("Y (mm)", color=fg); axes[1].set_ylabel("Dose (Gy)", color=fg)

    # Perfil Z (profundidade): varia fatia k, fixa i=iy, j=jx
    perfil_z = vol[:, iy, jx]
    z_coords = [oz + (gfov[k] if k < len(gfov) else k*spacing_z) for k in range(nk)]
    axes[2].plot(z_coords, perfil_z, color="#ff6b6b", lw=1.6)
    axes[2].axvline(ref_point["z_mm"], color="#ff5555", ls="--", alpha=0.7)
    axes[2].set_title(f"Perfil em Profundidade" if lang=="pt" else "Depth profile",
                      color=fg, fontsize=11)
    axes[2].set_xlabel("Z (mm)", color=fg); axes[2].set_ylabel("Dose (Gy)", color=fg)

    for ax in axes:
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelsize=8)
        ax.grid(True, alpha=0.2)
        for sp in ax.spines.values():
            sp.set_color(fg)

    sup = f"Perfis de Dose - Referencia: {refname}" if lang=="pt" else f"Dose profiles - Reference: {refname}"
    fig.suptitle(sup, color=fg, fontsize=13, fontweight="bold")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
