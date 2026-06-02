"""
calibration_engine.py — Ponte entre os ROIs dos filmes e a curva de calibracao.

Faz:
  1. Extrai o valor medio do canal vermelho no ROI de cada filme.
  2. Identifica o filme de dose zero (background) automaticamente.
  3. Calcula o NOD de cada filme (usando image_proc do usuario).
  4. Ajusta todos os modelos (calibration.py do usuario).
  5. Gera uma recomendacao de equacao com justificativa (literatura + R2).

Referencias das recomendacoes:
  - Funcao racional X(D)=a+b/(D-c): recomendada pela Ashland/Gafchromic.
  - Logaritmica: melhor em doses baixas (0-2 Gy).
  - Racional/potencia: melhor em faixa ampla (ate 10 Gy).
"""

import numpy as np


def red_channel_mean_in_roi(image_rgb, bbox_film, roi_bbox):
    """
    Retorna a media do canal vermelho dentro do ROI de um filme.

    Args:
        image_rgb: imagem completa (H,W,3) ou (H,W).
        bbox_film: (minr,minc,maxr,maxc) do filme na imagem completa.
        roi_bbox: (minr,minc,maxr,maxc) do ROI, em coords RELATIVAS ao recorte do filme.

    Returns:
        float: media do canal vermelho no ROI.
    """
    img = np.asarray(image_rgb)
    fminr, fminc, fmaxr, fmaxc = bbox_film
    crop = img[fminr:fmaxr, fminc:fmaxc]

    # Canal vermelho
    if crop.ndim == 3:
        # assume RGB (PIL); vermelho = canal 0
        red = crop[:, :, 0].astype(np.float64)
    else:
        red = crop.astype(np.float64)

    rminr, rminc, rmaxr, rmaxc = roi_bbox
    rminr = max(0, rminr); rminc = max(0, rminc)
    rmaxr = min(red.shape[0], rmaxr); rmaxc = min(red.shape[1], rmaxc)
    roi = red[rminr:rmaxr, rminc:rmaxc]
    if roi.size == 0:
        return float(np.mean(red))
    return float(np.mean(roi))


def compute_nod_values(red_means, dose_values, bit_depth=8):
    """
    Calcula o NOD de cada filme em relacao ao filme de dose zero.

    NOD = log10(R_background / R_irradiado), aproximado por valor de pixel:
        NOD_i = log10(PV_zero / PV_i)

    Args:
        red_means: lista de medias do canal vermelho (1 por filme).
        dose_values: lista de doses correspondentes.
        bit_depth: profundidade (nao usado diretamente aqui; PV ja e a reflectancia relativa).

    Returns:
        (nods, zero_index) — array de NOD e indice do filme zero.
        Se nao houver filme de dose zero, zero_index = None.
    """
    doses = np.asarray(dose_values, dtype=np.float64)
    pv = np.asarray(red_means, dtype=np.float64)

    # Identificar filme de dose zero
    zero_candidates = np.where(doses == 0)[0]
    if len(zero_candidates) == 0:
        return None, None

    zero_index = int(zero_candidates[0])
    pv_zero = pv[zero_index]
    pv_safe = np.clip(pv, 1e-6, None)
    pv_zero = max(pv_zero, 1e-6)

    nods = np.log10(pv_zero / pv_safe)
    return nods, zero_index


def fit_all_models(nods, doses):
    """
    Ajusta todos os modelos disponiveis e retorna metricas de cada um.

    Returns:
        lista de dicts: {"model", "r_squared", "rmse", "model_obj"} ordenada
        por R2 decrescente. Modelos que falharem sao ignorados.
    """
    from calibration import CalibrationData, fit_calibration

    # Excluir o ponto de dose zero do ajuste? Nao — mantem (NOD=0, Dose=0).
    data = CalibrationData(nod=np.asarray(nods), dose=np.asarray(doses))

    model_types = ["devic", "polynomial3", "power_law", "polynomial2", "log_linear"]
    results = []
    for mt in model_types:
        try:
            model = fit_calibration(data, model_type=mt)
            if np.isfinite(model.r_squared) and np.isfinite(model.rmse):
                results.append({
                    "model": mt,
                    "r_squared": float(model.r_squared),
                    "rmse": float(model.rmse),
                    "model_obj": model,
                })
        except Exception:
            continue

    results.sort(key=lambda r: r["r_squared"], reverse=True)
    return results


