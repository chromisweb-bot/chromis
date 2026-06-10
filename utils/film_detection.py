"""
film_detection.py — Detecção, segmentação e ordenação de filmes radiocrômicos.

Baseado nas práticas do Dosepy (scikit-image) e protocolos de dosimetria com
filme. Detecta cada pedaço de filme num scan, separa do fundo branco, e
ordena do mais claro (menor dose) ao mais escuro (maior dose).

ROBUSTEZ (v2): filmes encostados ou quase encostados no scan são separados
corretamente. Estratégia em camadas:
  1. Limiar de Otsu (filme escuro vs fundo claro do scanner).
  2. Corte pelas BORDAS (gradiente de Sobel): a junção entre dois filmes
     sempre tem uma transição detectável — filmes com doses diferentes mudam
     de tom, e mesmo filmes de mesma dose têm a borda física (sombra/reflexo).
  3. Erosão leve adaptativa -> sementes (núcleos) de cada filme.
  4. Watershed sobre o gradiente, limitado à máscara, recupera cada filme
     inteiro até a sua borda real.
  5. Refino por região: abertura morfológica remove "vazamentos" finos
     (fios, molduras, riscos) e fill-holes fecha buracos internos do filme —
     POR REGIÃO, sem nunca soldar filmes vizinhos (o erro da versão antiga,
     que usava um closing global).

Funções principais:
    detect_films(image, ...) -> lista de filmes detectados, cada um com
        bbox, máscara, centroide, intensidade média e recorte.
    order_films_by_intensity(films) -> ordena do mais claro ao mais escuro.
"""

import numpy as np
from scipy import ndimage as ndi
from skimage import color, filters, measure, morphology, segmentation


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


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """Mantém apenas o maior componente conectado de uma máscara booleana."""
    lbl, n = ndi.label(mask)
    if n <= 1:
        return mask
    sizes = ndi.sum(mask, lbl, index=range(1, n + 1))
    keep = int(np.argmax(sizes)) + 1
    return lbl == keep


