"""
Helpers para Telegram: envio de mensagens, documentos e inline keyboards.
Centraliza toda comunicação com a API do Telegram.
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()


def _bot() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def _url(metodo: str) -> str:
    return f"https://api.telegram.org/bot{_bot()}/{metodo}"


# ─────────────────────────────────────────────
# Envio
# ─────────────────────────────────────────────

def enviar_mensagem(texto: str, parse_mode: str = "HTML") -> int:
    """Envia mensagem de texto. Retorna message_id."""
    resp = requests.post(_url("sendMessage"), json={
        "chat_id": _chat(),
        "text": texto[:4096],
        "parse_mode": parse_mode,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]["message_id"]


def enviar_com_botoes(
    texto: str,
    conteudo_id: str,
    tipo: str,
    parse_mode: str = "HTML",
) -> int:
    """
    Envia mensagem com botões inline [✅ Publicar] [❌ Descartar].
    conteudo_id: _id do MongoDB do conteúdo.
    tipo: 'linkedin' | 'blog'.
    Retorna message_id.
    """
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Publicar",  "callback_data": f"aprovar:{tipo}:{conteudo_id}"},
            {"text": "❌ Descartar", "callback_data": f"reprovar:{tipo}:{conteudo_id}"},
        ]]
    }
    resp = requests.post(_url("sendMessage"), json={
        "chat_id": _chat(),
        "text": texto[:4096],
        "parse_mode": parse_mode,
        "reply_markup": keyboard,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]["message_id"]


def enviar_documento(caminho: Path, caption: str = "") -> int:
    """Envia arquivo (PDF, imagem, etc). Retorna message_id."""
    with open(caminho, "rb") as f:
        resp = requests.post(_url("sendDocument"), data={
            "chat_id": _chat(),
            "caption": caption[:1024],
        }, files={"document": f}, timeout=60)
    resp.raise_for_status()
    return resp.json()["result"]["message_id"]


def enviar_foto(caminho: Path, caption: str = "") -> int:
    """Envia imagem como foto. Retorna message_id."""
    with open(caminho, "rb") as f:
        resp = requests.post(_url("sendPhoto"), data={
            "chat_id": _chat(),
            "caption": caption[:1024],
        }, files={"photo": f}, timeout=60)
    resp.raise_for_status()
    return resp.json()["result"]["message_id"]


# ─────────────────────────────────────────────
# Polling de updates (para o listener)
# ─────────────────────────────────────────────

def get_updates(offset: int = 0, timeout: int = 5) -> list[dict]:
    """Retorna lista de updates pendentes."""
    resp = requests.get(_url("getUpdates"), params={
        "offset": offset,
        "timeout": timeout,
        "allowed_updates": ["callback_query", "message"],
    }, timeout=timeout + 10)
    if resp.ok:
        return resp.json().get("result", [])
    return []


def responder_callback(callback_query_id: str, texto: str = ""):
    """Confirma recebimento de callback_query (remove o loading no botão)."""
    requests.post(_url("answerCallbackQuery"), json={
        "callback_query_id": callback_query_id,
        "text": texto,
    }, timeout=10)
