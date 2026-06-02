"""
accounts.py — Gerenciamento de contas e aprovação de cadastros.

ARMAZENAMENTO:
  Usa um arquivo JSON local (users.json) para guardar usuários e status.
  Em produção no Streamlit Cloud, o sistema de arquivos é efêmero — para
  persistência real, conecte um banco (ex: Google Sheets, Firebase, Supabase).
  A estrutura aqui já isola isso em funções fáceis de trocar depois.

STATUS de um usuário:
  "pending"  → cadastrou, aguardando aprovação do admin
  "approved" → pode entrar
  "rejected" → recusado

SEGURANÇA:
  Senhas são guardadas com hash (hashlib + salt). Nunca em texto puro.
  Login com Google é tratado à parte (ver google_auth.py).
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime

_USERS_FILE = Path(__file__).parent / "users.json"


def _load_users() -> dict:
    if _USERS_FILE.exists():
        try:
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_users(users: dict):
    _USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash_password(password: str, salt: str = None) -> tuple:
    """Retorna (hash, salt). Gera salt novo se não fornecido."""
    if salt is None:
        salt = secrets.token_hex(16)
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
