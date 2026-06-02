# Guia de Configuração — Chromis WEB

Este guia explica como configurar o Chromis WEB para rodar com todas as
funcionalidades: cadastro de usuários, aprovação por email e notificações.

---

## 1. Estrutura do projeto

```
chromis/
├── app.py                  ← aplicativo principal (rode este)
├── admin_panel.py          ← painel de aprovação de cadastros
├── i18n.py                 ← traduções PT/EN
├── theme.py                ← tema escuro e componentes
├── requirements.txt        ← dependências
├── .gitignore              ← protege seus secrets
├── .streamlit/
│   ├── config.toml         ← tema escuro do Streamlit
│   └── secrets.toml.example ← MODELO (renomeie e preencha)
├── assets/                 ← logos (PNG)
├── auth/                   ← login, cadastro, notificações
├── views/                  ← telas dos módulos
└── (engines)               ← calibration.py, gamma_engine.py, etc.
```

---

## 2. Rodar localmente (no seu computador)

```bash
# 1. Instale Python 3.10+ e as dependências:
pip install -r requirements.txt

# 2. Rode o app:
streamlit run app.py

# 3. (Opcional) Rode o painel admin em outra aba:
streamlit run admin_panel.py
```

---

## 3. Configurar o envio de emails (IMPORTANTE)

As notificações por email (cadastros, atividades, relatórios) precisam de
credenciais. **Elas nunca vão para o GitHub** — ficam só nos "secrets".

### Passo 1 — Criar uma senha de app no Gmail

1. Acesse https://myaccount.google.com/apppasswords (logado em chromisweb@gmail.com)
2. Crie uma senha de app chamada "Chromis WEB"
3. O Google vai gerar uma senha de 16 letras (ex: `abcd efgh ijkl mnop`)
4. **Guarde essa senha** — ela substitui a senha normal só para o envio

> Obs.: você precisa ter a verificação em duas etapas ativada na conta Google
> para o "senhas de app" aparecer.

### Passo 2 — Preencher os secrets

**Localmente:** crie o arquivo `.streamlit/secrets.toml` (copie do `.example`):

```toml
[smtp]
host = "smtp.gmail.com"
port = 587
user = "chromisweb@gmail.com"
app_password = "abcd efgh ijkl mnop"   # a senha de app do passo 1

[admin]
password = "escolha-uma-senha-forte"   # para entrar no admin_panel
```

**No Streamlit Cloud:** vá em Settings → Secrets e cole o mesmo conteúdo.

---

## 4. Como funciona o fluxo de cadastro

1. Usuário clica em **"Fazer cadastro"** na tela de login
2. Preenche nome, email e senha (ou usa Google — ver seção 6)
3. Você (admin) **recebe um email** em chromisweb@gmail.com avisando do pedido
4. Você abre o **admin_panel.py**, digita sua senha de admin, e **aprova ou recusa**
5. Após aprovado, o usuário consegue fazer login

---

## 5. Notificações que você recebe

- **Novo cadastro** → email com nome e email do solicitante
- **Atividades** → quando o usuário conclui setup, carrega imagens, gera análises
- **Relatórios** → o PDF gerado pelo usuário chega anexado no seu email

Tudo vai para **chromisweb@gmail.com**.

---

## 6. Login com Google (opcional, configuração avançada)

A estrutura já está pronta, mas requer criar credenciais OAuth:

1. Acesse https://console.cloud.google.com/apis/credentials
2. Crie um "OAuth 2.0 Client ID" do tipo "Web application"
3. Adicione a URL do seu app em "Authorized redirect URIs"
4. Copie o Client ID e Secret para os secrets (seção `[google_oauth]`)

> Sem essa configuração, o botão "Cadastrar com Google" apenas avisa que
> precisa ser configurado — o cadastro por email funciona normalmente.

---

## 7. Subir para o GitHub

```bash
cd chromis
git init
git add .
git commit -m "Chromis WEB - versão inicial"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/ChromisWEB.git
git push -u origin main
```

O `.gitignore` **garante** que `secrets.toml` e `users.json` NÃO sejam enviados.
Confirme com `git status` antes do commit — esses arquivos não devem aparecer.

---

## 8. Deploy no Streamlit Cloud

1. Acesse https://share.streamlit.io
2. Conecte sua conta GitHub e selecione o repositório ChromisWEB
3. Arquivo principal: `app.py`
4. Em **Advanced settings → Secrets**, cole o conteúdo do seu secrets.toml
5. Deploy!

---

## Observação sobre persistência de dados

No Streamlit Cloud, o sistema de arquivos é **temporário** — o `users.json`
pode ser apagado em reinícios. Para um sistema de produção real com muitos
usuários, recomenda-se conectar um banco de dados externo (Google Sheets,
Supabase ou Firebase). O código está organizado para facilitar essa troca
no futuro (ver `auth/accounts.py`, funções `_load_users` / `_save_users`).
