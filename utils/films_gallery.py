"""films_gallery.py - Figura com filmes numerados + legenda (recuo, ROI, campo)."""
import io
import numpy as np

_TXT = {
    "film": {"pt": "Filme", "en": "Film"},
    "recoil": {"pt": "recuo", "en": "recoil"},
    "roi": {"pt": "ROI", "en": "ROI"},
    "field_full": {"pt": "campo = filme", "en": "field = film"},
    "field_smaller": {"pt": "campo < filme", "en": "field < film"},
}


def make_films_gallery(image_rgb, ordered_films, doses_map=None, unit="cGy",
                       lang="pt", theme="light", roi_info=None):
    """
    PNG com cada filme recortado, numerado e com legenda (dose, recuo, ROI, campo).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    img = np.asarray(image_rgb)
    n = len(ordered_films)
    if n == 0:
        return None

    def tr(k):
        return _TXT[k][lang]

    ncols = min(n, 4)
    nrows = (n + ncols - 1) // ncols

    bg = "#ffffff" if theme == "light" else "#0d1117"
    fg = "#1e293b" if theme == "light" else "#e6edf3"
    sub = "#475569" if theme == "light" else "#8b949e"

    fig, axes = plt.subplots(nrows, ncols, figsize=(3.0 * ncols, 3.3 * nrows), dpi=100)
    fig.patch.set_facecolor(bg)
    axes = np.array(axes).reshape(-1) if n > 1 else np.array([axes])

    for i, f in enumerate(ordered_films):
        ax = axes[i]
        minr, minc, maxr, maxc = f["bbox"]
        ax.imshow(img[minr:maxr, minc:maxc])
        ax.set_xticks([]); ax.set_yticks([])
        order = f.get("order", i)

        # Titulo: Filme #n - dose
        dose_txt = ""
        if doses_map is not None:
            dv = doses_map.get(f"dose_{order}")
            if dv is not None:
                dose_txt = f" - {dv:.0f} {unit}"
        ax.set_title(f"{tr('film')} #{order+1}{dose_txt}", fontsize=11, color=fg,
                     fontweight="bold", pad=6)

        # Legenda embaixo: recuo, ROI, campo
        ri = (roi_info or {}).get(order, {})
        parts = []
        if ri.get("recoil_mm") is not None:
            parts.append(f"{tr('recoil')} {ri['recoil_mm']}mm")
        if ri.get("roi_mode"):
            parts.append(f"{tr('roi')} {ri['roi_mode']}")
        if ri.get("field_type"):
            parts.append(tr("field_full") if ri["field_type"] == "full" else tr("field_smaller"))
        if parts:
            ax.set_xlabel(" · ".join(parts), fontsize=8, color=sub)

        for spine in ax.spines.values():
            spine.set_color("#3fb950"); spine.set_linewidth(2)

    for j in range(n, len(axes)):
        axes[j].axis("off")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
