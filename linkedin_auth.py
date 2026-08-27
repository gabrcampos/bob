#!/usr/bin/env python3
"""
Autenticação OAuth 2.0 do LinkedIn para a página da Tecnosolve.
Gera o LINKEDIN_ACCESS_TOKEN e salva em config/linkedin_token.json.

Pré-requisito no painel LinkedIn Developer:
  1. Acesse developers.linkedin.com → seu app → Auth
  2. Em "Authorized Redirect URLs", adicione: http://localhost:8765/callback
  3. Certifique-se de ter o produto "Share on LinkedIn" e/ou "Marketing Developer Platform"

Uso:
  python3 linkedin_auth.py
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI  = "http://localhost:8765/callback"
SCOPES        = "w_member_social"
TOKEN_FILE    = Path("config/linkedin_token.json")


def _trocar_codigo(code: str) -> dict:
    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  REDIRECT_URI,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("LINKEDIN_CLIENT_ID e LINKEDIN_CLIENT_SECRET precisam estar no .env")
        sys.exit(1)

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
    })
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"

    print("\n=== LinkedIn OAuth 2.0 — Fluxo Manual ===")
    print("\nPasso 1: Abra esta URL no seu browser:")
    print(f"\n{auth_url}\n")
    print("Passo 2: Autorize o acesso.")
    print("Passo 3: O browser vai tentar abrir localhost:8765 e dar erro de conexão — isso é normal.")
    print("Passo 4: Copie a URL COMPLETA da barra do browser (começa com http://localhost:8765/callback?code=...)")
    print()

    url_retorno = input("Cole aqui a URL completa: ").strip()

    parsed = urllib.parse.urlparse(url_retorno)
    params_retorno = urllib.parse.parse_qs(parsed.query)
    code = params_retorno.get("code", [None])[0]
    error = params_retorno.get("error", [None])[0]

    if error:
        print(f"LinkedIn retornou erro: {error}")
        sys.exit(1)
    if not code:
        print("Código não encontrado na URL. Verifique se copiou a URL completa.")
        sys.exit(1)

    print("Trocando código por token...")
    try:
        token_data = _trocar_codigo(code)
    except Exception as e:
        print(f"Erro ao trocar código: {e}")
        sys.exit(1)

    access_token = token_data.get("access_token", "")
    expires_in   = token_data.get("expires_in", 0)

    if not access_token:
        print(f"Token não encontrado na resposta: {token_data}")
        sys.exit(1)

    org_id = os.getenv("LINKEDIN_ORG_ID", "515795")

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({
        "access_token": access_token,
        "expires_in":   expires_in,
        "org_id":       org_id,
    }, indent=2))

    print(f"\nToken obtido! Expira em {expires_in // 86400} dias.")
    print(f"Salvo em {TOKEN_FILE}")
    print(f"\nAdicione ao .env:")
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")


if __name__ == "__main__":
    main()
