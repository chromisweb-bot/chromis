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
                         lang="pt", theme="dark", dpi=150,
                         lateral_depth_y_mm=None, show_points=True):
    """
    Gera os perfis de dose com a geometria FISICA correta para um filme
    irradiado com o feixe entrando ao longo de Y (gantry 0):

      - PDD (dose vs Y / profundidade): tirado no EIXO CENTRAL do campo, isto e,
        no (X,Z) onde a dose lateral e maxima. Mostra o decaimento em profundidade.
      - Perfil lateral X (dose vs X): tirado na PROFUNDIDADE do campo de interesse
        (por padrao, a profundidade Y do ponto de referencia / DMAX), onde o campo
        e o 5x5 que se quer avaliar — NAO na profundidade do R0.
      - Perfil lateral Z (dose vs Z): idem, na mesma profundidade. Se a curva nao
        cair ate ~0 nas bordas, avisa que o volume de dose esta truncado em Z.

    Assim cada perfil passa pelo lugar fisicamente correto, em vez de todos
    cruzarem o mesmo ponto.

    Parametros:
      ref_point: ponto de referencia (define a profundidade dos laterais e marca
                 a posicao nos graficos). Tipicamente o DMAX.
      lateral_depth_y_mm: profundidade Y (mm) dos perfis laterais. Se None, usa a
                 profundidade do ref_point.
      show_points: se True e points for dado, sobrepoe os pontos nos perfis.
    Retorna bytes PNG.
    """
    vol = dose_volume_gy
    if vol.ndim == 2:
        vol = vol[np.newaxis, :, :]
    nk, ni, nj = vol.shape

    ox, oy, oz = geometry["origin_mm"]
    row_sp, col_sp = geometry["pixel_spacing_mm"][0], geometry["pixel_spacing_mm"][1]
    gfov = list(geometry.get("grid_frame_offset", [0.0]))
    spacing_z = (gfov[1] - gfov[0]) if len(gfov) > 1 else max(row_sp, 1.0)

    is_pt = lang == "pt"
    if theme == "dark":
        bg, fg = "#0d1117", "#e6edf3"
    else:
        bg, fg = "#ffffff", "#1e293b"

    refname = ref_point.get("name", "ref")
    rx, ry, rz = ref_point["x_mm"], ref_point["y_mm"], ref_point["z_mm"]

    # ── EIXO CENTRAL = o ponto de referencia escolhido pelo usuario (ex: R0) ─
    # O PDD passa pelo (X,Z) do ponto de referencia; nao pelo pixel mais quente
    # (que e sensivel a ruido e pode cair fora do centro real do campo).
    x_central = rx
    z_central = rz
    j_cen = int(round((x_central - ox) / col_sp)); j_cen = max(0, min(j_cen, nj - 1))
    k_cen = int(round((z_central - oz) / spacing_z)) if spacing_z else 0
    k_cen = max(0, min(k_cen, nk - 1))

    # Profundidade dos perfis laterais (Y): padrao = a do ref_point
    if lateral_depth_y_mm is None:
        lateral_depth_y_mm = ry
    i_lat = int(round((lateral_depth_y_mm - oy) / row_sp)); i_lat = max(0, min(i_lat, ni - 1))

    n_panels = 3
    fig, axes = plt.subplots(1, n_panels, figsize=(18, 5), dpi=dpi)
    fig.patch.set_facecolor(bg)

    def _overlay_points(ax, axis, fixed_tol_mm=8.0):
        """Sobrepoe pontos cujos OUTROS eixos batem com o perfil (tolerancia)."""
        if not (show_points and points):
            return
        for p in points:
            if str(p.get("name", "")).lower() == "patient":
                continue
            d = p.get("tps_dose_gy")
            if d is None or p.get("x_mm") is None:
                continue
            if axis == "Y":   # PDD no eixo central: pontos com X,Z ~ central
                if abs(p["x_mm"] - x_central) <= fixed_tol_mm and abs(p["z_mm"] - z_central) <= fixed_tol_mm:
                    ax.plot(p["y_mm"], d, "o", color="#ffd166", markersize=6,
                            markeredgecolor="#b8860b", zorder=10)
                    ax.annotate(p["name"], (p["y_mm"], d), fontsize=6, color=fg,
                                xytext=(4, 3), textcoords="offset points")
            elif axis == "X":  # lateral em X: pontos na profundidade Y_lat e Z central
                if abs(p["y_mm"] - lateral_depth_y_mm) <= fixed_tol_mm and abs(p["z_mm"] - z_central) <= fixed_tol_mm:
                    ax.plot(p["x_mm"], d, "o", color="#ffd166", markersize=6,
                            markeredgecolor="#b8860b", zorder=10)
                    ax.annotate(p["name"], (p["x_mm"], d), fontsize=6, color=fg,
                                xytext=(4, 3), textcoords="offset points")
            elif axis == "Z":  # lateral em Z: pontos na profundidade Y_lat e X central
                if abs(p["y_mm"] - lateral_depth_y_mm) <= fixed_tol_mm and abs(p["x_mm"] - x_central) <= fixed_tol_mm:
                    ax.plot(p["z_mm"], d, "o", color="#ffd166", markersize=6,
                            markeredgecolor="#b8860b", zorder=10)
                    ax.annotate(p["name"], (p["z_mm"], d), fontsize=6, color=fg,
                                xytext=(4, 3), textcoords="offset points")

    # ── 1) PDD: dose vs Y, no eixo central = (X,Z) do ponto de referencia ───
    pdd = vol[k_cen, :, j_cen]
    y_coords = [oy + i * row_sp for i in range(ni)]
    axes[0].plot(y_coords, pdd, color="#5fd35f", lw=1.7)
    axes[0].axvline(ry, color="#ff5555", ls="--", alpha=0.85, lw=1.3,
                    label=f"{refname} (Y={ry:.1f} mm)")
    axes[0].set_title(("PDD — dose × profundidade" if is_pt else "PDD — dose vs depth")
                      + f"\n({'eixo central' if is_pt else 'central axis'} = {refname}: "
                      + f"X={x_central:.1f}, Z={z_central:.1f} mm)",
                      color=fg, fontsize=10)
    axes[0].set_xlabel("Y DICOM (mm) — " + ("profundidade" if is_pt else "depth"), color=fg)
    axes[0].set_ylabel("Dose (Gy)", color=fg)
    axes[0].legend(loc="best", fontsize=8, framealpha=0.85, facecolor=bg,
                   edgecolor=fg, labelcolor=fg)
    _overlay_points(axes[0], "Y")

    # ── 2) Lateral X: dose vs X, na profundidade Y_lat e Z central ──────────
    latx = vol[k_cen, i_lat, :]
    x_coords = [ox + j * col_sp for j in range(nj)]
    axes[1].plot(x_coords, latx, color="#4da3ff", lw=1.7)
    axes[1].axvline(x_central, color="#ff5555", ls="--", alpha=0.85, lw=1.3,
                    label=f"{refname} (X={x_central:.1f} mm)")
    axes[1].set_title(("Perfil lateral X" if is_pt else "Lateral profile X")
                      + f"\n(profundidade Y={lateral_depth_y_mm:.1f} mm)",
                      color=fg, fontsize=10)
    axes[1].set_xlabel("X DICOM (mm) — " + ("lateral" if is_pt else "lateral"), color=fg)
    axes[1].set_ylabel("Dose (Gy)", color=fg)
    axes[1].legend(loc="best", fontsize=8, framealpha=0.85, facecolor=bg,
                   edgecolor=fg, labelcolor=fg)
    _overlay_points(axes[1], "X")

    # ── 3) Lateral Z: dose vs Z, na profundidade Y_lat e X central ──────────
    latz = vol[:, i_lat, j_cen]
    z_coords = [oz + (gfov[k] if k < len(gfov) else k * spacing_z) for k in range(nk)]
    axes[2].plot(z_coords, latz, color="#ff6b6b", lw=1.7)
    axes[2].axvline(z_central, color="#ff5555", ls="--", alpha=0.85, lw=1.3,
                    label=f"{refname} (Z={z_central:.1f} mm)")
    axes[2].set_title(("Perfil lateral Z" if is_pt else "Lateral profile Z")
                      + f"\n(profundidade Y={lateral_depth_y_mm:.1f} mm)",
                      color=fg, fontsize=10)
    axes[2].set_xlabel("Z DICOM (mm) — " + ("lateral" if is_pt else "lateral"), color=fg)
    axes[2].set_ylabel("Dose (Gy)", color=fg)
    axes[2].legend(loc="best", fontsize=8, framealpha=0.85, facecolor=bg,
                   edgecolor=fg, labelcolor=fg)
    _overlay_points(axes[2], "Z")

    # Aviso de truncamento em Z: se as bordas nao chegam perto de 0.
    if latz.size > 4:
        edge = max(latz[0], latz[-1])
        peak = latz.max()
        if peak > 0 and edge > 0.15 * peak:
            msg = ("⚠ Perfil Z truncado: o volume de dose do TPS nao se estende o "
                   "suficiente em Z para a dose cair a zero nas bordas."
                   if is_pt else
                   "⚠ Z profile truncated: TPS dose volume does not extend far "
                   "enough in Z for the dose to reach zero at the edges.")
            axes[2].text(0.5, -0.22, msg, transform=axes[2].transAxes,
                         ha="center", va="top", fontsize=7.5, color="#ffb454", wrap=True)

    for ax in axes:
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelsize=8)
        ax.grid(True, alpha=0.2)
        for sp in ax.spines.values():
            sp.set_color(fg)

    sup = (f"Perfis de Dose — eixo central do campo (ref.: {refname})" if is_pt
           else f"Dose profiles — field central axis (ref.: {refname})")
    fig.suptitle(sup, color=fg, fontsize=13, fontweight="bold")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
