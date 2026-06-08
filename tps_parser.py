"""
tps_parser.py — Parser Universal de TPS com suporte completo ao Monaco

Suporta:
  - DICOM RT Dose (.dcm)     → mapa de dose 2D/3D do Monaco
  - DICOM RT Structure (.dcm) → curvas de isodose como contornos
  - CSV/TXT de pontos         → pontos de dose exportados do Monaco
  - CSV/TXT genérico          → matriz de dose
  - PNG/TIFF                  → imagem de dose com escala manual

Como exportar do Monaco:
  1. Mapa de dose:
     Plan Evaluation → Export → DICOM RT Dose → salvar como .dcm

  2. Isodoses:
     Plan Evaluation → Isodose Lines → Export → DICOM RT Structure → salvar como .dcm
     (ou exportar como imagem e usar o modo image)

  3. Pontos de dose:
     Plan Evaluation → Point Dose → Export to CSV / copiar tabela
     Salvar como .csv ou .txt
"""

import numpy as np
import io
import re
from pathlib import Path
from PIL import Image
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# CLASSES DE DADOS
# ══════════════════════════════════════════════════════════════════════════════

class DoseDistribution:
    """
    Container padronizado para distribuição de dose 2D.
    Sempre em Gy internamente.
    """
    def __init__(self, dose, resolution_mm, origin_mm=(0.0, 0.0),
                 source="unknown", metadata=None):
        self.dose         = np.asarray(dose, dtype=np.float64)
        self.resolution_mm = float(resolution_mm)
        self.origin_mm    = tuple(origin_mm)
        self.shape        = self.dose.shape
        self.max_dose     = float(np.max(self.dose))
        self.min_dose     = float(np.min(self.dose[self.dose > 0])) if np.any(self.dose > 0) else 0.0
        self.mean_dose    = float(np.mean(self.dose[self.dose > 0])) if np.any(self.dose > 0) else 0.0
        self.source       = source
        self.metadata     = metadata or {}

    def get_axes_mm(self):
        """Arrays de coordenadas físicas em mm (origem no canto superior esquerdo)."""
        h, w = self.shape
        x0, y0 = self.origin_mm
        x_axis = x0 + np.arange(w) * self.resolution_mm
        y_axis = y0 + np.arange(h) * self.resolution_mm
        return x_axis, y_axis

    def get_axes_centered_mm(self):
        """Arrays de coordenadas com origem no CENTRO do mapa (padrão TPS)."""
        h, w = self.shape
        cx = w / 2.0 * self.resolution_mm
        cy = h / 2.0 * self.resolution_mm
        x_axis = np.arange(w) * self.resolution_mm - cx
        y_axis = cy - np.arange(h) * self.resolution_mm  # Y invertido
        return x_axis, y_axis

    def get_dose_at_mm(self, x_mm, y_mm):
        """
        Retorna dose (Gy) em coordenadas mm centradas.
        Usa interpolação bilinear.
        """
        from scipy.ndimage import map_coordinates
        h, w = self.shape
        col = (x_mm / self.resolution_mm) + w / 2.0
        row = -(y_mm / self.resolution_mm) + h / 2.0
        if row < 0 or row >= h or col < 0 or col >= w:
            return np.nan
        result = map_coordinates(self.dose, [[row], [col]], order=1, mode='nearest')
        return float(result[0])

    def summary(self):
        return {
            'shape': self.shape,
            'resolution_mm': self.resolution_mm,
            'origin_mm': self.origin_mm,
            'max_dose_gy': self.max_dose,
            'max_dose_cgy': self.max_dose * 100,
            'min_dose_gy': self.min_dose,
            'mean_dose_gy': self.mean_dose,
            'source': self.source,
            'metadata': self.metadata,
        }


class IsodoseContours:
    """
    Container para curvas de isodose extraídas do TPS.
    Cada nível tem uma lista de contornos (arrays Nx2 em mm).
    """
    def __init__(self, contours_mm, levels_gy, prescription_dose_gy=None,
                 source="unknown", metadata=None):
        self.contours_mm         = contours_mm          # dict: level_gy → [array(N,2), ...]
        self.levels_gy           = sorted(levels_gy)
        self.prescription_dose_gy = prescription_dose_gy
        self.source              = source
        self.metadata            = metadata or {}

    def get_levels_percent(self):
        """Retorna níveis como % da dose de prescrição."""
        if self.prescription_dose_gy and self.prescription_dose_gy > 0:
            return {
                round(100 * lvl / self.prescription_dose_gy): lvl
                for lvl in self.levels_gy
            }
        return {}

    def get_contours_at_percent(self, pct, tolerance=2.0):
        """Retorna contornos mais próximos de um percentual."""
        if not self.prescription_dose_gy:
            return []
        target_gy = self.prescription_dose_gy * pct / 100.0
        best_lvl = min(self.levels_gy, key=lambda l: abs(l - target_gy))
        if abs(best_lvl - target_gy) / target_gy * 100 <= tolerance:
            return self.contours_mm.get(best_lvl, [])
        return []


