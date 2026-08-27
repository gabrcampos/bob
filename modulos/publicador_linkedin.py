"""
Publicação de posts texto na página LinkedIn da empresa via API v2.

Autenticação:
  - Coloque LINKEDIN_ACCESS_TOKEN no .env (obtido via linkedin_auth.py)
  - Coloque LINKEDIN_ORG_ID no .env (número na URL linkedin.com/company/NUMERO)

Escopo OAuth necessário: w_organization_social
"""
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_TOKEN_FILE = Path("config/linkedin_token.json")
_LI_API = "https://api.linkedin.com/v2"


# ─────────────────────────────────────────────
# Token
# ─────────────────────────────────────────────

def _token() -> str:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    if token:
        return token
    if _TOKEN_FILE.exists():
        data = json.loads(_TOKEN_FILE.read_text())
        return data.get("access_token", "")
    raise RuntimeError(
        "LINKEDIN_ACCESS_TOKEN não encontrado. "
        "Execute linkedin_auth.py para autenticar ou adicione ao .env"
    )


def _org_id() -> str:
    org = os.getenv("LINKEDIN_ORG_ID")
    if not org:
        if _TOKEN_FILE.exists():
            data = json.loads(_TOKEN_FILE.read_text())
            org = data.get("org_id", "")
    if not org:
        raise RuntimeError("LINKEDIN_ORG_ID não encontrado no .env")
    return str(org).strip()


def ln_esta_autenticado() -> bool:
    try:
        token = _token()
        return bool(token)
    except Exception:
        return False


# ─────────────────────────────────────────────
# Publicação
# ─────────────────────────────────────────────

def publicar_post_texto(texto: str, org_id: str | None = None, access_token: str | None = None) -> str:
    """
    Publica post de texto na página LinkedIn da organização.
    Retorna o URN do post criado (ex: 'urn:li:ugcPost:1234567890').
    """
    token = access_token or _token()
    oid   = org_id or _org_id()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    payload = {
        "author": f"urn:li:organization:{oid}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": texto[:3000]
                },
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = requests.post(f"{_LI_API}/ugcPosts", json=payload, headers=headers, timeout=30)

    if not resp.ok:
        raise RuntimeError(
            f"LinkedIn API erro {resp.status_code}: {resp.text[:300]}"
        )

    post_urn = resp.headers.get("x-restli-id") or resp.json().get("id", "")
    print(f"[LinkedIn] Post publicado: {post_urn}")
    return post_urn


# ─────────────────────────────────────────────
# Verificação do token
# ─────────────────────────────────────────────

def verificar_token(access_token: str | None = None) -> dict:
    """Verifica se o token está válido e retorna info do perfil/organização."""
    token = access_token or _token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{_LI_API}/me", headers=headers, timeout=15)
    if resp.ok:
        return resp.json()
    raise RuntimeError(f"Token inválido: {resp.status_code} {resp.text[:200]}")
