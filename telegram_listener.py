#!/usr/bin/env python3
"""
Processa aprovações/rejeições de conteúdo pendentes no Telegram.
Executar via cron a cada 5 minutos:
  */5 * * * * cd /home/campos_1122/bob && python3 telegram_listener.py

Fluxo:
  1. Lê updates do Telegram (botões inline pressionados)
  2. Para 'aprovar': publica o conteúdo na plataforma correspondente
  3. Para 'reprovar': marca como reprovado no banco e notifica
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from modulos.telegram_bot import get_updates, responder_callback, enviar_mensagem
from modulos.db import buscar_conteudo, atualizar_conteudo, buscar_empresa

_OFFSET_FILE = "config/telegram_offset.json"


def _load_offset() -> int:
    try:
        return json.loads(open(_OFFSET_FILE).read()).get("offset", 0)
    except Exception:
        return 0


def _save_offset(offset: int):
    os.makedirs("config", exist_ok=True)
    with open(_OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


# ─────────────────────────────────────────────
# Handlers por tipo de conteúdo
# ─────────────────────────────────────────────

def _publicar_linkedin(conteudo_id: str) -> str:
    doc = buscar_conteudo(conteudo_id)
    if not doc:
        return "Conteúdo não encontrado no banco."
    if doc.get("status") in ("publicado", "publicado_webflow"):
        return "Conteúdo já publicado anteriormente — ignorando clique duplicado."

    post_text = doc.get("post_linkedin", "")
    if not post_text:
        return "Conteúdo não tem post_linkedin salvo."

    token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    org_id = os.getenv("LINKEDIN_ORG_ID")

    if not token:
        return "LINKEDIN_ACCESS_TOKEN não configurado no .env"
    if not org_id:
        return "LINKEDIN_ORG_ID não configurado no .env"

    try:
        from modulos.publicador_linkedin import publicar_post_texto
        post_urn = publicar_post_texto(post_text, org_id=org_id, access_token=token)
        atualizar_conteudo(conteudo_id, {
            "status": "publicado",
            "platform_post_id": post_urn,
        })
        tema = doc.get("tema", "")
        return f"Publicado no LinkedIn.\nTema: {tema}\nURN: {post_urn}"
    except Exception as e:
        atualizar_conteudo(conteudo_id, {"status": "erro_publicacao", "erro_msg": str(e)})
        return f"Erro ao publicar no LinkedIn: {e}"


def _publicar_blog_webflow(conteudo_id: str) -> str:
    doc = buscar_conteudo(conteudo_id)
    if not doc:
        return "Conteúdo não encontrado no banco."
    if doc.get("status") in ("publicado_webflow", "publicado"):
        return "Conteúdo já publicado anteriormente — ignorando clique duplicado."

    blog_text = doc.get("blog", "")
    if not blog_text:
        return "Conteúdo não tem blog salvo."

    empresa_id = doc.get("empresa_id", "")
    emp = buscar_empresa(empresa_id)

    token = (emp or {}).get("webflow_api_token") or os.getenv("WEBFLOW_API_TOKEN_TECNOSOLVE")
    col_id = (emp or {}).get("webflow_collection_id") or os.getenv("WEBFLOW_COLLECTION_ID_TECNOSOLVE")

    if not token:
        return "WEBFLOW_API_TOKEN_TECNOSOLVE não configurado no .env"
    if not col_id:
        return "WEBFLOW_COLLECTION_ID_TECNOSOLVE não configurado no .env"

    try:
        from modulos import webflow
        capa_path = doc.get("capa_path")
        result = webflow.enviar_post(token, col_id, doc["tema"], blog_text, imagem_path=capa_path)
        item_id = result.get("id", "")
        atualizar_conteudo(conteudo_id, {
            "status": "publicado_webflow",
            "webflow_item_id": item_id,
        })
        tema = doc.get("tema", "")
        return (
            f"Blog enviado ao Webflow como rascunho.\n"
            f"Tema: {tema}\n"
            f"Item ID: {item_id}\n"
            f"Acesse o painel Webflow para revisar e publicar."
        )
    except Exception as e:
        atualizar_conteudo(conteudo_id, {"status": "erro_publicacao", "erro_msg": str(e)})
        return f"Erro ao enviar ao Webflow: {e}"


_HANDLERS = {
    "linkedin": _publicar_linkedin,
    "blog":     _publicar_blog_webflow,
}


# ─────────────────────────────────────────────
# Loop principal
# ─────────────────────────────────────────────

def processar_updates():
    offset = _load_offset()
    updates = get_updates(offset)

    if not updates:
        return

    novo_offset = offset
    for update in updates:
        update_id = update["update_id"]
        novo_offset = max(novo_offset, update_id + 1)

        if "callback_query" not in update:
            continue

        cq = update["callback_query"]
        data = cq.get("data", "")
        callback_id = cq["id"]

        if ":" not in data:
            continue

        partes = data.split(":", 2)
        if len(partes) != 3:
            continue

        acao, tipo, conteudo_id = partes

        if acao == "aprovar":
            responder_callback(callback_id, "Processando...")
            handler = _HANDLERS.get(tipo)
            if handler:
                resultado = handler(conteudo_id)
                emoji = "✅" if "Erro" not in resultado else "❌"
                enviar_mensagem(f"{emoji} {resultado}")
            else:
                responder_callback(callback_id, "Tipo desconhecido.")
                enviar_mensagem(f"Tipo de conteúdo desconhecido: {tipo}")

        elif acao == "reprovar":
            responder_callback(callback_id, "Descartado.")
            atualizar_conteudo(conteudo_id, {"status": "reprovado"})
            enviar_mensagem(f"❌ Conteúdo descartado.\nID: {conteudo_id}")

    _save_offset(novo_offset)


if __name__ == "__main__":
    processar_updates()
