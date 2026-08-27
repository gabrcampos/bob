#!/usr/bin/env python3
"""
Rotina diária: gera post LinkedIn para Tecnosolve, revisa com Gemini
e envia ao Telegram para aprovação com botões inline.

Executar via cron (ex: 08:00 todo dia útil):
  0 8 * * 1-5 cd /home/campos_1122/bob && python3 rotina_linkedin_tecnosolve.py

Fluxo:
  1. Sugere temas relevantes com Google Search
  2. Gera post LinkedIn (texto completo)
  3. Gemini revisa qualidade e precisão técnica
  4. Envia revisão + post ao Telegram com botões [✅ Publicar] [❌ Descartar]
  5. telegram_listener.py processa a resposta e publica se aprovado
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from modulos import llm_brain
from modulos.revisor_ia import revisar_linkedin
from modulos.telegram_bot import enviar_mensagem, enviar_com_botoes
from modulos.db import salvar_conteudo, buscar_empresa

EMPRESA_ID = "tecnosolve"


def _emoji_nota(nota: int) -> str:
    if nota >= 8:
        return "🟢"
    if nota >= 6:
        return "🟡"
    return "🔴"


def main():
    emp = buscar_empresa(EMPRESA_ID)
    if not emp:
        print(f"[LinkedIn] Empresa '{EMPRESA_ID}' não encontrada.")
        sys.exit(1)

    nome    = emp["nome"]
    publico = emp["publico_alvo"]
    url     = emp.get("url_site", "")

    # ── 1. Sugerir tema ───────────────────────────────────────────
    print("[1/4] Sugerindo temas...")
    try:
        temas = llm_brain.sugerir_temas(
            empresa=nome,
            empresa_id=EMPRESA_ID,
            publico_alvo=publico,
            url_site=url,
        )
        tema = temas[0] if temas else "Gestão de infraestrutura de TI no varejo"
        print(f"   Tema: {tema}")
    except Exception as e:
        print(f"   Erro ao sugerir temas ({e}). Usando padrão.")
        tema = "Infraestrutura de TI e eficiência operacional no varejo"

    # ── 2. Gerar post LinkedIn ────────────────────────────────────
    print(f"[2/4] Gerando post LinkedIn...")
    post_text = llm_brain.gerar_linkedin(
        tema=tema,
        empresa=nome,
        empresa_id=EMPRESA_ID,
        publico_alvo=publico,
        url_site=url,
    )
    print(f"   {len(post_text)} caracteres.")

    # ── 3. Revisão Gemini ─────────────────────────────────────────
    print("[3/4] Revisando com Gemini...")
    revisao  = revisar_linkedin(post_text, tema, nome, publico)
    nota     = revisao.get("nota", 7)
    parecer  = revisao.get("parecer", "APROVADO")
    obs      = revisao.get("observacoes", "")
    aprovado = revisao.get("aprovado", True)
    print(f"   {parecer} | Nota: {nota}/10")

    # ── 4. Salvar no banco ────────────────────────────────────────
    conteudo_id = salvar_conteudo(
        empresa_id=EMPRESA_ID,
        empresa_nome=nome,
        tipo="linkedin",
        tema=tema,
        post_linkedin=post_text,
        publico_alvo=publico,
    )
    print(f"   ID: {conteudo_id}")

    # ── 5. Enviar ao Telegram ─────────────────────────────────────
    print("[4/4] Enviando ao Telegram...")

    emoji = _emoji_nota(nota)
    status_icon = "✅" if aprovado else "⚠️"

    msg_revisao = (
        f"🤖 <b>REVISÃO GEMINI — LinkedIn Tecnosolve</b>\n"
        f"📌 Tema: <i>{tema}</i>\n\n"
        f"{emoji} <b>{parecer}</b>  |  Nota: {nota}/10\n\n"
        f"{status_icon} {obs}"
    )
    enviar_mensagem(msg_revisao)

    # Trunca o post se necessário (limite Telegram: 4096 chars)
    preview = post_text if len(post_text) <= 3600 else post_text[:3600] + "\n\n<i>...(truncado)</i>"
    msg_post = f"📝 <b>Post LinkedIn para aprovação:</b>\n\n{preview}"
    enviar_com_botoes(msg_post, conteudo_id, "linkedin")

    print("   Enviado! Aguardando sua aprovação no Telegram.")


if __name__ == "__main__":
    main()