# Nomes amigaveis e justificativas
MODEL_INFO = {
    "devic": {
        "nome": "Devic (padrao do filme)",
        "formula": "Dose = a·NOD + b·NOD^n",
        "vantagem": "equacao padrao da dosimetria de filme (Devic et al.); passa pela "
                    "origem (0,0), e sempre crescente e e a forma validada na literatura "
                    "para EBT3/EBT4 (n tipico entre 2.4 e 2.9)",
    },
    "rational": {
        "nome": "Racional",
        "formula": "Dose = c + b/(a - NOD)",
        "vantagem": "forma racional do fabricante; util em alguns casos, mas sensivel "
                    "ao ajuste com poucos pontos",
    },
    "power_law": {
        "nome": "Potencia",
        "formula": "Dose = a·NOD^b",
        "vantagem": "muito usada com NOD; boa para faixas amplas de dose",
    },
    "polynomial3": {
        "nome": "Polinomial 3 grau",
        "formula": "Dose = a + b·NOD + c·NOD² + d·NOD³",
        "vantagem": "flexivel e comum na pratica clinica",
    },
    "polynomial2": {
        "nome": "Polinomial 2 grau",
        "formula": "Dose = a + b·NOD + c·NOD²",
        "vantagem": "simples; util com poucos pontos",
    },
    "log_linear": {
        "nome": "Logaritmica",
        "formula": "Dose = e^(a + b·ln(NOD))",
        "vantagem": "melhor precisao em doses baixas (0-2 Gy)",
    },
}


def recommend_model(fit_results, doses, unit="cGy"):
    """
    Gera a recomendacao de modelo com justificativa, combinando:
      - faixa de dose (literatura)
      - R2 real nos dados do usuario
      - comportamento fisico

    Returns:
        dict com "recommended" (model_type), "reasons" (lista de str),
        "best_r2_model" (o de melhor R2).
    """
    if not fit_results:
        return None

    doses = np.asarray(doses, dtype=np.float64)
    dose_max = float(np.max(doses))
    # Converter para Gy para comparar com a literatura
    dose_max_gy = dose_max / 100.0 if unit == "cGy" else dose_max

    best_r2 = fit_results[0]  # ja ordenado por R2
    reasons = []

    # Recomendacao: Devic e o padrao da dosimetria de filme em toda a faixa
    teorico = "devic"
    reasons.append(f"A equacao de Devic (Dose = a·NOD + b·NOD^n) e o padrao consagrado "
                   f"na dosimetria de filme radiocromico (Devic et al.). Ela passa pela "
                   f"origem (0,0), e sempre crescente e e validada para EBT3/EBT4.")
    if dose_max_gy <= 2.0:
        reasons.append(f"Para suas doses baixas (ate {dose_max:.0f} {unit}), a forma "
                       f"logaritmica tambem e uma alternativa citada na literatura.")

    # 2. Verificar se o teorico esta entre os disponiveis e seu R2
    disponiveis = {r["model"]: r for r in fit_results}
    if teorico in disponiveis:
        r2_teorico = disponiveis[teorico]["r_squared"]
        reasons.append(f"Nos seus dados, a {MODEL_INFO[teorico]['nome']} obteve "
                       f"R² = {r2_teorico:.4f}.")
        # Se o teorico tambem e o melhor R2, reforca
        if best_r2["model"] == teorico:
            reasons.append("Esse modelo tambem teve o melhor ajuste entre todos os testados — "
                           "recomendacao reforcada.")
            recommended = teorico
        else:
            # Se outro ajustou bem melhor, avisa
            if best_r2["r_squared"] - r2_teorico > 0.005:
                reasons.append(f"Atencao: o modelo {MODEL_INFO[best_r2['model']]['nome']} "
                               f"ajustou melhor (R² = {best_r2['r_squared']:.4f}). "
                               f"A teoria sugere a {MODEL_INFO[teorico]['nome']}, mas vale "
                               f"comparar os dois no grafico.")
                recommended = teorico  # mantem o teorico como recomendacao primaria
            else:
                recommended = teorico
    else:
        recommended = best_r2["model"]
        reasons.append(f"Recomendo a {MODEL_INFO[recommended]['nome']} por ter o melhor "
                       f"ajuste (R² = {best_r2['r_squared']:.4f}).")

    # 3. Aviso geral sobre numero de pontos
    n = len(doses)
    if n < 5:
        reasons.append(f"Voce tem {n} pontos. Para curvas confiaveis, o ideal sao 6-8 pontos "
                       f"(incluindo o filme nao irradiado), com doses bem distribuidas.")

    return {
        "recommended": recommended,
        "best_r2_model": best_r2["model"],
        "reasons": reasons,
    }