class DosePoints:
    """Container para pontos de dose do TPS."""
    def __init__(self, points, source="unknown"):
        # points: lista de dicts com name, x_mm, y_mm, z_mm, dose_gy
        self.points = points
        self.source = source

    def to_dataframe(self):
        return pd.DataFrame(self.points)

    def get_point(self, name):
        for p in self.points:
            if p.get('name', '').lower() == name.lower():
                return p
        return None


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS INTERNOS
# ══════════════════════════════════════════════════════════════════════════════

def _read_raw(filepath_or_bytes):
    """Lê conteúdo bruto do arquivo (path, file-like, bytes)."""
    if isinstance(filepath_or_bytes, (str, Path)):
        with open(filepath_or_bytes, 'rb') as f:
            return f.read()
    elif hasattr(filepath_or_bytes, 'read'):
        pos = filepath_or_bytes.tell() if hasattr(filepath_or_bytes, 'tell') else None
        data = filepath_or_bytes.read()
        if pos is not None and hasattr(filepath_or_bytes, 'seek'):
            filepath_or_bytes.seek(0)
        return data
    elif isinstance(filepath_or_bytes, bytes):
        return filepath_or_bytes
    raise ValueError(f"Tipo não suportado: {type(filepath_or_bytes)}")


def _get_filename(filepath_or_bytes, filename=None):
    if filename:
        return filename
    if hasattr(filepath_or_bytes, 'name'):
        return filepath_or_bytes.name
    if isinstance(filepath_or_bytes, (str, Path)):
        return str(filepath_or_bytes)
    return "arquivo"


def detect_format(filepath_or_bytes, filename=None):
    """Detecta o formato a partir da extensão e conteúdo."""
    fname = _get_filename(filepath_or_bytes, filename)
    ext = Path(fname).suffix.lower()

    if ext == '.all':
        return 'all_dose'
    if ext == '.dcm':
        # Pode ser RT Dose ou RT Structure — detectar pelo conteúdo
        try:
            content = _read_raw(filepath_or_bytes)
            if b'RTDOSE' in content[:2000] or b'RT DOSE' in content[:2000]:
                return 'dicom_dose'
            if b'RTSTRUCT' in content[:2000] or b'RT STRUCT' in content[:2000]:
                return 'dicom_struct'
            return 'dicom_dose'  # default para .dcm
        except Exception:
            return 'dicom_dose'
    elif ext in ('.csv', '.txt'):
        # Pode ser pontos de dose ou matriz
        try:
            content = _read_raw(filepath_or_bytes).decode('utf-8', errors='ignore')
            lower = content[:500].lower()
            if any(k in lower for k in ['point', 'ponto', 'name', 'nome', 'coord', 'x_mm', 'y_mm']):
                return 'dose_points'
        except Exception:
            pass
        return 'csv_matrix'
    elif ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'):
        return 'image'
    else:
        # Tentar pelo conteúdo
        try:
            content = _read_raw(filepath_or_bytes)
            if b'DICM' in content[:132]:
                return 'dicom_dose'
            head = content[:600].decode('latin-1', errors='ignore')
            if ('DosePtsxy' in head) or ('DoseUnits' in head and 'DoseResmm' in head):
                return 'all_dose'
        except Exception:
            pass
        return 'csv_matrix'


# ══════════════════════════════════════════════════════════════════════════════
# LEITORES DICOM
# ══════════════════════════════════════════════════════════════════════════════

