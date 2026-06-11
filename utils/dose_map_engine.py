"""
dose_map_engine.py - Reconstrucao do mapa de dose 2D a partir do filme.

Metodo (padrao da literatura - Devic, Micke, Lewis):
  1. Para cada pixel do filme irradiado, calcula netOD = log10(PV0 / PV)
     usando o canal vermelho e o PV0 do filme de dose zero.
  2. Aplica a curva de calibracao (modelo ajustado) em cada pixel:
     Dose(x,y) = f(netOD(x,y)).
  3. Retorna a matriz 2D de dose (em cGy ou Gy).

Robustez: opera em qualquer recorte de filme; trata PV invalidos; permite
um leve blur opcional para reduzir ruido de scanner (mediana).
"""

import numpy as np


def _red_channel(image):
    """Extrai o canal vermelho como float."""
    img = np.asarray(image)
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = img[:, :, :3]
        red = img[:, :, 0].astype(np.float64)
    else:
        red = img.astype(np.float64)
    return red


def compute_dose_map(film_image, pv_zero, model_obj, denoise=True,
                     normalize=None, edge_margin_px=0):
    """
    Converte um recorte de filme irradiado em mapa de dose.

    Args:
        film_image: recorte RGB (ou cinza) do filme irradiado.
        pv_zero: valor de pixel (canal vermelho) do filme de dose zero.
        model_obj: CalibrationModel ajustado (calibration.py).
        denoise: se True, aplica filtro de mediana leve para reduzir ruido.
        normalize: None = dose absoluta; "max" = % da dose maxima;
                   um numero = % em relacao a esse valor de referencia.
        edge_margin_px: margem (px) EXCLUIDA nas 4 bordas do filme. A borda
                   cortada do filme tem uma sombra escura no scan que vira
                   "dose" falsa altissima e contamina maximo/percentis
                   (pratica padrao: Dosepy/OMG analisam DENTRO do filme).
                   Os pixels excluidos viram NaN no mapa.

    Returns:
        dict com dose_map (absoluta), netod_map, dose_min/max/mean,
        e se normalize for usado: dose_map_pct, ref_dose, mode.
    """
    from calibration import predict_dose

    red = _red_channel(film_image)

    if denoise:
        try:
            from scipy.ndimage import median_filter
            red = median_filter(red, size=3)
        except Exception:
            pass

    pv_zero = max(float(pv_zero), 1e-6)
    red_safe = np.clip(red, 1e-6, None)
    netod = np.log10(pv_zero / red_safe)
    netod = np.clip(netod, 0.0, None)

    flat = netod.ravel()
    dose_flat = predict_dose(model_obj, flat)
    dose_map = np.asarray(dose_flat, dtype=np.float64).reshape(netod.shape)
    dose_map = np.clip(dose_map, 0.0, None)

    # Exclui a moldura das bordas (sombra de corte do filme) -> NaN
    m = int(edge_margin_px)
    if m > 0 and dose_map.shape[0] > 2 * m + 4 and dose_map.shape[1] > 2 * m + 4:
        dose_map[:m, :] = np.nan
        dose_map[-m:, :] = np.nan
        dose_map[:, :m] = np.nan
        dose_map[:, -m:] = np.nan
        netod[:m, :] = np.nan
        netod[-m:, :] = np.nan
        netod[:, :m] = np.nan
        netod[:, -m:] = np.nan

    result = {
        "dose_map": dose_map,
        "netod_map": netod,
        "dose_min": float(np.nanmin(dose_map)),
        "dose_max": float(np.nanmax(dose_map)),
        "dose_mean": float(np.nanmean(dose_map)),
        "edge_margin_px": m,
    }

    # Mapa percentual
    if normalize is not None:
        if normalize == "max":
            # usa percentil 99 para evitar outliers/artefatos (boa pratica)
            ref = float(np.nanpercentile(dose_map, 99))
        else:
            ref = float(normalize)
        ref = max(ref, 1e-6)
        dose_pct = dose_map / ref * 100.0
        result["dose_map_pct"] = dose_pct
        result["ref_dose"] = ref
        result["pct_min"] = float(np.nanmin(dose_pct))
        result["pct_max"] = float(np.nanmax(dose_pct))
        result["pct_mean"] = float(np.nanmean(dose_pct))

    return result


def render_dose_map_png(dose_map, unit="cGy", lang="pt", theme="dark",
                        title=None, percent=False, colormap="jet"):
    """
    Renderiza o mapa de dose como imagem PNG (heatmap) com barra de cor.
    Se percent=True, o dose_map ja esta em % e a barra mostra %.
    colormap: paleta de cores do matplotlib (jet, viridis, turbo, inferno, etc).
    Retorna bytes PNG.
    """
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if theme == "dark":
        bg, fg = "#0d1117", "#e6edf3"
    else:
        bg, fg = "#ffffff", "#1e293b"

    if title is None:
        title = "Mapa de Dose" if lang == "pt" else "Dose Map"
    if percent:
        cbar_label = "Dose (%)"
    else:
        cbar_label = f"Dose ({unit})"

    fig, ax = plt.subplots(figsize=(6, 5), dpi=100)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    import matplotlib.cm as _cm
    cmap_obj = _cm.get_cmap(colormap).copy()
    cmap_obj.set_bad(color=bg)   # NaN (margem de borda excluida) = fundo

    im = ax.imshow(dose_map, cmap=cmap_obj, origin="upper")
    ax.set_title(title, color=fg, fontsize=12, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label, color=fg)
    cbar.ax.yaxis.set_tick_params(color=fg)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=fg)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
