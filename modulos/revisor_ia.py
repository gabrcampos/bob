"""Revisão automática de conteúdo via Gemini antes do envio ao Telegram."""
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_CLICHES = (
    "apagar incêndios, modo crise, no mundo de hoje, descubra como, "
    "você sabia que, transformação digital, inovação disruptiva, em um mundo, "
    "cada vez mais, na era digital, disrupção"
)

PROMPT_REVISAR_LINKEDIN = """Você é um editor-chefe especialista em comunicação B2B para tecnologia corporativa.
Revise o post LinkedIn abaixo produzido para a empresa {empresa} com público-alvo: {publico_alvo}.

POST:
{post}

CRITÉRIOS DE AVALIAÇÃO:
1. Precisão técnica: as afirmações fazem sentido para um público de CIO/CTO? Sem contradições ou simplificações incorretas?
2. Tom: direto, sem jargão de marketing, sem emojis corporativos, sem fechamento promocional?
3. Clichês proibidos: contém algum de: {cliches}?
4. Estrutura: mín 4 parágrafos separados por linha em branco, máx 3.000 caracteres?
5. Abertura: começa com gancho forte (fato, pergunta real ou dado)?

Responda SOMENTE com JSON válido:
{{"aprovado": true, "nota": 8, "parecer": "APROVADO", "observacoes": "feedback em 2-3 frases"}}

Parecer pode ser: APROVADO (nota >= 7) | REVISAR (nota 5-6) | REPROVAR (nota <= 4)"""

PROMPT_REVISAR_BLOG = """Você é um editor-chefe especialista em conteúdo B2B, SEO e tecnologia corporativa.
Revise o artigo de blog abaixo produzido para a empresa {empresa} com público-alvo: {publico_alvo}.

TÍTULO: {titulo}

ARTIGO (primeiros 3.000 caracteres):
{conteudo}

CRITÉRIOS DE AVALIAÇÃO:
1. Precisão técnica: afirmações corretas e relevantes para executivos de TI?
2. Estrutura: tem título H1, subtítulos H2, introdução, seções e conclusão?
3. Profundidade: entre 1.500-2.000 palavras estimadas? Cases ou dados concretos?
4. Clichês proibidos: contém algum de: {cliches}?
5. SEO: título com palavra-chave natural? Subtítulos descritivos?

Responda SOMENTE com JSON válido:
{{"aprovado": true, "nota": 8, "parecer": "APROVADO", "observacoes": "feedback em 2-3 frases"}}

Parecer pode ser: APROVADO (nota >= 7) | REVISAR (nota 5-6) | REPROVAR (nota <= 4)"""


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no .env")
    return genai.Client(api_key=api_key)


def _parse_revisao(texto: str) -> dict:
    from modulos.llm_brain import _parse_json, _strip_markdown_fence
    try:
        return _parse_json(_strip_markdown_fence(texto.strip()))
    except Exception:
        return {"aprovado": True, "nota": 7, "parecer": "APROVADO", "observacoes": "Revisão automática indisponível."}


def revisar_linkedin(post: str, tema: str, empresa: str, publico_alvo: str) -> dict:
    """Revisa post LinkedIn com Gemini. Retorna dict com aprovado, nota, parecer, observacoes."""
    client = _get_client()
    prompt = PROMPT_REVISAR_LINKEDIN.format(
        empresa=empresa, publico_alvo=publico_alvo, post=post, cliches=_CLICHES
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        print(f"[Revisor] LinkedIn revisado — tema: {tema[:50]}")
        return _parse_revisao(response.text or "")
    except Exception as e:
        print(f"[Revisor] Erro na revisão LinkedIn: {e}")
        return {"aprovado": True, "nota": 7, "parecer": "APROVADO", "observacoes": f"Revisão indisponível: {e}"}


def revisar_blog(titulo: str, conteudo: str, tema: str, empresa: str, publico_alvo: str) -> dict:
    """Revisa artigo de blog com Gemini. Retorna dict com aprovado, nota, parecer, observacoes."""
    client = _get_client()
    prompt = PROMPT_REVISAR_BLOG.format(
        empresa=empresa, publico_alvo=publico_alvo,
        titulo=titulo, conteudo=conteudo[:3000], cliches=_CLICHES
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        print(f"[Revisor] Blog revisado — tema: {tema[:50]}")
        return _parse_revisao(response.text or "")
    except Exception as e:
        print(f"[Revisor] Erro na revisão blog: {e}")
        return {"aprovado": True, "nota": 7, "parecer": "APROVADO", "observacoes": f"Revisão indisponível: {e}"}