def read_dicom_dose(filepath_or_bytes, filename=None, slice_index=None):
    """
    Lê DICOM RT Dose do Monaco (ou qualquer TPS).

    O Monaco exporta RT Dose como volume 3D (múltiplas fatias axiais).
    Por padrão seleciona a fatia mais próxima do isocentro (z=0).

    Args:
        filepath_or_bytes : arquivo .dcm
        slice_index       : índice da fatia (None = automático por isocentro)

    Returns:
        DoseDistribution, info_dict
    """
    try:
        import pydicom
    except ImportError:
        raise ImportError(
            "pydicom não instalado.\n"
            "Instale com: pip install pydicom"
        )

    content = _read_raw(filepath_or_bytes)
    ds = pydicom.dcmread(io.BytesIO(content))

    # ── Verificar que é RT Dose ────────────────────────────────────────────
    modality = getattr(ds, 'Modality', '')
    if modality not in ('RTDOSE', ''):
        raise ValueError(f"Arquivo não é RT Dose (Modality={modality})")

    # ── Escalar dose ───────────────────────────────────────────────────────
    pixel_array = ds.pixel_array.astype(np.float64)  # shape: (slices, rows, cols) ou (rows, cols)
    scaling = float(getattr(ds, 'DoseGridScaling', 1.0))
    dose_volume = pixel_array * scaling  # em Gy

    # ── Metadados espaciais ────────────────────────────────────────────────
    pixel_spacing = [1.0, 1.0]
    if hasattr(ds, 'PixelSpacing'):
        pixel_spacing = [float(ds.PixelSpacing[0]), float(ds.PixelSpacing[1])]
    elif hasattr(ds, 'ImagePlanePixelSpacing'):
        pixel_spacing = [float(ds.ImagePlanePixelSpacing[0]), float(ds.ImagePlanePixelSpacing[1])]

    resolution_mm = pixel_spacing[0]  # assumindo pixels quadrados (comum no Monaco)

    # Posição da imagem (canto superior esquerdo da primeira fatia)
    ipp = getattr(ds, 'ImagePositionPatient', [0.0, 0.0, 0.0])
    origin_x = float(ipp[0])
    origin_y = float(ipp[1])
    origin_z = float(ipp[2])

    # ── Selecionar fatia 2D ────────────────────────────────────────────────
    n_slices = dose_volume.shape[0] if dose_volume.ndim == 3 else 1

    if dose_volume.ndim == 2:
        dose_2d = dose_volume
        selected_slice = 0
        z_mm = origin_z
    else:
        # Calcular z de cada fatia
        grid_offset = list(getattr(ds, 'GridFrameOffsetVector', [0.0]))
        z_positions = [origin_z + float(off) for off in grid_offset]

        if slice_index is not None:
            selected_slice = int(slice_index)
        else:
            # Selecionar fatia mais próxima do isocentro (z=0)
            selected_slice = int(np.argmin(np.abs(np.array(z_positions))))

        dose_2d = dose_volume[selected_slice]
        z_mm = z_positions[selected_slice] if selected_slice < len(z_positions) else origin_z

    # ── Unidades ───────────────────────────────────────────────────────────
    dose_units = getattr(ds, 'DoseUnits', 'GY').upper()
    if dose_units == 'CGY':
        dose_2d = dose_2d / 100.0  # converter cGy → Gy

    # ── Metadados extras ───────────────────────────────────────────────────
    metadata = {
        'modality':             modality,
        'dose_units_original':  dose_units,
        'dose_summation_type':  getattr(ds, 'DoseSummationType', ''),
        'dose_type':            getattr(ds, 'DoseType', 'PHYSICAL'),
        'patient_name':         str(getattr(ds, 'PatientName', '')),
        'patient_id':           str(getattr(ds, 'PatientID', '')),
        'study_description':    str(getattr(ds, 'StudyDescription', '')),
        'series_description':   str(getattr(ds, 'SeriesDescription', '')),
        'n_slices':             n_slices,
        'selected_slice':       selected_slice,
        'z_mm':                 z_mm,
        'pixel_spacing_mm':     pixel_spacing,
        'resolution_mm':        resolution_mm,
        'origin_patient_mm':    [origin_x, origin_y, origin_z],
        'tps':                  'Monaco' if 'monaco' in str(getattr(ds, 'ManufacturerModelName', '')).lower() else 'Desconhecido',
    }

    info = {
        'n_slices':        n_slices,
        'selected_slice':  selected_slice,
        'z_mm':            z_mm,
        'all_z_mm':        z_positions if dose_volume.ndim == 3 else [origin_z],
        'resolution_mm':   resolution_mm,
        'shape':           dose_2d.shape,
        'max_dose_gy':     float(np.max(dose_2d)),
        'max_dose_cgy':    float(np.max(dose_2d)) * 100,
        'patient_name':    metadata['patient_name'],
        'patient_id':      metadata['patient_id'],
    }

    dist = DoseDistribution(
        dose=dose_2d,
        resolution_mm=resolution_mm,
        origin_mm=(origin_x, origin_y),
        source='dicom_monaco',
        metadata=metadata,
    )

    return dist, info


def read_dicom_struct(filepath_or_bytes, filename=None, z_target_mm=0.0,
                      z_tolerance_mm=5.0):
    """
    Lê DICOM RT Structure e extrai contornos de isodose.

    O Monaco exporta isodoses como RT Structure com contornos por fatia.
    Seleciona os contornos na fatia mais próxima de z_target_mm.

    Args:
        z_target_mm   : posição Z da fatia de interesse (mm) — usar z da RT Dose
        z_tolerance_mm: tolerância em Z para aceitar contornos

    Returns:
        IsodoseContours
    """
    try:
        import pydicom
    except ImportError:
        raise ImportError("pydicom não instalado. Instale com: pip install pydicom")

    content = _read_raw(filepath_or_bytes)
    ds = pydicom.dcmread(io.BytesIO(content))

    modality = getattr(ds, 'Modality', '')
    if modality not in ('RTSTRUCT', ''):
        raise ValueError(f"Arquivo não é RT Structure (Modality={modality})")

    # ── Extrair estruturas ─────────────────────────────────────────────────
    roi_names = {}
    if hasattr(ds, 'StructureSetROISequence'):
        for roi in ds.StructureSetROISequence:
            roi_names[int(roi.ROINumber)] = str(roi.ROIName)

    contours_mm = {}   # dose_value_gy → [array(N,2), ...]
    levels_gy   = []
    metadata    = {'roi_names': roi_names, 'n_rois': len(roi_names)}

    if hasattr(ds, 'ROIContourSequence'):
        for roi_contour in ds.ROIContourSequence:
            roi_num  = int(getattr(roi_contour, 'ReferencedROINumber', 0))
            roi_name = roi_names.get(roi_num, f'ROI_{roi_num}')

            # Tentar extrair valor de dose do nome
            # Monaco nomeia como: "Isodose_100cGy", "95%", "100 cGy", etc.
            dose_gy = _parse_dose_from_roi_name(roi_name)

            if dose_gy is None:
                continue  # pular ROIs sem dose identificável

            contour_list = []
            if hasattr(roi_contour, 'ContourSequence'):
                for contour in roi_contour.ContourSequence:
                    if not hasattr(contour, 'ContourData'):
                        continue
                    data = np.array(contour.ContourData, dtype=np.float64)
                    if len(data) < 9:  # mínimo 3 pontos × 3 coords
                        continue

                    # Reshape: (N, 3) — x, y, z em mm
                    pts = data.reshape(-1, 3)
                    z_slice = pts[0, 2]

                    # Filtrar por profundidade z
                    if abs(z_slice - z_target_mm) > z_tolerance_mm:
                        continue

                    # Guardar só X, Y (plano 2D)
                    contour_list.append(pts[:, :2])  # array (N, 2)

            if contour_list:
                if dose_gy not in contours_mm:
                    contours_mm[dose_gy] = []
                    levels_gy.append(dose_gy)
                contours_mm[dose_gy].extend(contour_list)

    return IsodoseContours(
        contours_mm=contours_mm,
        levels_gy=sorted(levels_gy),
        source='dicom_struct',
        metadata=metadata,
    )


