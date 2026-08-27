#!/usr/bin/env python3
"""
Pipeline completo de geração de blog para a Tecnosolve.

Uso:
  python3 gerar_blog_tecnosolve.py                   # tema escolhido automaticamente
  python3 gerar_blog_tecnosolve.py "Meu tema aqui"   # tema passado manualmente

Fluxo:
  1. Escolhe tema ainda não publicado
  2. Gera artigo (1.500-2.000 palavras) com Gemini + Google Search
  3. Revisa com Gemini (nota /10)
  4. Corrige automaticamente se nota < 8
  5. Gera imagem de capa via Imagen
  6. Sobe ao Webflow como rascunho
  7. Salva no MongoDB com status publicado_webflow
"""
import os
import re
import sys
import base64
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from modulos import llm_brain, webflow
from modulos.revisor_ia import revisar_blog
from modulos.db import salvar_conteudo, atualizar_conteudo, buscar_empresa, col_conteudos

EMPRESA_ID = "tecnosolve"


def _temas_usados() -> set:
    docs = col_conteudos().find({"empresa_id": EMPRESA_ID}, {"tema": 1})
    return {d["tema"] for d in docs if "tema" in d}


def _escolher_tema(tema_arg: str | None, emp: dict) -> str:
    if tema_arg:
        print(f"[1/6] Tema fornecido: {tema_arg}")
        return tema_arg

    print("[1/6] Escolhendo tema não publicado...")
    usados = _temas_usados()
    temas = llm_brain.sugerir_temas(
        empresa=emp["nome"],
        empresa_id=EMPRESA_ID,
        publico_alvo=emp["publico_alvo"],
        url_site=emp.get("url_site", ""),
    )
    for t in temas:
        if t not in usados:
            print(f"   Tema escolhido: {t}")
            return t
    tema = temas[0]
    print(f"   (todos sugeridos já usados) Usando: {tema}")
    return tema


def _extrair_titulo(blog: str) -> str:
    for linha in blog.splitlines():
        linha = linha.strip()
        if linha.startswith("# "):
            return linha[2:].strip()
    return "Artigo sem título"


