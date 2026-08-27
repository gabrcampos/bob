#!/usr/bin/env python3
"""
Rotina de geração de blog para Tecnosolve: gera artigo, revisa com Gemini,
gera imagem de capa e envia ao Telegram para aprovação.

Executar sob demanda ou via cron (ex: segunda-feira 09:00):
  0 9 * * 1 cd /home/campos_1122/bob && python3 rotina_blog_tecnosolve.py

Fluxo:
  1. Sugere temas
  2. Gera artigo em markdown (1.500-2.000 palavras)
  3. Gemini revisa qualidade editorial e precisão técnica
  4. Gera imagem de capa via Imagen
  5. Envia resumo + imagem ao Telegram com botões [✅ Publicar no Webflow] [❌ Descartar]
  6. telegram_listener.py envia ao Webflow como rascunho quando aprovado

Variáveis de ambiente necessárias:
  WEBFLOW_API_TOKEN_TECNOSOLVE   — token API do Webflow
  WEBFLOW_COLLECTION_ID_TECNOSOLVE — collection ID do blog
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from modulos import llm_brain
from modulos.revisor_ia import revisar_blog
from modulos.telegram_bot import enviar_mensagem, enviar_com_botoes, enviar_foto
from modulos.db import salvar_conteudo, buscar_empresa

EMPRESA_ID = "tecnosolve"


def _emoji_nota(nota: int) -> str:
    if nota >= 8:
        return "🟢"
    if nota >= 6:
        return "🟡"
    return "🔴"


def _extrair_titulo(blog_markdown: str) -> str:
    """Extrai o H1 do artigo como título."""
    for linha in blog_markdown.splitlines():
        linha = linha.strip()
        if linha.startswith("# "):
            return linha[2:].strip()
    return "Artigo sem título"


def _gerar_imagem_capa(prompt: str, stem: str, empresa_id: str) -> Path | None:
    """Gera imagem de capa via Imagen e salva localmente. Retorna Path ou None."""
    try:
        import base64
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        prompt_full = (
            f"Pure visual scene, absolutely NO text NO letters NO words NO numbers NO labels anywhere. "
            f"{prompt} "
            f"High resolution, suitable for a blog cover image, 16:9 aspect ratio, "
            f"professional corporate photography style. "
            f"Do not include any typography, signage, screens with text, or written content."
        )
        response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=prompt_full,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        img_bytes = response.generated_images[0].image.image_bytes
        if isinstance(img_bytes, str):
            img_bytes = base64.b64decode(img_bytes)

        pasta = Path(f"outputs/{empresa_id}/blog_capas")
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{stem}_capa.png"
        caminho.write_bytes(img_bytes)
        print(f"[Blog] Capa gerada: {caminho}")
        return caminho
    except Exception as e:
        print(f"[Blog] Aviso: não foi possível gerar imagem de capa: {e}")
        return None


def main():
    emp = buscar_empresa(EMPRESA_ID)
    if not emp:
        print(f"[Blog] Empresa '{EMPRESA_ID}' não encontrada.")
        sys.exit(1)

    nome    = emp["nome"]
    publico = emp["publico_alvo"]
    url     = emp.get("url_site", "")
    estilo  = emp.get("estilo_imagem", "")

    # ── 1. Sugerir tema ───────────────────────────────────────────
    print("[1/5] Sugerindo temas...")
    try:
        temas = llm_brain.sugerir_temas(
            empresa=nome,
            empresa_id=EMPRESA_ID,
            publico_alvo=publico,
            url_site=url,
        )
        # Usa o segundo tema (o primeiro foi para o LinkedIn do dia)
        tema = temas[1] if len(temas) > 1 else temas[0] if temas else "Gestão de TI no varejo"
        print(f"   Tema: {tema}")
    except Exception as e:
        print(f"   Erro ao sugerir temas ({e}). Usando padrão.")
        tema = "Modernização de infraestrutura de TI: estratégias para o varejo"

    # ── 2. Gerar artigo ───────────────────────────────────────────
    print(f"[2/5] Gerando artigo de blog...")
    blog_texto = llm_brain.gerar_blog(
        tema=tema,
        empresa=nome,
        empresa_id=EMPRESA_ID,
        publico_alvo=publico,
        url_site=url,
    )
    titulo = _extrair_titulo(blog_texto)
    palavras = len(blog_texto.split())
    print(f"   Título: {titulo}")
    print(f"   {palavras} palavras geradas.")

    # ── 3. Revisão Gemini ─────────────────────────────────────────
    print("[3/5] Revisando com Gemini...")
    revisao  = revisar_blog(titulo, blog_texto, tema, nome, publico)
    nota     = revisao.get("nota", 7)
    parecer  = revisao.get("parecer", "APROVADO")
    obs      = revisao.get("observacoes", "")
    aprovado = revisao.get("aprovado", True)
    print(f"   {parecer} | Nota: {nota}/10")

    # ── 4. Gerar imagem de capa ───────────────────────────────────
    print("[4/5] Gerando imagem de capa...")
    try:
        prompt_capa = llm_brain.gerar_prompt_capa_blog(
            tema=tema,
            blog_content=blog_texto,
            empresa_id=EMPRESA_ID,
            empresa_nome=nome,
            estilo_imagem=estilo,
        )
        print(f"   Prompt capa: {prompt_capa[:80]}...")
    except Exception as e:
        prompt_capa = f"Professional corporate technology scene related to {tema}"
        print(f"   Prompt capa fallback: {e}")

    # Gera slug simples para o stem
    import re
    stem = re.sub(r"[^a-z0-9]+", "_", tema.lower())[:40]
    caminho_capa = _gerar_imagem_capa(prompt_capa, stem, EMPRESA_ID)

    # ── 5. Salvar no banco ────────────────────────────────────────
    from modulos.db import atualizar_conteudo
    conteudo_id = salvar_conteudo(
        empresa_id=EMPRESA_ID,
        empresa_nome=nome,
        tipo="blog",
        tema=tema,
        blog=blog_texto,
        publico_alvo=publico,
    )
    if caminho_capa and caminho_capa.exists():
        atualizar_conteudo(conteudo_id, {"capa_path": str(caminho_capa)})
    print(f"   ID: {conteudo_id}")

    # ── 6. Enviar ao Telegram ─────────────────────────────────────
    print("[5/5] Enviando ao Telegram...")

    emoji    = _emoji_nota(nota)
    status_i = "✅" if aprovado else "⚠️"

    # Revisão
    msg_revisao = (
        f"🤖 <b>REVISÃO GEMINI — Blog Tecnosolve</b>\n"
        f"📌 Tema: <i>{tema}</i>\n"
        f"📖 Título: <i>{titulo}</i>\n"
        f"📊 {palavras} palavras\n\n"
        f"{emoji} <b>{parecer}</b>  |  Nota: {nota}/10\n\n"
        f"{status_i} {obs}"
    )
    enviar_mensagem(msg_revisao)

    # Imagem de capa (se gerada)
    if caminho_capa and caminho_capa.exists():
        try:
            enviar_foto(caminho_capa, caption=f"Capa sugerida: {titulo}")
        except Exception as e:
            print(f"   Aviso: não foi possível enviar foto: {e}")

    # Preview do blog (introdução)
    linhas = blog_texto.splitlines()
    intro_linhas = [l for l in linhas if l.strip() and not l.startswith("#")][:8]
    intro = "\n".join(intro_linhas)[:800]

    msg_blog = (
        f"📄 <b>Artigo para aprovação:</b>\n"
        f"<b>{titulo}</b>\n\n"
        f"{intro}\n\n"
        f"<i>...({palavras} palavras no total)</i>"
    )
    enviar_com_botoes(msg_blog, conteudo_id, "blog")

    print("   Enviado! Aguardando sua aprovação no Telegram.")


if __name__ == "__main__":
    main()
