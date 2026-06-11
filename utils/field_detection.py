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
                       uniformity_tol: float = None):
    """
    Analisa um recorte de filme (cinza 0..1) e detecta o campo irradiado.

    v2 — criterio ADAPTATIVO (corrige a versao antiga, que so detectava campo
    menor em filmes de dose alta):
      1. Otsu DENTRO do filme separa a regiao escura (campo) da clara (borda
         nao irradiada).
      2. A separacao entre as classes precisa superar o ruido interno
         (>= 1.5x o desvio-padrao medio das classes) e um minimo absoluto
         pequeno (0.02) — em vez do antigo limiar fixo de 0.12 que so
         filmes muito escuros atingiam.
      3. Validacao GEOMETRICA: a regiao clara deve tocar a borda do filme
         (e uma moldura/faixa externa) e o campo deve ter area razoavel
         (15%..97% do filme). Evita falsos positivos por ruido/poeira.

    Returns:
        dict com field_type ("full"|"smaller"), field_bbox, center_intensity,
        border_intensity, diff.
    """
    if mask is None:
        mask = np.ones_like(film_gray, dtype=bool)

    h, w = film_gray.shape

    # Analisa apenas o MIOLO do filme: a borda cortada do filme costuma ter
    # uma sombra escura fina no scan que contamina a separacao campo/borda.
    # IMPORTANTE: erosao morfologica NAO encolhe a mascara nas bordas da
    # imagem (padding por reflexao), entao a moldura e zerada explicitamente.
    core_r = max(2, int(round(min(h, w) * 0.04)))
    mask_core = mask.copy()
    mask_core[:core_r, :] = False
    mask_core[-core_r:, :] = False
    mask_core[:, :core_r] = False
    mask_core[:, -core_r:] = False
    mask_core &= morphology.erosion(mask, morphology.disk(core_r))
    if mask_core.sum() < 100:
        mask_core = mask
    mask = mask_core

    vals = film_gray[mask]
    if vals.size < 100:
        return {"field_type": "full", "field_bbox": None,
                "center_intensity": float(vals.mean()) if vals.size else 0.0,
                "border_intensity": 0.0, "diff": 0.0}

    # 1) Otsu interno ao filme
    try:
        thr = filters.threshold_otsu(vals)
    except Exception:
        thr = float(np.median(vals))
    dark = (film_gray < thr) & mask     # candidato a campo
    light = (film_gray >= thr) & mask   # candidato a borda nao irradiada

    d_vals = film_gray[dark]
    l_vals = film_gray[light]
    if d_vals.size < 50 or l_vals.size < 50:
        return {"field_type": "full", "field_bbox": None,
                "center_intensity": float(vals.mean()),
                "border_intensity": float(vals.mean()), "diff": 0.0}

    d_mean, l_mean = float(d_vals.mean()), float(l_vals.mean())
    sep = l_mean - d_mean
    noise = 0.5 * (float(d_vals.std()) + float(l_vals.std()))

    # 2) Separacao significativa? (adaptativa ao ruido; minimo absoluto baixo)
    min_sep = max(0.02, 1.5 * noise)
    if uniformity_tol is not None:           # compatibilidade com chamadas antigas
        min_sep = max(min_sep, 0.0)          # uniformity_tol legado ignorado
    if sep < min_sep:
        return {"field_type": "full", "field_bbox": None,
                "center_intensity": d_mean, "border_intensity": l_mean,
                "diff": sep}

    # 3) Geometria: limpa o campo e valida proporcoes/posicao
    field_bin = morphology.remove_small_objects(dark, min_size=int(h * w * 0.02))
    field_bin = morphology.binary_closing(field_bin, morphology.disk(2))
    if not field_bin.any():
        return {"field_type": "full", "field_bbox": None,
                "center_intensity": d_mean, "border_intensity": l_mean,
                "diff": sep}

    labels = measure.label(field_bin)
    largest = max(measure.regionprops(labels), key=lambda r: r.area)
    field_mask = labels == largest.label
    area_frac = field_mask.sum() / float(mask.sum())

    # a regiao clara precisa existir de verdade na PERIFERIA do filme:
    edge_band = np.zeros_like(mask)
    b = max(2, int(min(h, w) * 0.06))
    edge_band[:b, :] = True; edge_band[-b:, :] = True
    edge_band[:, :b] = True; edge_band[:, -b:] = True
    edge_band &= mask
    light_on_edge = float((light & edge_band).sum()) / max(1, int(edge_band.sum()))

    if area_frac < 0.15 or area_frac > 0.97 or light_on_edge < 0.10:
        return {"field_type": "full", "field_bbox": None,
                "center_intensity": d_mean, "border_intensity": l_mean,
                "diff": sep}

    fb = _fwhm_bbox(film_gray, mask, d_vals, l_vals)
    if fb is None:
        fb = largest.bbox  # fallback: bbox do maior componente escuro
    return {"field_type": "smaller", "field_bbox": fb,
            "center_intensity": d_mean, "border_intensity": l_mean,
            "diff": sep}


def _fwhm_bbox(film_gray, mask, d_vals, l_vals):
    """
    Bordas do campo pelo metodo FISICO padrao (FWHM/50%):
    o campo e definido onde o sinal cruza 50% entre o PLATO (regiao central
    irradiada, escura) e o FUNDO (borda nao irradiada, clara).

    v2 — robusta a artefatos reais de scan:
      * perfis por MEDIANA (nao media) de cada linha/coluna -> imune a
        etiquetas, poeira e a SOMBRA ESCURA da borda cortada do filme,
        que na v1 'esticava' o campo ate a borda;
      * o cruzamento de 50% e buscado DO CENTRO DO CAMPO PARA FORA,
        parando no primeiro cruzamento real (quedas espurias na borda do
        filme ficam alem do cruzamento e nao contaminam).
    """
    try:
        h, w = film_gray.shape
        plateau = float(np.median(d_vals[d_vals <= np.percentile(d_vals, 40)])) \
            if d_vals.size else float(np.percentile(film_gray[mask], 10))
        bg = float(np.median(l_vals)) if l_vals.size else float(np.percentile(film_gray[mask], 95))
        half = 0.5 * (plateau + bg)

        g = film_gray.copy()
        g[~mask] = bg  # fora do filme conta como fundo

        # Perfis por MEDIANA (robustos), suavizados com media movel de 3
        med_c = np.median(g, axis=0)
        med_r = np.median(g, axis=1)
        prof_c = np.convolve(med_c, np.ones(3) / 3.0, mode="same")
        prof_r = np.convolve(med_r, np.ones(3) / 3.0, mode="same")

        def walk_out(prof, n):
            """Acha o platô central e caminha para fora ate cruzar 'half'."""
            lo, hi = int(n * 0.20), max(int(n * 0.80), int(n * 0.20) + 1)
            center = lo + int(np.argmin(prof[lo:hi]))
            if prof[center] > half:      # nem o centro esta abaixo de 50%
                return None
            left = center
            while left > 0 and prof[left - 1] <= half:
                left -= 1
            right = center
            while right < n - 1 and prof[right + 1] <= half:
                right += 1
            return left, right + 1

        cw = walk_out(prof_c, w)
        rw = walk_out(prof_r, h)
        if cw is None or rw is None:
            return None
        minc, maxc = cw
        minr, maxr = rw
        # sanidade: campo entre 10% e 97% do filme em cada eixo
        if not (0.10 * w <= (maxc - minc) <= 0.97 * w):
            return None
        if not (0.10 * h <= (maxr - minr) <= 0.97 * h):
            return None
        return (minr, minc, maxr, maxc)
    except Exception:
        return None


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