def _parse_dose_from_roi_name(name):
    """
    Tenta extrair valor de dose em Gy a partir do nome de uma ROI.

    Exemplos que reconhece:
      "Isodose_100cGy"  → 1.0
      "100 cGy"         → 1.0
      "95%"             → None (precisa de prescrição para converter)
      "2.0Gy"           → 2.0
      "200"             → 2.0 (assume cGy se > 10)
    """
    name_lower = name.lower().strip()

    # Padrão: número seguido de 'cgy'
    m = re.search(r'([\d.]+)\s*cgy', name_lower)
    if m:
        return float(m.group(1)) / 100.0

    # Padrão: número seguido de 'gy' (sem 'c' antes)
    m = re.search(r'([\d.]+)\s*gy', name_lower)
    if m:
        val = float(m.group(1))
        return val  # já em Gy

    # Padrão: só número (assume cGy se > 10, Gy se <= 10)
    m = re.search(r'^[\w_-]*([\d.]+)[\w_-]*$', name_lower)
    if m:
        val = float(m.group(1))
        if val > 10:
            return val / 100.0  # cGy → Gy
        else:
            return val  # Gy

    return None


# ══════════════════════════════════════════════════════════════════════════════
# LEITORES DE PONTOS DE DOSE
# ══════════════════════════════════════════════════════════════════════════════

def read_dose_points_csv(filepath_or_bytes, filename=None):
    """
    Lê pontos de dose exportados do Monaco (CSV ou TXT).

    Formatos aceitos:

    Formato 1 — Monaco padrão:
        Name,X[mm],Y[mm],Z[mm],Dose[cGy]
        Centro,0.0,0.0,0.0,100.0
        P1,10.0,0.0,0.0,98.5

    Formato 2 — com cabeçalho em português:
        Ponto;X (mm);Y (mm);Z (mm);Dose (cGy)
        Centro;0;0;0;100

    Formato 3 — copiado do Monaco (sem cabeçalho):
        Centro  0.0  0.0  0.0  100.0

    Returns:
        DosePoints
    """
    content = _read_raw(filepath_or_bytes).decode('utf-8', errors='ignore')
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    # Detectar separador
    sep = ','
    if lines:
        first_data = next((l for l in lines if l[0].isalpha() or l[0] in '"\''), lines[0])
        if ';' in first_data:
            sep = ';'
        elif '\t' in first_data:
            sep = '\t'
        elif ',' not in first_data:
            sep = None  # espaço

    points = []
    header_found = False
    col_map = {}

    for line in lines:
        if sep:
            tokens = [t.strip().strip('"\'') for t in line.split(sep)]
        else:
            tokens = line.split()

        if not tokens:
            continue

        # Tentar detectar cabeçalho
        if not header_found:
            lower_tokens = [t.lower() for t in tokens]
            is_header = any(k in ' '.join(lower_tokens) for k in
                           ['name', 'nome', 'ponto', 'point', 'dose', 'x[', 'y[', 'x ('])
            if is_header:
                header_found = True
                for i, t in enumerate(lower_tokens):
                    if any(k in t for k in ['name', 'nome', 'ponto', 'point']):
                        col_map['name'] = i
                    elif t in ('x', 'x[mm]', 'x (mm)', 'x_mm') or t.startswith('x[') or t.startswith('x ('):
                        col_map['x'] = i
                    elif t in ('y', 'y[mm]', 'y (mm)', 'y_mm') or t.startswith('y[') or t.startswith('y ('):
                        col_map['y'] = i
                    elif t in ('z', 'z[mm]', 'z (mm)', 'z_mm') or t.startswith('z[') or t.startswith('z ('):
                        col_map['z'] = i
                    elif 'dose' in t or 'cgy' in t or 'gy' in t:
                        col_map['dose'] = i
                continue

        # Linha de dados
        if len(tokens) < 2:
            continue

        try:
            # Se não encontrou cabeçalho, assumir ordem: name, x, y, z, dose
            name = tokens[col_map.get('name', 0)]
            x    = float(tokens[col_map.get('x', 1)].replace(',', '.'))
            y    = float(tokens[col_map.get('y', 2)].replace(',', '.')) if len(tokens) > 2 else 0.0
            z    = float(tokens[col_map.get('z', 3)].replace(',', '.')) if len(tokens) > 3 else 0.0

            dose_idx = col_map.get('dose', 4 if len(tokens) > 4 else len(tokens) - 1)
            dose_str = tokens[dose_idx].replace(',', '.') if dose_idx < len(tokens) else '0'
            dose_raw = float(dose_str)

            # Converter para Gy se necessário
            dose_gy = dose_raw / 100.0 if dose_raw > 10 else dose_raw

            points.append({
                'name':    name,
                'x_mm':    x,
                'y_mm':    y,
                'z_mm':    z,
                'dose_gy': dose_gy,
                'dose_cgy': dose_gy * 100,
            })
        except (ValueError, IndexError):
            continue

    return DosePoints(points=points, source='csv_monaco')


