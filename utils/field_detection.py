"""
field_detection.py — Deteccao de campo de irradiacao dentro do filme.

Distingue dois casos:
  (A) Campo = tamanho do filme: coloracao uniforme ate as bordas.
  (B) Campo < filme: regiao central mais escura (irradiada) cercada por
      borda mais clara (nao irradiada).

Tambem aplica o recuo de borda e calcula o ROI central conforme protocolo.
"""

import numpy as np
from skimage import filters, measure, morphology


def analyze_film_field(film_gray: np.ndarray, mask: np.ndarray = None,
                       uniformity_tol: float = 0.12):
    """
    Analisa um recorte de filme (em cinza) para detectar o campo irradiado.

    Args:
        film_gray: recorte 2D do filme (escala de cinza, 0..1).
        mask: mascara booleana do filme (mesmo shape). Se None, usa tudo.
        uniformity_tol: tolerancia de uniformidade. Se a diferenca entre
                        centro e borda for menor que isso, considera
                        campo = filme.

    Returns:
        dict com:
          "field_type": "full" (campo=filme) ou "smaller" (campo<filme)
          "field_bbox": bbox do campo dentro do recorte (ou None se full)
          "center_intensity", "border_intensity"
    """
    if mask is None:
        mask = np.ones_like(film_gray, dtype=bool)

    h, w = film_gray.shape

    # Define uma faixa de borda (15% externo) e uma regiao central (40% central)
    by = max(1, int(h * 0.15))
    bx = max(1, int(w * 0.15))

    # Borda: moldura externa
    border_mask = np.zeros_like(mask)
    border_mask[:by, :] = True
    border_mask[-by:, :] = True
    border_mask[:, :bx] = True
    border_mask[:, -bx:] = True
    border_mask &= mask

    # Centro: regiao central
    cy0, cy1 = int(h * 0.3), int(h * 0.7)
    cx0, cx1 = int(w * 0.3), int(w * 0.7)
    center_mask = np.zeros_like(mask)
    center_mask[cy0:cy1, cx0:cx1] = True
    center_mask &= mask

    center_int = float(np.mean(film_gray[center_mask])) if center_mask.any() else 0.0
    border_int = float(np.mean(film_gray[border_mask])) if border_mask.any() else 0.0

    # Se centro e borda tem intensidade parecida -> campo cobre o filme todo
    diff = abs(center_int - border_int)
    if diff < uniformity_tol:
        return {
            "field_type": "full",
            "field_bbox": None,
            "center_intensity": center_int,
            "border_intensity": border_int,
            "diff": diff,
        }

    # Campo menor: segmenta a regiao central mais escura
    # (centro irradiado e mais escuro = menor cinza que a borda)
    thr = (center_int + border_int) / 2.0
    field_bin = (film_gray < thr) & mask
    field_bin = morphology.remove_small_objects(field_bin, min_size=int(h * w * 0.02))
    field_bin = morphology.binary_closing(field_bin, morphology.disk(2))

    if field_bin.any():
        labels = measure.label(field_bin)
        regions = measure.regionprops(labels)
        # maior regiao = campo
        largest = max(regions, key=lambda r: r.area)
        fb = largest.bbox  # (minr,minc,maxr,maxc)
    else:
        fb = None

    return {
        "field_type": "smaller",
        "field_bbox": fb,
        "center_intensity": center_int,
        "border_intensity": border_int,
        "diff": diff,
    }


def compute_roi(film_shape, field_bbox=None, edge_recoil_mm=3.0,
                roi_percent=40.0, dpi=72, roi_size_cm=None):
    """
    Calcula o ROI central conforme protocolo.

    Args:
        film_shape: (h, w) do recorte do filme em pixels.
        field_bbox: bbox do campo (se campo<filme). Se None, usa o filme todo.
        edge_recoil_mm: recuo da borda para dentro, em mm (2,3,4,5).
        roi_percent: tamanho do ROI como % da area util (usado se roi_size_cm=None).
        dpi: resolucao do scan, para converter mm/cm->pixels.
        roi_size_cm: se informado (ex: 2.0 ou 2.5), define o ROI com tamanho
                     FIXO em cm (lado do quadrado). Tem prioridade sobre roi_percent.

    Returns:
        dict com roi_bbox, usable_bbox, recoil_px, roi_size_px, roi_mode.
    """
    h, w = film_shape
    px_per_mm = dpi / 25.4
    recoil_px = int(round(edge_recoil_mm * px_per_mm))

    if field_bbox is not None:
        minr, minc, maxr, maxc = field_bbox
    else:
        minr, minc, maxr, maxc = 0, 0, h, w

    # Aplicar recuo para dentro
    u_minr = minr + recoil_px
    u_minc = minc + recoil_px
    u_maxr = maxr - recoil_px
    u_maxc = maxc - recoil_px

    if u_maxr <= u_minr or u_maxc <= u_minc:
        u_minr, u_minc, u_maxr, u_maxc = minr, minc, maxr, maxc

    usable_h = u_maxr - u_minr
    usable_w = u_maxc - u_minc

    cy = (u_minr + u_maxr) // 2
    cx = (u_minc + u_maxc) // 2

    if roi_size_cm is not None:
        # ROI com tamanho fisico fixo (lado do quadrado em cm)
        side_px = int(round(roi_size_cm * 10.0 * px_per_mm))  # cm -> mm -> px
        # Nao deixar passar da area util
        roi_h = min(side_px, usable_h)
        roi_w = min(side_px, usable_w)
        roi_mode = f"{roi_size_cm} x {roi_size_cm} cm"
    else:
        frac = (roi_percent / 100.0) ** 0.5
        roi_h = int(usable_h * frac)
        roi_w = int(usable_w * frac)
        roi_mode = f"{roi_percent:.0f}%"

    roi_minr = cy - roi_h // 2
    roi_maxr = cy + roi_h // 2
    roi_minc = cx - roi_w // 2
    roi_maxc = cx + roi_w // 2

    return {
        "roi_bbox": (roi_minr, roi_minc, roi_maxr, roi_maxc),
        "usable_bbox": (u_minr, u_minc, u_maxr, u_maxc),
        "recoil_px": recoil_px,
        "roi_size_px": (roi_h, roi_w),
        "roi_mode": roi_mode,
    }
