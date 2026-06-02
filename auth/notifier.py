"""
notifier.py — Envio de notificações por email para o administrador.

IMPORTANTE — SEGURANÇA:
  As credenciais NUNCA ficam no código. Elas são lidas de st.secrets,
  que você configura no painel do Streamlit Cloud (Settings → Secrets)
  ou localmente em .streamlit/secrets.toml (que está no .gitignore).

  Veja o arquivo .streamlit/secrets.toml.example para o formato.

Como funciona o envio:
  Usa SMTP do Gmail. Você precisa criar uma "Senha de app" na sua conta
  Google (https://myaccount.google.com/apppasswords) — não use a senha
  normal da conta. Cole essa senha de app nos secrets.

Se os secrets não estiverem configurados, as funções apenas registram
no log e retornam False, sem quebrar o app.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

import streamlit as st

# Email do administrador que recebe as notificações
ADMIN_EMAIL = "chromisweb@gmail.com"


def _get_smtp_config():
    """
    Lê config SMTP dos secrets. Retorna dict ou None se não configurado.
    Espera em st.secrets:
        [smtp]
        host = "smtp.gmail.com"
        port = 587
        user = "chromisweb@gmail.com"
        app_password = "xxxx xxxx xxxx xxxx"
    """
    try:
        smtp = st.secrets.get("smtp", None)
        if not smtp:
            return None
        return {
            "host": smtp.get("host", "smtp.gmail.com"),
            "port": int(smtp.get("port", 587)),
            "user": smtp["user"],
            "app_password": smtp["app_password"],
        }
    except Exception:
        return None



def send_email_diagnostic(subject: str, body_html: str, attachments=None):
    """Envia email e RETORNA (sucesso, mensagem) com diagnóstico detalhado."""
    cfg = _get_smtp_config()
    if cfg is None:
        return False, "Secao [smtp] nao encontrada nos Secrets ou campo faltando."

    app_pwd = cfg["app_password"].replace(" ", "")
    if len(app_pwd) != 16:
        return False, (f"A senha de app tem {len(app_pwd)} caracteres "
                       f"(deveria ter 16 sem espacos). Verifique a senha de app do Google.")
    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["user"]
        msg["To"] = ADMIN_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        if attachments:
            for fname, fbytes in attachments:
                part = MIMEApplication(fbytes, Name=fname)
                part["Content-Disposition"] = f'attachment; filename="{fname}"'
                msg.attach(part)
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.starttls(context=context)
            server.login(cfg["user"], app_pwd)
            server.send_message(msg)
        return True, f"Email enviado com sucesso para {ADMIN_EMAIL}!"
    except smtplib.SMTPAuthenticationError as e:
        return False, ("Erro de autenticacao: senha de app ou email incorretos. "
                       f"Detalhe: {e}")
    except Exception as e:
        return False, f"Erro: {type(e).__name__}: {e}"


def _send_email(subject: str, body_html: str, attachments=None) -> bool:
    """
    Envia um email para ADMIN_EMAIL.
    attachments: lista de tuplas (filename, bytes) — opcional.
    Retorna True se enviou, False caso contrário.
    """
    cfg = _get_smtp_config()
    if cfg is None:
        # Secrets não configurados — não quebra o app
        print(f"[notifier] SMTP não configurado. Email '{subject}' não enviado.")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["user"]
        msg["To"] = ADMIN_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if attachments:
            for fname, fbytes in attachments:
                part = MIMEApplication(fbytes, Name=fname)
                part["Content-Disposition"] = f'attachment; filename="{fname}"'
                msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls(context=context)
            server.login(cfg["user"], cfg["app_password"].replace(" ", ""))
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[notifier] Erro ao enviar email: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────
# NOTIFICAÇÕES ESPECÍFICAS
# ──────────────────────────────────────────────────────────────────────────

def notify_registration_request(name: str, email: str, method: str = "email") -> bool:
    """Notifica o admin de um novo pedido de cadastro a aprovar."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    body = f"""
    <div style="font-family:sans-serif">
      <h2 style="color:#238636">Novo pedido de cadastro — Chromis WEB</h2>
      <p>Um usuário solicitou acesso ao sistema:</p>
      <ul>
        <li><b>Nome:</b> {name}</li>
        <li><b>Email:</b> {email}</li>
        <li><b>Método:</b> {method}</li>
        <li><b>Data:</b> {now}</li>
      </ul>
      <p>Para aprovar ou recusar, acesse o painel administrativo do Chromis WEB.</p>
    </div>
    """
    return _send_email(f"[Chromis WEB] Novo cadastro: {name}", body)


def notify_user_activity(user: str, action: str, details: str = "") -> bool:
    """Notifica o admin de uma atividade do usuário."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    body = f"""
    <div style="font-family:sans-serif">
      <h3 style="color:#1f6feb">Atividade no Chromis WEB</h3>
      <ul>
        <li><b>Usuário:</b> {user}</li>
        <li><b>Ação:</b> {action}</li>
        <li><b>Detalhes:</b> {details}</li>
        <li><b>Data:</b> {now}</li>
      </ul>
    </div>
    """
    return _send_email(f"[Chromis WEB] {action} — {user}", body)


def notify_report_generated(user: str, report_bytes: bytes,
                            filename: str = "relatorio.pdf",
                            summary: str = "") -> bool:
    """Envia o relatório gerado pelo usuário para o admin."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    body = f"""
    <div style="font-family:sans-serif">
      <h3 style="color:#238636">Relatório gerado — Chromis WEB</h3>
      <ul>
        <li><b>Usuário:</b> {user}</li>
        <li><b>Data:</b> {now}</li>
      </ul>
      <p>{summary}</p>
      <p>O relatório está em anexo.</p>
    </div>
    """
    return _send_email(
        f"[Chromis WEB] Relatório de {user}",
        body,
        attachments=[(filename, report_bytes)],
    )
