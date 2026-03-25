import os
import json
import re
from pathlib import Path
from html.parser import HTMLParser

import requests
from google import genai
from google.genai import types

CONTEXTOS_DIR = Path("config/contextos")

ESTRUTURA_CARROSSEL = """
Slide 1 — Gancho: frase de impacto que prende a atenção imediatamente. O TÍTULO deste slide deve ser uma frase curta de no máximo 6 palavras que funcione como gancho do conteúdo. O texto deve apresentar o dado ou estatística mais impactante sobre o tema (cite fonte, setor e ano).
Slide 2 — O Problema: descrição direta do problema em 1-2 frases, sem rodeios
Slide 3 — Causa Raiz: por que o problema persiste? A causa real, não o sintoma superficial
Slide 4 — Impactos: consequências operacionais e financeiras concretas (use números reais)
Slide 5 — O que NÃO resolve: abordagens paliativas comuns e por que continuam falhando
Slide 6 — Case real: empresa ou setor que resolveu isso, qual abordagem usou e qual resultado obteve (cite fonte)
Slide 7 — O que está por trás: categoria de solução e princípio que explica o resultado — sem receita, sem produto específico
Slide 8 — Outros exemplos: 1-2 casos adicionais com abordagens diferentes e resultados distintos, mostrando que não existe solução única
Slide 9 — O que considerar: fatores-chave para avaliar qual caminho faz sentido para o contexto de cada empresa
"""

PROMPT_COMPILAR_CONTEXTO = """Você é um estrategista de conteúdo B2B. Analise as informações brutas abaixo sobre a empresa "{empresa}" e compile um perfil editorial conciso que será usado para orientar a produção de conteúdo.

O perfil deve cobrir:
- O que a empresa faz e qual o seu diferencial
- Público-alvo e os problemas que esse público enfrenta
- Tom de voz e posicionamento
- Temas, argumentos e dados relevantes encontrados nos materiais
- O que NÃO deve aparecer no conteúdo (contradições, temas sensíveis, etc.)

Escreva em texto corrido, sem headers markdown, de forma densa e objetiva. Máximo 500 palavras.

--- INFORMAÇÕES BRUTAS ---
{raw}
"""

# Instruções comuns de qualidade para todos os prompts
PADRAO_QUALIDADE = """
PADRÃO DE QUALIDADE OBRIGATÓRIO:
- Ancore cada argumento em um case real (empresa, setor, país) com resultado mensurável e fonte — nunca use exemplos hipotéticos
- Use estatísticas com fonte e ano (Gartner, IDC, McKinsey, MIT, Harvard Business Review, etc.)
- Quando citar tecnologia, use a categoria conceitual ("plataformas de event streaming", "modelos de linguagem", "computação de borda"), não produtos específicos — a menos que o case real mencione explicitamente
- Mostre que existem múltiplos caminhos para o mesmo problema: cases diferentes com abordagens diferentes
- O público são executivos de TI (CIO/CTO) — eles não precisam de tutorial, precisam de evidência e raciocínio
- Tom jornalístico e consultivo: traga o fato, o resultado, e o princípio por trás. Não prescreva receita.
- PROIBIDO: CTAs, menções à empresa produtora, convites para contato, frases de venda, listas de ferramentas como solução
"""

SYSTEM_PROMPT = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Você produz conteúdo editorial para a {empresa}.
O público-alvo são {publico_alvo}.
Todo o conteúdo deve ser em português brasileiro.
{contexto_compilado}
{padrao_qualidade}

Gere 3 peças de conteúdo sobre o tema "{tema}":

1. CARROSSEL (9 slides obrigatórios):
{estrutura}
Cada slide deve ter:
- "titulo": título curto e impactante (máx 8 palavras; slide 1 deve ter máx 6 palavras — gancho direto)
- "texto": corpo do slide (máx 2 frases curtas e diretas, sem bullets, sem rodeios — vá direto ao dado ou argumento)
- "prompt_imagem": descrição objetiva em inglês do que deve aparecer na imagem de fundo deste slide (1-2 frases). REGRAS OBRIGATÓRIAS: (a) cada slide deve ter uma cena visualmente distinta dos demais — varie ambientes, perspectivas, elementos e iluminação; (b) seja específico e concreto: descreva uma cena real, não conceitos abstratos (ex: "aerial view of a busy port logistics yard at dusk, stacked shipping containers", não "abstract technology concept"); (c) PROIBIDO incluir qualquer texto, letras, palavras, números ou lettering — apenas elementos visuais puros.

2. POST LINKEDIN (mín 4 parágrafos, máx 3.000 caracteres):
- Parágrafo 1: fato ou case concreto que para o scroll — dado real ou resultado surpreendente
- Parágrafo 2: contexto e problema — por que isso acontece, qual é a causa raiz
- Parágrafo 3: desenvolvimento — apresente 1-2 cases reais com o raciocínio por trás do resultado
- Parágrafo 4: perspectiva — mostre abordagens diferentes para o mesmo problema ou o que separa quem resolve de quem não resolve
- Adicione mais parágrafos se necessário para desenvolver bem o raciocínio (até o limite de 3.000 caracteres)
- Separe os parágrafos com uma linha em branco
- Sem fechamento promocional, sem convite para contato, sem "fale comigo"
- Tom direto, sem hashtags em excesso, sem emojis corporativos
- Sem headers, texto fluido

