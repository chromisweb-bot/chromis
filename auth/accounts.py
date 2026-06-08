"""
accounts.py — Gerenciamento de contas e aprovação de cadastros.

ARMAZENAMENTO (PERSISTENTE):
  Usa uma planilha do Google Sheets como banco de dados, para que os
  cadastros SOBREVIVAM aos reinícios do Streamlit Cloud (cujo sistema de
  arquivos é efêmero). Toda a leitura/escrita está isolada em duas funções:
  _load_users() e _save_users(). O resto do sistema (register/login/approve)
  não sabe de onde vêm os dados — continua igual.

  Se o Google Sheets não estiver configurado nos Secrets (ex: rodando
  localmente sem credenciais), o sistema CAI AUTOMATICAMENTE para um arquivo
  local users.json, para não quebrar o app durante o desenvolvimento.

CONFIGURAÇÃO (Secrets do Streamlit):
    [gcp_service_account]
    ... (a chave JSON da conta de serviço, em formato TOML) ...

    [sheets]
    spreadsheet_id = "id-da-planilha"

  A planilha deve ter, na primeira aba, a linha de cabeçalho:
    name | email | method | status | password_hash | salt | created_at | approved_at

STATUS de um usuário:
  "pending"  -> cadastrou, aguardando aprovação do admin
  "approved" -> pode entrar
  "rejected" -> recusado

SEGURANÇA:
  Senhas são guardadas com hash PBKDF2-SHA256 + salt. Nunca em texto puro.
"""

import json
import hashlib
import secrets as _secrets
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PLANILHA
# ──────────────────────────────────────────────────────────────────────────

# Colunas da planilha, NESTA ordem. A primeira linha da planilha deve conter
# exatamente estes nomes como cabeçalho.
_COLUMNS = [
    "name", "email", "method", "status",
    "password_hash", "salt", "created_at", "approved_at",
]

# Índice da aba (worksheet) usada (0 = primeira aba).
_WORKSHEET_INDEX = 0

# Arquivo local de fallback (usado só se o Sheets não estiver configurado).
_USERS_FILE = Path(__file__).parent / "users.json"

# Cache do cliente gspread para não reconectar a cada chamada.
_GSPREAD_WS = None
_BACKEND = None  # "sheets" ou "local" — definido na primeira leitura.


# ──────────────────────────────────────────────────────────────────────────
# CONEXÃO COM O GOOGLE SHEETS
# ──────────────────────────────────────────────────────────────────────────

def _get_worksheet():
    """
    Retorna a worksheet do Google Sheets, ou None se não configurado.
    Conecta uma única vez e reaproveita (cache em _GSPREAD_WS).
    """
    global _GSPREAD_WS
    if _GSPREAD_WS is not None:
        return _GSPREAD_WS

    try:
        import streamlit as st
    except Exception:
        return None

    # Sem a seção de credenciais nos Secrets -> não há Sheets configurado.
    try:
        has_creds = ("gcp_service_account" in st.secrets) and ("sheets" in st.secrets)
    except Exception:
        has_creds = False
    if not has_creds:
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_info = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(credentials)

        spreadsheet_id = st.secrets["sheets"]["spreadsheet_id"]
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.get_worksheet(_WORKSHEET_INDEX)

        # Garante o cabeçalho na primeira linha (cria se a planilha estiver vazia).
        _ensure_header(ws)

        _GSPREAD_WS = ws
        return ws
    except Exception as e:
        # Falha de conexão -> loga e cai para o fallback local.
        print(f"[accounts] Falha ao conectar no Google Sheets: {type(e).__name__}: {e}")
        return None


def _ensure_header(ws):
    """Garante que a primeira linha da planilha tenha o cabeçalho correto."""
    try:
        first_row = ws.row_values(1)
    except Exception:
        first_row = []
    if [c.strip() for c in first_row] != _COLUMNS:
        if not first_row:
            ws.update("A1", [_COLUMNS])
        # Se já houver um cabeçalho diferente, NÃO sobrescreve (evita perder
        # dados de uma estrutura existente); apenas confia nos nomes de coluna.


# ──────────────────────────────────────────────────────────────────────────
# LEITURA / ESCRITA — as DUAS funções que isolam o armazenamento
# ──────────────────────────────────────────────────────────────────────────