def detect_films(image: np.ndarray,
                 min_area_frac: float = 0.003,
                 close_radius: int = 3,
                 separate_touching: bool = True,
                 edge_threshold: float = 0.04):
    """
    Detecta pedaços de filme num scan com fundo claro, separando corretamente
    filmes que se tocam ou estão muito próximos.

    Args:
        image: array da imagem (RGB, RGBA, cinza; uint8/uint16/float).
        min_area_frac: área mínima de um filme como fração da imagem
                       (descarta sujeira/respingos).
        close_radius: raio do fechamento aplicado POR REGIÃO (fecha
                      rachaduras internas do filme; nunca solda vizinhos).
        separate_touching: usa bordas + watershed para separar filmes
                      encostados (recomendado: True).
        edge_threshold: limiar do gradiente de Sobel que define as linhas
                      de junção entre filmes (0.02–0.08 funciona bem).

    Returns:
        (films, debug) onde films é lista de dicts:
            {
              "id", "bbox" (min_row,min_col,max_row,max_col),
              "centroid", "area_px", "mean_intensity_gray",
              "mask" (2D bool do tamanho do bbox),
            }
        debug traz a máscara binária, o limiar usado e o nº de sementes.
    """
    gray = _to_gray(image)
    h, w = gray.shape
    total_area = h * w

    # 1) Limiar robusto: Otsu separa bem filmes escuros do fundo, mas pode
    #    DEIXAR DE FORA filmes muito claros (dose baixa, quase transparentes).
    #    Por isso combinamos com uma estimativa do branco do fundo do scanner
    #    (percentil alto) e capturamos tudo que for visivelmente mais escuro.
    thresh_otsu = filters.threshold_otsu(gray)
    bg_white = float(np.percentile(gray, 95))     # branco do scanner
    thresh = max(thresh_otsu, bg_white - 0.06)
    thresh = min(thresh, 0.985)                   # nunca engolir o fundo todo
    binary = gray < thresh
    # ruído fino fora dos filmes
    binary = morphology.remove_small_objects(binary,
                                             int(total_area * 0.0005))

    n_seeds = 0
    if separate_touching:
        # 2) Bordas: junções entre filmes têm gradiente alto
        edges = filters.sobel(gray)
        # 3) Sementes: máscara sem as linhas de junção, erodida de leve.
        #    Raio adaptativo ao tamanho da imagem (≈0.5% do menor lado).
        er = max(2, int(round(min(h, w) / 200.0)))
        seeds_mask = binary & ~(edges > edge_threshold)
        seeds_mask = morphology.erosion(seeds_mask, morphology.disk(er))
        seeds = measure.label(seeds_mask)
        # descarta sementes minúsculas (ruído)
        min_seed = total_area * max(min_area_frac / 4.0, 0.0005)
        for reg in measure.regionprops(seeds):
            if reg.area < min_seed:
                seeds[seeds == reg.label] = 0
        seeds, n_seeds = measure.label(seeds > 0, return_num=True)
        if n_seeds > 0:
            # 4) Watershed sobre o gradiente: corta exatamente nas junções
            labels = segmentation.watershed(edges, markers=seeds, mask=binary)
        else:
            labels = measure.label(binary)
    else:
        labels = measure.label(binary)

    films = []
    fid = 0
    refine_r = max(2, int(round(min(h, w) / 200.0)))
    for reg in measure.regionprops(labels):
        if reg.area < total_area * min_area_frac:
            continue
        # 5) Refino POR REGIÃO:
        region_mask = labels == reg.label
        # remove vazamentos finos (molduras, fios, riscos)
        refined = morphology.opening(region_mask, morphology.disk(refine_r))
        if not refined.any():
            refined = region_mask
        refined = _largest_component(refined)
        # fecha rachaduras e buracos INTERNOS do filme (seguro: só esta região)
        if close_radius > 0:
            refined = morphology.closing(refined, morphology.disk(close_radius))
        refined = ndi.binary_fill_holes(refined)
        if refined.sum() < total_area * min_area_frac:
            continue

        rows = np.any(refined, axis=1)
        cols = np.any(refined, axis=0)
        minr, maxr = np.where(rows)[0][[0, -1]]
        minc, maxc = np.where(cols)[0][[0, -1]]
        maxr += 1
        maxc += 1

        sub = refined[minr:maxr, minc:maxc]
        vals = gray[minr:maxr, minc:maxc][sub]
        cy, cx = ndi.center_of_mass(refined)

        fid += 1
        films.append({
            "id": fid,
            "bbox": (int(minr), int(minc), int(maxr), int(maxc)),
            "centroid": (float(cy), float(cx)),
            "area_px": int(refined.sum()),
            "mean_intensity_gray": float(vals.mean()) if vals.size else 0.0,
            "mask": sub,
        })

    debug = {"binary": binary, "threshold": float(thresh),
             "n_found": len(films), "image_shape": (h, w),
             "n_seeds": int(n_seeds)}
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

    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/1781127628637_image.png"
    img = np.array(Image.open(path))
    print(f"Imagem: {img.shape}, dtype={img.dtype}")

    films, debug = detect_films(img)
    print(f"\nLimiar Otsu: {debug['threshold']:.3f}  ·  Sementes: {debug['n_seeds']}")
    print(f"Filmes detectados: {debug['n_found']}")

    ordered = order_films_by_intensity(films)
    print("\nOrdem (claro -> escuro / menor -> maior dose):")
    for f in ordered:
        minr, minc, maxr, maxc = f["bbox"]
        wpx, hpx = maxc - minc, maxr - minr
        print(f"  Filme {f['order']+1}: intensidade={f['mean_intensity_gray']:.3f}, "
              f"tamanho={wpx}x{hpx}px, centro=({f['centroid'][1]:.0f},{f['centroid'][0]:.0f})")