# ══════════════════════════════════════════════════════════════════════════════
# LEITORES GENÉRICOS (mantidos para compatibilidade)
# ══════════════════════════════════════════════════════════════════════════════

def read_csv_matrix(filepath_or_bytes, filename=None, delimiter=None):
    """Lê matriz de dose de CSV/TXT genérico."""
    content = _read_raw(filepath_or_bytes)
    text    = content.decode('utf-8', errors='ignore')
    lines   = text.splitlines()

    header_lines = []
    data_rows    = []
    resolution_mm = 1.0
    origin_mm     = (0.0, 0.0)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            header_lines.append(stripped[1:].strip())
            continue
        if stripped[0].isdigit() or stripped[0] in '-+.':
            if delimiter:
                tokens = stripped.split(delimiter)
            else:
                delim = ',' if ',' in stripped else ('\t' if '\t' in stripped else None)
                tokens = stripped.split(delim) if delim else stripped.split()
            try:
                row = [float(t.replace(',', '.')) for t in tokens if t.strip()]
                if row:
                    data_rows.append(row)
            except ValueError:
                pass
        else:
            header_lines.append(stripped)

    if not data_rows:
        raise ValueError("Nenhum dado numérico encontrado no CSV/TXT")

    lengths = [len(r) for r in data_rows]
    max_len = max(lengths)
    dose_matrix = np.array([r for r in data_rows if len(r) == max_len], dtype=np.float64)

    # Tentar extrair resolução do cabeçalho
    for line in header_lines:
        ll = line.lower()
        if any(k in ll for k in ['resolution', 'spacing', 'pixel_size']):
            nums = re.findall(r'\d+\.?\d*', line)
            if nums:
                resolution_mm = float(nums[0])
                if 'cm' in ll:
                    resolution_mm *= 10.0

    if dose_matrix.max() > 100:
        dose_matrix /= 100.0  # cGy → Gy

    return DoseDistribution(
        dose=dose_matrix,
        resolution_mm=resolution_mm,
        origin_mm=origin_mm,
        source='csv_matrix',
        metadata={'header': header_lines},
    )