def _row_to_user(row: dict) -> dict:
    """Converte uma linha da planilha (dict de strings) no dict de usuário."""
    user = {
        "name": row.get("name", ""),
        "email": (str(row.get("email", "")) or "").lower().strip(),
        "method": row.get("method", "email") or "email",
        "status": row.get("status", "pending") or "pending",
        "created_at": row.get("created_at", ""),
    }
    # Campos opcionais — só inclui se tiverem valor (preserva o formato original).
    if row.get("password_hash"):
        user["password_hash"] = str(row["password_hash"])
    if row.get("salt"):
        user["salt"] = str(row["salt"])
    if row.get("approved_at"):
        user["approved_at"] = str(row["approved_at"])
    return user


def _user_to_row(user: dict) -> list:
    """Converte um dict de usuário numa linha (lista) na ordem de _COLUMNS."""
    return [str(user.get(col, "") or "") for col in _COLUMNS]


def _load_users() -> dict:
    """
    Carrega todos os usuários como dict {email: {dados}}.
    Funciona com Google Sheets (persistente) ou arquivo local (fallback).
    """
    global _BACKEND
    ws = _get_worksheet()

    if ws is not None:
        _BACKEND = "sheets"
        try:
            records = ws.get_all_records()  # lista de dicts, usa a 1a linha como chave
        except Exception as e:
            print(f"[accounts] Erro ao ler a planilha: {e}")
            records = []
        users = {}
        for row in records:
            email = (str(row.get("email", "")) or "").lower().strip()
            if email:
                users[email] = _row_to_user(row)
        return users

    # ---- Fallback: arquivo local ----
    _BACKEND = "local"
    if _USERS_FILE.exists():
        try:
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_users(users: dict):
    """
    Salva o dict completo {email: {dados}}.
    No Sheets, reescreve a aba inteira (cabeçalho + uma linha por usuário).
    No fallback local, grava o users.json.
    """
    ws = _get_worksheet()

    if ws is not None:
        try:
            rows = [_COLUMNS]  # cabeçalho
            for user in users.values():
                rows.append(_user_to_row(user))
            ws.clear()
            ws.update("A1", rows)
            return
        except Exception as e:
            print(f"[accounts] Erro ao gravar na planilha: {e}")
            # Em caso de erro de escrita, tenta o fallback local p/ não perder o dado.

    # ---- Fallback: arquivo local ----
    _USERS_FILE.write_text(
        json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ──────────────────────────────────────────────────────────────────────────
# DAQUI PARA BAIXO: NADA MUDOU. A lógica continua idêntica à original.
# ──────────────────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str = None) -> tuple:
    """Retorna (hash, salt). Gera salt novo se não fornecido."""
    if salt is None:
        salt = _secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return h.hex(), salt


def register_user(name: str, email: str, password: str = None,
                  method: str = "email") -> tuple:
    """
    Registra um novo usuário com status 'pending'.
    Retorna (sucesso: bool, mensagem: str).
    """
    users = _load_users()
    email = email.lower().strip()

    if email in users:
        status = users[email].get("status")
        if status == "approved":
            return False, "Este email já está cadastrado e aprovado."
        elif status == "pending":
            return False, "Já existe um pedido pendente para este email."

    entry = {
        "name": name,
        "email": email,
        "method": method,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    if password and method == "email":
        pwd_hash, salt = _hash_password(password)
        entry["password_hash"] = pwd_hash
        entry["salt"] = salt

    users[email] = entry
    _save_users(users)
    return True, "Cadastro enviado! Aguarde a aprovação do administrador."


def verify_login(email: str, password: str) -> tuple:
    """
    Verifica credenciais. Retorna (sucesso, mensagem, user_dict|None).
    """
    users = _load_users()
    email = email.lower().strip()

    user = users.get(email)
    if user is None:
        return False, "Usuário não encontrado.", None
    if user.get("status") == "pending":
        return False, "Seu cadastro ainda está aguardando aprovação.", None
    if user.get("status") == "rejected":
        return False, "Seu cadastro não foi aprovado.", None

    if user.get("method") == "email":
        pwd_hash, _ = _hash_password(password, user.get("salt", ""))
        if pwd_hash != user.get("password_hash"):
            return False, "Senha incorreta.", None

    return True, "Login realizado.", user


def approve_user(email: str) -> bool:
    users = _load_users()
    email = email.lower().strip()
    if email in users:
        users[email]["status"] = "approved"
        users[email]["approved_at"] = datetime.now().isoformat()
        _save_users(users)
        return True
    return False


def reject_user(email: str) -> bool:
    users = _load_users()
    email = email.lower().strip()
    if email in users:
        users[email]["status"] = "rejected"
        _save_users(users)
        return True
    return False


def list_pending() -> list:
    """Retorna lista de usuários pendentes de aprovação."""
    users = _load_users()
    return [u for u in users.values() if u.get("status") == "pending"]
