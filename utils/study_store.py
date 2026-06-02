"""
study_store.py — Armazenamento central dos resultados do estudo.

Cada modulo (Setup, Upload, Calibracao, etc.) salva seus resultados aqui
conforme o usuario avanca. O relatorio le desta estrutura.

Tudo fica em st.session_state["study"], um dicionario organizado por modulo.
Isso permite gerar relatorios PARCIAIS (so os modulos concluidos) a qualquer
momento, sem precisar refazer nada.
"""

from datetime import datetime


def init_study(state):
    """Garante que a estrutura do estudo existe no estado."""
    if "study" not in state:
        state["study"] = {
            "created_at": datetime.now().isoformat(),
            "setup": None,        # dados do setup
            "tps": None,          # planejamento
            "upload": None,       # filmes carregados + doses
            "calibration": None,  # curva ajustada
            "dosemap": None,
            "isodose": None,
            "gamma": None,
            "point": None,
            "symmetry": None,
            "isocenter": None,
        }
    return state["study"]


def save_module(state, module_key, data):
    """
    Salva o resultado de um modulo no estudo.

    Args:
        module_key: "setup", "upload", "calibration", etc.
        data: dicionario com os resultados daquele modulo.
    """
    study = init_study(state)
    data = dict(data)
    data["_saved_at"] = datetime.now().isoformat()
    study[module_key] = data
    return study


def get_module(state, module_key):
    """Retorna os dados salvos de um modulo, ou None."""
    study = init_study(state)
    return study.get(module_key)


def completed_modules(state):
    """Retorna a lista de modulos que ja tem resultado salvo."""
    study = init_study(state)
    done = []
    for key, val in study.items():
        if key == "created_at":
            continue
        if val is not None:
            done.append(key)
    return done


def study_summary(state):
    """Retorna um resumo curto do que ja foi feito (para o dashboard)."""
    done = completed_modules(state)
    labels = {
        "setup": "Setup", "tps": "TPS", "upload": "Upload",
        "calibration": "Calibracao", "dosemap": "Mapa de dose",
        "isodose": "Isodose", "gamma": "Gamma", "point": "Dose pontual",
        "symmetry": "Simetria", "isocenter": "Isocentro",
    }
    return [labels.get(d, d) for d in done]