3. NARRAÇÃO DE VÍDEO (30-45 segundos / ~80-100 palavras):
- Apenas o texto que será lido em voz alta, sem qualquer indicação de cena, corte ou visual
- Começa com um gancho forte
- Texto contínuo, fluido para leitura em voz alta

Responda SOMENTE com JSON válido, sem markdown, sem texto fora do JSON.
Estrutura exata:
{{
  "carrossel": [
    {{"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."}},
    ... (9 slides)
  ],
  "post_linkedin": "...",
  "narracao_video": "..."
}}"""

PROMPT_BLOG = """Você é um redator especialista em SEO e tecnologia B2B corporativa.
Escreva um artigo de blog aprofundado para a {empresa} sobre o tema "{tema}".
Público-alvo: {publico_alvo}.
Idioma: português brasileiro.
{contexto_compilado}
{padrao_qualidade}

ESTRUTURA DO ARTIGO:
- Título SEO otimizado (H1)
- Introdução: contexto atual com dado recente + o que o leitor vai aprender
- 4 a 6 seções com subtítulos (H2) cobrindo: causas, impactos, abordagens técnicas, casos de uso, recomendações práticas
- Conclusão com próximos passos concretos
- Entre 1.500 e 2.000 palavras
- Use markdown para formatação (# H1, ## H2, **negrito**)
- Cada seção deve ter ao menos um case real ou dado com fonte e ano
- Apresente múltiplos casos com abordagens distintas — o leitor decide o caminho
- Sem CTA, sem menção à empresa produtora, sem convite para contato
- Conteúdo jornalístico e consultivo: contexto → problema → cases reais → princípios → o que considerar

Responda APENAS com o texto do artigo em markdown, sem JSON, sem comentários."""


# ─────────────────────────────────────────────
# Extratores de texto bruto
# ─────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self):
        return " ".join(self._parts)


def _extrair_texto_site(url: str, max_chars: int = 4000) -> str:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        parser = _TextExtractor()
        parser.feed(resp.text)
        texto = re.sub(r"\s+", " ", parser.get_text()).strip()
        return texto[:max_chars]
    except Exception as e:
        print(f"[LLM] Aviso: não foi possível buscar o site '{url}': {e}")
        return ""


def _extrair_texto_pdf(path: Path) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
        partes = [page.extract_text() or "" for page in reader.pages]
        return " ".join(partes).strip()
    except Exception as e:
        print(f"[LLM] Aviso: erro ao ler PDF '{path.name}': {e}")
        return ""


def _extrair_texto_docx(path: Path) -> str:
    from docx import Document
    try:
        doc = Document(str(path))
        partes = [p.text for p in doc.paragraphs if p.text.strip()]
        return " ".join(partes).strip()
    except Exception as e:
        print(f"[LLM] Aviso: erro ao ler DOCX '{path.name}': {e}")
        return ""


def _coletar_raw(empresa_id: str, url_site: str = "", max_chars_arquivo: int = 3000) -> str:
    partes = []
    pasta = Path("config/arquivos") / empresa_id
    if pasta.exists():
        for arq in sorted(pasta.iterdir()):
            texto = ""
            if arq.suffix.lower() == ".pdf":
                texto = _extrair_texto_pdf(arq)
            elif arq.suffix.lower() in (".docx", ".doc"):
                texto = _extrair_texto_docx(arq)
            if texto:
                partes.append(f"[Arquivo: {arq.name}]\n{texto[:max_chars_arquivo]}")
    if url_site:
        texto_site = _extrair_texto_site(url_site)
        if texto_site:
            partes.append(f"[Site]\n{texto_site}")
    return "\n\n".join(partes)


# ─────────────────────────────────────────────
# Contexto compilado
# ─────────────────────────────────────────────

def caminho_contexto(empresa_id: str) -> Path:
    return CONTEXTOS_DIR / f"{empresa_id}.md"


def carregar_contexto_compilado(empresa_id: str) -> str:
    path = caminho_contexto(empresa_id)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def salvar_contexto_compilado(empresa_id: str, texto: str):
    CONTEXTOS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_contexto(empresa_id).write_text(texto, encoding="utf-8")


def processar_contexto(empresa_id: str, empresa_nome: str, url_site: str = "") -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no ambiente.")
    raw = _coletar_raw(empresa_id=empresa_id, url_site=url_site)
    if not raw:
        raise ValueError("Nenhuma fonte de contexto encontrada. Adicione o site ou arquivos da empresa.")
    client = genai.Client(api_key=api_key)
    prompt = PROMPT_COMPILAR_CONTEXTO.format(empresa=empresa_nome, raw=raw)
    print(f"[LLM] Compilando contexto para '{empresa_nome}'...")
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    texto_compilado = response.text.strip()
    salvar_contexto_compilado(empresa_id, texto_compilado)
    return texto_compilado


# ─────────────────────────────────────────────
# Geração de conteúdo principal
# ─────────────────────────────────────────────

def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no ambiente. Verifique o arquivo .env")
    return genai.Client(api_key=api_key)


def _bloco_contexto(empresa_id: str, url_site: str) -> str:
    ctx = carregar_contexto_compilado(empresa_id)
    if ctx:
        return f"\nPerfil editorial da empresa:\n{ctx}\n"
    raw = _coletar_raw(empresa_id=empresa_id, url_site=url_site)
    return f"\nContexto adicional sobre a empresa:\n{raw}\n" if raw else ""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
    return json.loads(raw)


def gerar_conteudo(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> dict:
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)

    prompt = SYSTEM_PROMPT.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        estrutura=ESTRUTURA_CARROSSEL,
        contexto_compilado=bloco_ctx,
        padrao_qualidade=PADRAO_QUALIDADE,
    )

    print(f"[LLM] Gerando conteúdo para: '{tema}' ({empresa}) com Google Search Grounding...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )

    for tentativa in range(3):
        try:
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=config,
                )
            except Exception as e:
                print(f"[LLM] Grounding indisponível ({e}), gerando sem busca...")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )

            conteudo = _parse_json(response.text)
            conteudo["empresa"] = empresa
            conteudo["tema"] = tema
            conteudo["publico_alvo"] = publico_alvo
            return conteudo
        except Exception as e:
            print(f"[LLM] Tentativa {tentativa + 1}/3 falhou ({e}). Retentando...")

    raise RuntimeError("Falha ao gerar conteúdo após 3 tentativas. Tente novamente.")


def gerar_slides_carrossel(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> list[dict]:
    """Gera apenas os slides do carrossel, descartando linkedin e narração."""
    conteudo = gerar_conteudo(tema, empresa, empresa_id, publico_alvo, url_site)
    return conteudo["carrossel"]


PROMPT_LINKEDIN_ISOLADO = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Produz conteúdo editorial para a {empresa}. Público-alvo: {publico_alvo}.
Todo conteúdo em português brasileiro.
{contexto_compilado}
{padrao_qualidade}

Escreva um post LinkedIn sobre "{tema}":
- Mín 4 parágrafos separados por linha em branco, máx 3.000 caracteres
- Parágrafo 1: fato ou case concreto que para o scroll — dado real ou resultado surpreendente
- Parágrafo 2: contexto e problema — por que isso acontece, qual é a causa raiz
- Parágrafo 3: desenvolvimento com 1-2 cases reais com o raciocínio por trás do resultado
- Parágrafo 4+: perspectiva — abordagens diferentes ou o que separa quem resolve de quem não resolve
- Sem fechamento promocional, sem "fale comigo", sem hashtags em excesso, sem emojis corporativos
- Sem headers, texto fluido

Responda APENAS com o texto do post, sem JSON, sem markdown extra."""


PROMPT_NARRACAO_ISOLADO = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Produz conteúdo editorial para a {empresa}. Público-alvo: {publico_alvo}.
Todo conteúdo em português brasileiro.
{contexto_compilado}
{padrao_qualidade}

Escreva uma narração de vídeo de 30-45 segundos (~80-100 palavras) sobre "{tema}":
- Apenas o texto para leitura em voz alta, sem indicações de cena, corte ou visual
- Começa com um gancho forte
- Texto contínuo e fluido

Responda APENAS com o texto da narração, sem JSON, sem markdown."""


def _gerar_texto_simples(prompt: str) -> str:
    """Chama Gemini e retorna texto puro, com fallback sem grounding."""
    client = _get_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt, config=config
        )
    except Exception as e:
        print(f"[LLM] Grounding indisponível ({e}), gerando sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
    return response.text.strip()


def gerar_linkedin(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> str:
    bloco_ctx = _bloco_contexto(empresa_id, url_site)
    prompt = PROMPT_LINKEDIN_ISOLADO.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        contexto_compilado=bloco_ctx,
        padrao_qualidade=PADRAO_QUALIDADE,
    )
    print(f"[LLM] Gerando LinkedIn para: '{tema}' ({empresa})")
    return _gerar_texto_simples(prompt)


def gerar_narracao(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> str:
    bloco_ctx = _bloco_contexto(empresa_id, url_site)
    prompt = PROMPT_NARRACAO_ISOLADO.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        contexto_compilado=bloco_ctx,
        padrao_qualidade=PADRAO_QUALIDADE,
    )
    print(f"[LLM] Gerando narração para: '{tema}' ({empresa})")
    return _gerar_texto_simples(prompt)


def gerar_blog(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> str:
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)

    prompt = PROMPT_BLOG.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        contexto_compilado=bloco_ctx,
        padrao_qualidade=PADRAO_QUALIDADE,
    )

    print(f"[LLM] Gerando blog para: '{tema}' ({empresa}) com Google Search Grounding...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
    except Exception as e:
        print(f"[LLM] Grounding indisponível ({e}), gerando sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

    return response.text.strip()
