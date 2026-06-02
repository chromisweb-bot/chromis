"""
film_detection.py — Detecção, segmentação e ordenação de filmes radiocrômicos.

Baseado nas práticas do Dosepy (scikit-image) e protocolos de dosimetria com
filme. Detecta cada pedaço de filme num scan, separa do fundo branco, e
ordena do mais claro (menor dose) ao mais escuro (maior dose).

Funções principais:
    detect_films(image, ...) -> lista de filmes detectados, cada um com
        bbox, máscara, centroide, intensidade média e recorte.
    order_films_by_intensity(films) -> ordena do mais claro ao mais escuro.
"""

import numpy as np
from skimage import color, filters, measure, morphology, util


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Converte para escala de cinza float (0..1), lidando com RGB/RGBA/cinza."""
    img = np.asarray(image)
    # Remove canal alfa se houver
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    # Converte para float 0..1
    if img.dtype == np.uint8:
        img = img.astype(np.float64) / 255.0
    elif img.dtype == np.uint16:
        img = img.astype(np.float64) / 65535.0
    else:
        img = img.astype(np.float64)
        if img.max() > 1.0:
            img = img / img.max()
    # Cinza
    if img.ndim == 3:
        gray = color.rgb2gray(img)
    else:
        gray = img
    return gray


def detect_films(image: np.ndarray,
                 min_area_frac: float = 0.003,
                 close_radius: int = 3):
    """
    Detecta pedaços de filme num scan com fundo claro.

    Estratégia:
      1. Converte para cinza.
      2. Limiariza (Otsu) — filme é mais escuro que o fundo branco.
      3. Limpa ruído (operações morfológicas).
      4. Rotula regiões conectadas e filtra por área mínima.
      5. Extrai propriedades de cada filme.

    Args:
        image: array da imagem (RGB, RGBA, cinza; uint8/uint16/float).
        min_area_frac: área mínima de um filme como fração da imagem
                       (descarta sujeira/respingos).
        close_radius: raio para fechamento morfológico (une buracos).

    Returns:
        (films, debug) onde films é lista de dicts:
            {
              "id", "bbox" (min_row,min_col,max_row,max_col),
              "centroid", "area_px", "mean_intensity_gray",
              "mask" (2D bool do tamanho do bbox),
            }
        debug traz a máscara binária e o limiar usado.
    """
    gray = _to_gray(image)
    h, w = gray.shape
    total_area = h * w

    # Otsu: separa fundo (claro) de filme (escuro)
    thresh = filters.threshold_otsu(gray)
    # Filme = pixels mais escuros que o limiar
    binary = gray < thresh

    # Limpeza morfológica: fecha buracos e remove ruído
    if close_radius > 0:
        binary = morphology.closing(binary, morphology.disk(close_radius))
    binary = morphology.remove_small_holes(binary, area_threshold=int(total_area * 0.0005))
    binary = morphology.remove_small_objects(binary, min_size=int(total_area * min_area_frac))

    # Rotular regiões conectadas
    labels = measure.label(binary)
    regions = measure.regionprops(labels, intensity_image=gray)

    films = []
    for i, reg in enumerate(regions):
        if reg.area < total_area * min_area_frac:
            continue
        minr, minc, maxr, maxc = reg.bbox
        films.append({
            "id": i + 1,
            "bbox": (minr, minc, maxr, maxc),
            "centroid": reg.centroid,
            "area_px": int(reg.area),
            "mean_intensity_gray": float(reg.intensity_mean),
            "mask": reg.image,  # máscara booleana do tamanho do bbox
        })

    debug = {"binary": binary, "threshold": float(thresh),
             "n_found": len(films), "image_shape": (h, w)}
    return films, debug


def order_films_by_intensity(films: list) -> list:
    """
    Ordena os filmes do mais CLARO (maior intensidade = menor dose) ao
    mais ESCURO (menor intensidade = maior dose).

    No filme radiocrômico, mais dose = mais escuro = menor valor de cinza.
    """
    ordered = sorted(films, key=lambda f: f["mean_intensity_gray"], reverse=True)
    # Reatribui ordem sequencial
    for idx, f in enumerate(ordered):
        f["order"] = idx  # 0 = mais claro (menor dose)
    return ordered


if __name__ == "__main__":
    # Teste com imagem real
    import sys
    from PIL import Image

    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/1780356414772_image.png"
    img = np.array(Image.open(path))
    print(f"Imagem: {img.shape}, dtype={img.dtype}")

    films, debug = detect_films(img)
    print(f"\nLimiar Otsu: {debug['threshold']:.3f}")
    print(f"Filmes detectados: {debug['n_found']}")

    ordered = order_films_by_intensity(films)
    print("\nOrdem (claro -> escuro / menor -> maior dose):")
    for f in ordered:
        minr, minc, maxr, maxc = f["bbox"]
        wpx, hpx = maxc - minc, maxr - minr
        print(f"  Filme {f['order']+1}: intensidade={f['mean_intensity_gray']:.3f}, "
              f"tamanho={wpx}x{hpx}px, centro=({f['centroid'][1]:.0f},{f['centroid'][0]:.0f})")