def read_image_dose(filepath_or_bytes, filename=None, resolution_mm=1.0,
                    max_dose_gy=None):
    """Lê imagem PNG/TIFF como mapa de dose (com escala manual)."""
    content   = _read_raw(filepath_or_bytes)
    img       = Image.open(io.BytesIO(content))
    img_array = np.array(img)

    if img_array.ndim == 3:
        if img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]
        gray = 0.299 * img_array[:, :, 0] + 0.587 * img_array[:, :, 1] + 0.114 * img_array[:, :, 2]
    else:
        gray = img_array.astype(np.float64)

    mn, mx = gray.min(), gray.max()
    normalized = (gray - mn) / (mx - mn) if mx > mn else np.zeros_like(gray)
    dose = normalized * float(max_dose_gy) if max_dose_gy else normalized

    return DoseDistribution(
        dose=dose,
        resolution_mm=float(resolution_mm),
        origin_mm=(0.0, 0.0),
        source='image',
        metadata={'max_dose_gy': max_dose_gy},
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO UNIVERSAL
# ══════════════════════════════════════════════════════════════════════════════

def read_all_dose(filepath_or_bytes, filename=None, **kwargs):
    """
    Le um arquivo de dose em texto do tipo .ALL (export de TPS, ex: CMS/XiO).

    Estrutura do arquivo:
      - Linhas de cabecalho "Chave,valor[,valor...]" (ex: DoseUnits, DosePtsxy,
        DoseResmm, Upperleft, PlaneDesc, PatientID).
      - Em seguida, a matriz de dose: uma linha por fileira, valores separados
        por virgula. As dimensoes batem com DosePtsxy (largura, altura).

    O parsing e ROBUSTO: detecta dinamicamente onde o cabecalho termina e a
    matriz comeca; valida as dimensoes; le a resolucao espacial e a unidade.

    Returns:
        DoseDistribution (dose internamente em Gy).
    """
    content = _read_raw(filepath_or_bytes)
    text = content.decode("latin-1", errors="ignore")
    lines = text.splitlines()

    def _isnum(s):
        try:
            float(s)
            return True
        except Exception:
            return False

    header = {}
    data_start = None
    for i, ln in enumerate(lines):
        ln = ln.replace("\r", "").strip()
        if not ln:
            continue
        parts = [p.strip() for p in ln.split(",")]
        nums = sum(1 for p in parts[:12] if _isnum(p))
        if nums >= 10 and len(parts) > 50:
            data_start = i
            break
        if len(parts) >= 2:
            header[parts[0]] = parts[1:]

    if data_start is None:
        raise ValueError("Arquivo .ALL: nao foi possivel localizar a matriz de dose.")

    rows = []
    for ln in lines[data_start:]:
        ln = ln.replace("\r", "").strip()
        if not ln:
            continue
        vals = [v for v in ln.split(",") if v.strip() != ""]
        if vals and all(_isnum(v) for v in vals):
            rows.append([float(v) for v in vals])

    if not rows:
        raise ValueError("Arquivo .ALL: matriz de dose vazia.")

    lens = [len(r) for r in rows]
    ncol = max(set(lens), key=lens.count)
    rows = [r for r in rows if len(r) == ncol]
    dose_cgy = np.array(rows, dtype=np.float64)

    res_mm = 1.0
    if "DoseResmm" in header:
        try:
            res_mm = float(header["DoseResmm"][0])
        except Exception:
            pass

    units_field = " ".join(header.get("DoseUnits", [])).lower()
    if "cgy" in units_field or not units_field:
        dose_gy = dose_cgy / 100.0
        unit_src = "cGy"
    elif "gy" in units_field:
        dose_gy = dose_cgy
        unit_src = "Gy"
    else:
        dose_gy = dose_cgy / 100.0
        unit_src = "cGy (assumido)"

    declared = header.get("DosePtsxy")
    valid_dims = None
    if declared and len(declared) >= 2:
        try:
            w_dec, h_dec = int(float(declared[0])), int(float(declared[1]))
            valid_dims = (dose_gy.shape == (h_dec, w_dec))
        except Exception:
            valid_dims = None

    # Origem fisica real do mapa (canto superior esquerdo), em mm.
    # No .ALL vem como "Upperleft, x, y". Usamos como origem para que cada
    # pixel tenha coordenada espacial real (essencial para alinhar com o filme).
    origin = (0.0, 0.0)
    if "Upperleft" in header and len(header["Upperleft"]) >= 2:
        try:
            origin = (float(header["Upperleft"][0]), float(header["Upperleft"][1]))
        except Exception:
            origin = (0.0, 0.0)

    # Grade de calculo do TPS (mm). O nome do campo no arquivo e
    # "CalcGridResmm (x,y,z)" — as virgulas DENTRO do nome fazem o split
    # quebrar o cabecalho; entao procuramos a chave que comeca com o nome e
    # pegamos os ultimos 3 numeros da linha original.
    calc_grid_mm = None
    for k in header:
        if k.startswith("CalcGridResmm"):
            # junta nome partido + valores e extrai os numeros finais
            nums = []
            for tok in header[k]:
                try:
                    nums.append(float(tok))
                except Exception:
                    pass
            if len(nums) >= 3:
                calc_grid_mm = nums[-3:]
            break

    # Dimensoes fisicas do plano de QA (mm), ex: "OutputWidLenQAplane, 352, 304"
    qa_plane_mm = None
    if "OutputWidLenQAplane" in header and len(header["OutputWidLenQAplane"]) >= 2:
        try:
            qa_plane_mm = [float(v) for v in header["OutputWidLenQAplane"][:2]]
        except Exception:
            pass

    # Dose absoluta ou relativa (campo DoseUnits costuma ter "Abs" ou "Rel")
    dose_ref = None
    if "abs" in units_field:
        dose_ref = "Absoluta"
    elif "rel" in units_field:
        dose_ref = "Relativa"

    metadata = {
        "patient_id": header.get("PatientID", ["?"])[0],
        "plane_desc": header.get("PlaneDesc", ["?"])[0],
        "unit_source": unit_src,
        "dose_reference": dose_ref,
        "declared_pts_xy": declared,
        "dims_match_declared": valid_dims,
        "datetime": header.get("DateTime", ["?"])[0] if "DateTime" in header else None,
        "doc_num": header.get("DocNum", [None])[0] if "DocNum" in header else None,
        "upperleft_mm": list(origin),
        "calc_grid_mm": calc_grid_mm,
        "qa_plane_mm": qa_plane_mm,
        "raw_header_keys": list(header.keys()),
        "raw_header": {k: header[k] for k in header},
    }

    return DoseDistribution(
        dose=dose_gy,
        resolution_mm=res_mm,
        origin_mm=origin,
        source="all_text_tps",
        metadata=metadata,
    )


def read_tps(filepath_or_bytes, filename=None, **kwargs):
    """
    Funcao universal: detecta formato e le automaticamente.

    Suporta: DICOM RT Dose, DICOM RT Structure, CSV de pontos, CSV matriz,
    imagem, e matriz de dose .ALL (CMS/XiO e similares).

    Returns:
        DoseDistribution, IsodoseContours ou DosePoints conforme o formato.
    """
    fmt = detect_format(filepath_or_bytes, filename)

    if fmt == 'all_dose':
        return read_all_dose(filepath_or_bytes, filename, **kwargs)
    elif fmt == 'dicom_dose':
        return read_dicom_dose(filepath_or_bytes, filename, **kwargs)
    elif fmt == 'dicom_struct':
        return read_dicom_struct(filepath_or_bytes, filename, **kwargs)
    elif fmt == 'dose_points':
        return read_dose_points_csv(filepath_or_bytes, filename)
    elif fmt == 'csv_matrix':
        return read_csv_matrix(filepath_or_bytes, filename, **kwargs)
    elif fmt == 'image':
        return read_image_dose(filepath_or_bytes, filename, **kwargs)
    else:
        raise ValueError(f"Formato não reconhecido: {fmt}")


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════

def render_tps_import_ui():
    """
    Interface completa de importação do TPS para o Streamlit.
    Retorna (dose_dist, iso_contours, dose_points) — qualquer pode ser None.

    Como usar no seu app:
        from tps_parser import render_tps_import_ui
        dose_tps, iso_tps, pts_tps = render_tps_import_ui()
    """
    import streamlit as st

    st.subheader("📂 Importar Dados do TPS (Monaco)")

    st.info(
        "**Como exportar do Monaco:**\n"
        "1. **Mapa de dose:** Plan Evaluation → Export → DICOM RT Dose → salvar .dcm\n"
        "2. **Isodoses:** Plan Evaluation → Isodose Lines → Export → DICOM RT Structure → salvar .dcm\n"
        "3. **Pontos de dose:** Plan Evaluation → selecionar pontos → Export / copiar tabela → salvar .csv"
    )

    dose_dist    = None
    iso_contours = None
    dose_points  = None

    tab_dose, tab_iso, tab_pts = st.tabs([
        "🗂️ Mapa de Dose (RT Dose)",
        "〰️ Isodoses (RT Structure)",
        "📍 Pontos de Dose (CSV)",
    ])

    # ── ABA 1: RT Dose ─────────────────────────────────────────────────────
    with tab_dose:
        st.markdown("**Arquivo DICOM RT Dose exportado do Monaco (.dcm)**")
        f_dose = st.file_uploader(
            "Selecionar RT Dose", type=['dcm'],
            key="tps_rtdose_upload"
        )

        if f_dose:
            try:
                with st.spinner("Lendo DICOM RT Dose..."):
                    dist, info = read_dicom_dose(f_dose)

                st.success(f"✅ Lido com sucesso! {info['shape'][0]}×{info['shape'][1]} px | "
                           f"Resolução: {info['resolution_mm']:.3f} mm/px | "
                           f"Dose máx: {info['max_dose_cgy']:.1f} cGy")

                # Info do paciente
                if info.get('patient_name') or info.get('patient_id'):
                    st.caption(f"Paciente: {info.get('patient_name', '')} | "
                               f"ID: {info.get('patient_id', '')}")

                # Selecionar fatia se tiver múltiplas
                if info['n_slices'] > 1:
                    st.markdown(f"**{info['n_slices']} fatias encontradas.** "
                                f"Fatia selecionada automaticamente: {info['selected_slice']} "
                                f"(z = {info['z_mm']:.1f} mm, mais próxima do isocentro)")

                    if st.checkbox("Selecionar fatia manualmente", key="manual_slice"):
                        z_options = [f"Fatia {i} — z={z:.1f}mm"
                                     for i, z in enumerate(info['all_z_mm'])]
                        sel = st.selectbox("Fatia", z_options, index=info['selected_slice'],
                                           key="slice_sel")
                        slice_idx = z_options.index(sel)
                        f_dose.seek(0)
                        dist, info = read_dicom_dose(f_dose, slice_index=slice_idx)

                # Preview do mapa
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(5, 4))
                fig.patch.set_facecolor('#161b22')
                ax.set_facecolor('#161b22')
                im = ax.imshow(dist.dose * 100, cmap='jet', aspect='equal')
                plt.colorbar(im, ax=ax, label='Dose (cGy)')
                ax.set_title(f'RT Dose — fatia z={info["z_mm"]:.1f}mm',
                             color='#e6edf3', fontsize=10)
                ax.tick_params(colors='#484f58', labelsize=7)
                for sp in ax.spines.values():
                    sp.set_edgecolor('#30363d')
                plt.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

                # Resumo estatístico
                col1, col2, col3 = st.columns(3)
                col1.metric("Dose Máxima", f"{dist.max_dose * 100:.1f} cGy")
                col2.metric("Dose Média",  f"{dist.mean_dose * 100:.1f} cGy")
                col3.metric("Resolução",   f"{dist.resolution_mm:.3f} mm/px")

                dose_dist = dist
                st.session_state['tps_dose_dist'] = dist
                st.session_state['tps_dose_info']  = info

            except Exception as e:
                st.error(f"❌ Erro ao ler RT Dose: {e}")
                import traceback
                with st.expander("Detalhes do erro"):
                    st.code(traceback.format_exc())

    # ── ABA 2: RT Structure (Isodoses) ─────────────────────────────────────
    with tab_iso:
        st.markdown("**Arquivo DICOM RT Structure com isodoses exportadas do Monaco (.dcm)**")

        f_struct = st.file_uploader(
            "Selecionar RT Structure", type=['dcm'],
            key="tps_rtstruct_upload"
        )

        z_target = 0.0
        if 'tps_dose_info' in st.session_state:
            z_target = st.session_state['tps_dose_info'].get('z_mm', 0.0)
            st.info(f"Z da fatia selecionada no RT Dose: {z_target:.1f} mm (será usado para filtrar contornos)")
        else:
            z_target = st.number_input("Z do plano de interesse (mm)", value=0.0, step=1.0,
                                       key="z_target_struct")

        if f_struct:
            try:
                with st.spinner("Lendo RT Structure..."):
                    iso = read_dicom_struct(f_struct, z_target_mm=z_target)

                if not iso.levels_gy:
                    st.warning(
                        "⚠️ Nenhum contorno de isodose encontrado na fatia z="
                        f"{z_target:.1f}mm. Tente ajustar o Z ou a tolerância.\n\n"
                        "Verifique se exportou as isodoses como RT Structure no Monaco."
                    )
                else:
                    lvls_cgy = [f"{v*100:.0f} cGy" for v in iso.levels_gy]
                    st.success(f"✅ {len(iso.levels_gy)} níveis de isodose encontrados: "
                               f"{', '.join(lvls_cgy)}")

                    # Visualizar contornos
                    if 'tps_dose_dist' in st.session_state:
                        base_dose = st.session_state['tps_dose_dist']
                        import matplotlib.pyplot as plt
                        fig, ax = plt.subplots(figsize=(6, 5))
                        fig.patch.set_facecolor('#161b22')
                        ax.set_facecolor('#161b22')

                        # Mapa de fundo
                        x_ax, y_ax = base_dose.get_axes_mm()
                        ax.imshow(
                            base_dose.dose * 100,
                            cmap='gray', alpha=0.5, aspect='equal',
                            extent=[x_ax[0], x_ax[-1], y_ax[-1], y_ax[0]],
                        )

                        # Isodoses
                        colors_iso = plt.cm.jet(
                            np.linspace(0.1, 0.9, len(iso.levels_gy))
                        )
                        for lvl, color in zip(iso.levels_gy, colors_iso):
                            for contour in iso.contours_mm.get(lvl, []):
                                ax.plot(contour[:, 0], contour[:, 1],
                                        color=color, linewidth=1.5,
                                        label=f'{lvl*100:.0f} cGy')

                        # Remover duplicatas na legenda
                        handles, labels = ax.get_legend_handles_labels()
                        by_label = dict(zip(labels, handles))
                        ax.legend(by_label.values(), by_label.keys(),
                                  fontsize=7, facecolor='#1c2230',
                                  edgecolor='#30363d', labelcolor='#e6edf3')

                        ax.set_xlabel('X (mm)', color='#8b949e', fontsize=9)
                        ax.set_ylabel('Y (mm)', color='#8b949e', fontsize=9)
                        ax.set_title('Isodoses do TPS', color='#e6edf3', fontsize=10)
                        ax.tick_params(colors='#484f58', labelsize=7)
                        for sp in ax.spines.values():
                            sp.set_edgecolor('#30363d')
                        plt.tight_layout()
                        st.pyplot(fig, use_container_width=True)
                        plt.close(fig)

                    iso_contours = iso
                    st.session_state['tps_iso_contours'] = iso

            except Exception as e:
                st.error(f"❌ Erro ao ler RT Structure: {e}")
                import traceback
                with st.expander("Detalhes do erro"):
                    st.code(traceback.format_exc())

    # ── ABA 3: Pontos de Dose ──────────────────────────────────────────────
    with tab_pts:
        st.markdown("**Arquivo CSV/TXT com pontos de dose exportados do Monaco**")

        st.markdown("""
        **Formatos aceitos:**
        ```
        Name,X[mm],Y[mm],Z[mm],Dose[cGy]
        Centro,0.0,0.0,0.0,100.0
        P1,10.0,0.0,0.0,98.5
        P2,-10.0,0.0,0.0,98.3
        ```
        Separadores aceitos: vírgula, ponto-e-vírgula, tab ou espaço.
        """)

        f_pts = st.file_uploader(
            "Selecionar CSV de Pontos", type=['csv', 'txt'],
            key="tps_points_upload"
        )

        if f_pts:
            try:
                pts = read_dose_points_csv(f_pts)
                if not pts.points:
                    st.warning("Nenhum ponto encontrado. Verifique o formato do arquivo.")
                else:
                    st.success(f"✅ {len(pts.points)} pontos carregados.")
                    df_pts = pts.to_dataframe()
                    st.dataframe(df_pts, use_container_width=True, hide_index=True)

                    dose_points = pts
                    st.session_state['tps_dose_points'] = pts

            except Exception as e:
                st.error(f"❌ Erro ao ler CSV de pontos: {e}")

    return dose_dist, iso_contours, dose_points
