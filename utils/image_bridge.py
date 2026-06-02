"""
image_bridge.py — Ponte entre as imagens carregadas no Streamlit (bytes)
e os engines de calculo (que esperam arrays NumPy).

Reaproveita a logica do image_proc.py original, mas lendo de bytes
em vez de caminho de arquivo.
"""

import io
import numpy as np
from PIL import Image


def bytes_to_array(img_bytes: bytes, filename: str = "") -> np.ndarray:
    """
    Converte bytes de uma imagem (do st.file_uploader) em array NumPy,
    preservando 16-bit quando possivel.

    Tenta tifffile para TIFF, depois PIL como fallback.
    """
    name = filename.lower()

    # TIFF: tentar tifffile (melhor para 16-bit)
    if name.endswith((".tif", ".tiff")):
        try:
            import tifffile as tiff
            arr = tiff.imread(io.BytesIO(img_bytes))
            if arr is not None and arr.ndim >= 2:
                return np.asarray(arr)
        except Exception:
            pass

    # Fallback universal: PIL
    with Image.open(io.BytesIO(img_bytes)) as pil_img:
        return np.array(pil_img)


def get_saved_films_as_arrays(state):
    """
    Retorna a lista de imagens salvas na sessao como arrays NumPy.
    Cada item: {"name": str, "array": np.ndarray}
    """
    result = []
    for img in state.get("uploaded_films", []):
        try:
            arr = bytes_to_array(img["bytes"], img["name"])
            result.append({"name": img["name"], "array": arr})
        except Exception as e:
            result.append({"name": img["name"], "array": None, "error": str(e)})
    return result