def _corrigir_blog(blog: str, observacoes: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = f"""Você é um editor especialista em conteúdo B2B para tecnologia corporativa.
O artigo abaixo foi revisado e recebeu as seguintes observações de melhoria:

OBSERVAÇÕES: {observacoes}

ARTIGO ORIGINAL (Markdown):
{blog}

Reescreva o artigo corrigindo especificamente os problemas indicados nas observações.
Mantenha o mesmo tema, estrutura e título. Apenas corrija o que foi sinalizado.
Retorne apenas o artigo corrigido em Markdown, sem comentários adicionais.

REGRAS OBRIGATÓRIAS:
- Proibido: "apagar incêndios", "modo crise", "no mundo de hoje", "descubra como",
  "você sabia que", "transformação digital" (uso genérico), "inovação disruptiva"
- Estatísticas sem fonte devem ser removidas ou atribuídas a uma fonte real
- Manter entre 1.500 e 2.000 palavras
- Tom: técnico, direto, focado em CIO/CTO do varejo brasileiro"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )
    return (response.text or blog).strip()


def _gerar_imagem_capa(prompt_especifico: str, stem: str) -> Path | None:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        prompt_full = (
            "Pure visual scene, absolutely NO text NO letters NO words NO numbers NO labels anywhere. "
            f"{prompt_especifico} "
            "High resolution, blog cover image, 16:9 aspect ratio, "
            "professional corporate photography style. "
            "No typography, signage, screens with text, or written content."
        )
        response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=prompt_full,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        img_bytes = response.generated_images[0].image.image_bytes
        if isinstance(img_bytes, str):
            img_bytes = base64.b64decode(img_bytes)

        pasta = Path(f"outputs/{EMPRESA_ID}/blog_capas")
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{stem}_capa.png"
        caminho.write_bytes(img_bytes)
        print(f"[5/6] Capa: {caminho} ({len(img_bytes) // 1024} KB)")
        return caminho
    except Exception as e:
        print(f"[5/6] Aviso: imagem de capa não gerada — {e}")
        return None


def main(tema_arg: str | None = None):
    emp = buscar_empresa(EMPRESA_ID)
    if not emp:
        print(f"ERRO: empresa '{EMPRESA_ID}' não encontrada no banco.")
        sys.exit(1)

    # ── 1. Tema ───────────────────────────────────────────────────────────────
    tema = _escolher_tema(tema_arg, emp)

    # ── 2. Geração ────────────────────────────────────────────────────────────
    print(f"[2/6] Gerando artigo...")
    blog = llm_brain.gerar_blog(
        tema=tema,
        empresa=emp["nome"],
        empresa_id=EMPRESA_ID,
        publico_alvo=emp["publico_alvo"],
        url_site=emp.get("url_site", ""),
    )
    titulo = _extrair_titulo(blog)
    palavras = len(blog.split())
    print(f"   Título: {titulo}")
    print(f"   {palavras} palavras geradas")

    conteudo_id = salvar_conteudo(
        empresa_id=EMPRESA_ID,
        empresa_nome=emp["nome"],
        tipo="blog",
        tema=tema,
        blog=blog,
        publico_alvo=emp["publico_alvo"],
    )
    print(f"   ID no banco: {conteudo_id}")

    # ── 3. Revisão ────────────────────────────────────────────────────────────
    print(f"[3/6] Revisando com Gemini...")
    revisao = revisar_blog(titulo, blog, tema, emp["nome"], emp["publico_alvo"])
    nota = revisao.get("nota", 7)
    parecer = revisao.get("parecer", "APROVADO")
    obs = revisao.get("observacoes", "")
    print(f"   {parecer} | Nota: {nota}/10")
    if obs:
        print(f"   {obs}")

    # ── 4. Correção ───────────────────────────────────────────────────────────
    if nota < 8 and obs:
        print(f"[4/6] Corrigindo (nota {nota}/10)...")
        blog = _corrigir_blog(blog, obs)
        titulo = _extrair_titulo(blog)
        atualizar_conteudo(conteudo_id, {"blog": blog})

        revisao2 = revisar_blog(titulo, blog, tema, emp["nome"], emp["publico_alvo"])
        nota = revisao2.get("nota", nota)
        print(f"   Pós-correção: {revisao2.get('parecer')} | Nota: {nota}/10")
    else:
        print(f"[4/6] Artigo aprovado sem correções.")

    # ── 5. Imagem de capa ─────────────────────────────────────────────────────
    print(f"[5/6] Gerando imagem de capa...")
    try:
        prompt_capa = llm_brain.gerar_prompt_capa_blog(
            tema=tema,
            blog_content=blog,
            empresa_id=EMPRESA_ID,
            empresa_nome=emp["nome"],
            estilo_imagem=emp.get("estilo_imagem", ""),
        )
    except Exception as e:
        prompt_capa = f"Professional corporate technology scene related to {tema}, modern office, blue tones"
        print(f"   Prompt fallback: {e}")

    stem = re.sub(r"[^a-z0-9]+", "_", tema.lower())[:40]
    caminho_capa = _gerar_imagem_capa(prompt_capa, stem)
    if caminho_capa:
        atualizar_conteudo(conteudo_id, {"capa_path": str(caminho_capa)})

    # ── 6. Webflow ────────────────────────────────────────────────────────────
    print(f"[6/6] Subindo ao Webflow como rascunho...")
    token = os.getenv("WEBFLOW_API_TOKEN_TECNOSOLVE")
    col_id = os.getenv("WEBFLOW_COLLECTION_ID_TECNOSOLVE")
    if not token or not col_id:
        print("ERRO: WEBFLOW_API_TOKEN_TECNOSOLVE ou WEBFLOW_COLLECTION_ID_TECNOSOLVE ausentes no .env")
        sys.exit(1)

    result = webflow.enviar_post(token, col_id, titulo, blog, imagem_path=caminho_capa)
    item_id = result.get("id", "")
    atualizar_conteudo(conteudo_id, {
        "status": "publicado_webflow",
        "webflow_item_id": item_id,
    })

    print()
    print("=" * 60)
    print("BLOG CRIADO COM SUCESSO")
    print(f"  Tema:       {tema}")
    print(f"  Título:     {titulo}")
    print(f"  Nota final: {nota}/10")
    print(f"  Capa:       {caminho_capa or 'não gerada'}")
    print(f"  Webflow ID: {item_id}")
    print(f"  DB ID:      {conteudo_id}")
    print("=" * 60)
    print("Rascunho disponível no painel Webflow para publicação.")


if __name__ == "__main__":
    tema_arg = " ".join(sys.argv[1:]).strip() or None
    main(tema_arg)
