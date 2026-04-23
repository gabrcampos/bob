import os
import json
import re
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser

import requests
from google import genai
from google.genai import types

CONTEXTOS_DIR  = Path("config/contextos")
HISTORICO_DIR  = Path("config/historico")

ESTRUTURA_CARROSSEL = """
Slide 1 — Gancho/Capa: O TÍTULO deve ser uma frase de no máximo 6 palavras — gancho forte, provocador, que gere curiosidade. O TEXTO deve ser uma frase curta e impactante (máx 15 palavras) que amplifique o gancho do título. SEM dados, SEM estatísticas, SEM fontes — apenas conceito e impacto.
Slide 2 — O Problema: liste 3 a 5 sintomas/problemas diretos usando EXATAMENTE o formato de bullet - (um por linha, iniciando com o caractere - seguido de espaço e o texto). Cada item conceitual, sem dados ou percentuais, máx 12 palavras.
Slide 3 — Causa Raiz: por que o problema persiste? Título curto + texto conceitual (1-2 frases, SEM dados, SEM cases, texto corrido simples).
Slide 4 — Impactos: liste 3 a 5 consequências operacionais/financeiras usando EXATAMENTE o formato de bullet ✗ (um por linha, iniciando com o caractere ✗ seguido de espaço e o texto). Itens conceituais, sem números ou percentuais, máx 12 palavras cada.
Slide 5 — O que NÃO resolve: abordagens paliativas comuns e por que continuam falhando. Texto conceitual, sem dados.
Slide 6 — Insight central: o princípio ou mudança de perspectiva que faz a diferença. Título assertivo + texto conceitual (1-2 frases). prompt_imagem deve ser "" (este slide não usa imagem).
Slide 7 — O que está por trás: categoria de solução e princípio que explica o resultado — sem receita, sem produto específico. Texto conceitual.
Slide 8 — Quem resolve vs. quem não resolve: slide split com dois painéis lado a lado. Painel ESQUERDO = lado bom (azul), painel DIREITO = lado ruim (escuro). Título assertivo (máx 6 palavras) que resume o contraste. O campo "texto" deve ter EXATAMENTE este formato: "[descrição de quem resolve — 1 frase, estado positivo]\n---\n[descrição de quem não resolve — 1 frase, estado problemático]". SEM dados. O campo "prompt_imagem" deve ter EXATAMENTE este formato: "[cena do painel esquerdo — ambiente moderno, organizado e produtivo]\n---\n[cena do painel direito — ambiente desorganizado, caótico ou degradado]". As duas cenas devem ser visivelmente diferentes entre si.
Slide 9 — O que considerar: fatores-chave para avaliar qual caminho faz sentido para o contexto de cada empresa. Texto conceitual.
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

AVISO_SEM_GROUNDING = """

⚠️ INSTRUÇÃO PRIORITÁRIA — MODO SEM VERIFICAÇÃO DE DADOS:
O Google Search não está disponível nesta geração. Portanto, IGNORE qualquer instrução anterior que peça dados, estatísticas, percentuais, anos, fontes ou casos reais com números.
Todo o conteúdo — incluindo o slide 1, a introdução e os parágrafos de blog — deve ser 100% conceitual: raciocínio estratégico, frameworks, perspectivas e argumentos originais, sem nenhum dado numérico ou referência a pesquisa específica.
Esta instrução tem prioridade absoluta sobre qualquer regra anterior no prompt."""


SYSTEM_PROMPT = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Você produz conteúdo editorial para a {empresa}.
O público-alvo são {publico_alvo}.
Todo o conteúdo deve ser em português brasileiro.
{contexto_compilado}
{historico_recente}
{padrao_qualidade}
{dado_verificado}
Gere 3 peças de conteúdo sobre o tema "{tema}":

1. CARROSSEL (9 slides obrigatórios):
{estrutura}
REGRA CENTRAL: Apenas o slide 1 pode conter dados, estatísticas ou referências a casos reais — com fonte obrigatória. Todos os demais slides (2 a 9) devem ser 100% conceituais: sem números, sem percentuais, sem nomes de empresas como case, sem fontes. O valor está no raciocínio, não nos dados.

Cada slide deve ter:
- "titulo": título curto e impactante (máx 8 palavras; slide 1 deve ter máx 6 palavras — gancho direto)
- "texto": corpo do slide (máx 2 frases curtas e diretas, sem bullets, sem rodeios — direto ao argumento)
- "prompt_imagem": descrição objetiva em inglês do que deve aparecer na imagem de fundo deste slide (1-2 frases). EXCEÇÕES DE FORMATO: slide 6 deve ter prompt_imagem="" (sem imagem); slide 8 deve ter EXATAMENTE dois prompts separados por "\n---\n" (um para cada painel). REGRAS OBRIGATÓRIAS para todos os prompts: (a) cada slide deve ter uma cena visualmente distinta dos demais — varie ambientes, perspectivas, elementos e iluminação; (b) seja específico e concreto: descreva uma cena real com pessoas, objetos ou ambientes físicos — nunca conceitos abstratos (ex: "aerial view of a busy port logistics yard at dusk, stacked shipping containers", não "abstract technology concept"); (c) ABSOLUTAMENTE PROIBIDO: qualquer referência a texto, letras, palavras, números, letreiros, sinalização, telas com escrita, quadros brancos, apresentações, setas com labels, diagramas com texto, gráficos com labels ou qualquer elemento tipográfico — a cena deve ter APENAS elementos visuais puros sem escrita; (d) evite descrever setas, diagramas ou infográficos que naturalmente contenham texto; (e) prefira cenas do mundo físico: pessoas em ação, ambientes corporativos/industriais, paisagens urbanas, equipamentos, reuniões sem foco em telas.

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

4. LEGENDA (para acompanhar o carrossel na publicação):
- 2 a 4 frases que complementam o carrossel sem repetir o que já está nos slides
- Começa com um gancho ou pergunta que convida o leitor a ver o carrossel
- Tom direto, sem emojis corporativos, máx 220 palavras

Responda SOMENTE com JSON válido, sem markdown, sem texto fora do JSON.
Estrutura exata:
{{
  "carrossel": [
    {{"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."}},
    ... (9 slides)
  ],
  "post_linkedin": "...",
  "narracao_video": "...",
  "legenda": "..."
}}"""

PROMPT_BLOG = """Você é um redator especialista em SEO e tecnologia B2B corporativa.
Escreva um artigo de blog aprofundado para a {empresa} sobre o tema "{tema}".
Público-alvo: {publico_alvo}.
Idioma: português brasileiro.
{contexto_compilado}
{historico_recente}
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


# ─────────────────────────────────────────────
# Histórico de conteúdos (evitar repetição de dados)
# ─────────────────────────────────────────────

def _caminho_historico(empresa_id: str) -> Path:
    return HISTORICO_DIR / f"{empresa_id}.json"


def salvar_historico(empresa_id: str, tema: str, carrossel: list[dict]):
    """Persiste um resumo do carrossel gerado para evitar repetição de dados."""
    HISTORICO_DIR.mkdir(parents=True, exist_ok=True)
    path = _caminho_historico(empresa_id)
    historico = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entrada = {
        "data": datetime.now().strftime("%Y-%m-%d"),
        "tema": tema,
        "dados_usados": [
            f"[Slide {s.get('slide', i+1)}] {s.get('titulo', '')} — {s.get('texto', '')}"
            for i, s in enumerate(carrossel)
        ],
    }
    historico.append(entrada)
    # Mantém apenas as últimas 20 entradas
    path.write_text(json.dumps(historico[-20:], ensure_ascii=False, indent=2), encoding="utf-8")


def _bloco_historico(empresa_id: str, limit: int = 5) -> str:
    """Retorna bloco de prompt com histórico recente de conteúdos."""
    path = _caminho_historico(empresa_id)
    if not path.exists():
        return ""
    historico = json.loads(path.read_text(encoding="utf-8"))
    recentes = historico[-limit:]
    if not recentes:
        return ""
    linhas = [
        "\nHISTÓRICO DE CONTEÚDOS ANTERIORES (não repita os mesmos dados, estatísticas, cases ou ângulos):"
    ]
    for entrada in recentes:
        linhas.append(f"\nTema: \"{entrada['tema']}\" ({entrada.get('data', '')})")
        for dado in entrada.get("dados_usados", []):
            linhas.append(f"  • {dado}")
    linhas.append("\nUse perspectivas, cases e dados distintos dos listados acima.\n")
    return "\n".join(linhas)


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


_VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')


def _sanitize_json_strings(raw: str) -> str:
    """Corrige problemas comuns em JSON gerado por LLM:
    - Caracteres de controle literais (newline, tab, CR) dentro de strings
    - Backslashes com sequências de escape inválidas (ex: \\s, \\p)
    """
    result = []
    in_string = False
    escape_next = False
    for char in raw:
        if escape_next:
            if char not in _VALID_JSON_ESCAPES:
                result.append("\\")  # duplica a barra para tornar válido
            result.append(char)
            escape_next = False
        elif char == "\\" and in_string:
            result.append(char)
            escape_next = True
        elif char == '"':
            in_string = not in_string
            result.append(char)
        elif in_string and char == "\n":
            result.append("\\n")
        elif in_string and char == "\r":
            result.append("\\r")
        elif in_string and char == "\t":
            result.append("\\t")
        else:
            result.append(char)
    return "".join(result)


def _get_response_text(response) -> str | None:
    """Extrai texto de uma resposta Gemini de forma robusta.
    O response.text pode retornar None com grounding mesmo quando há conteúdo em parts."""
    if response.text:
        return response.text
    try:
        for part in (response.candidates[0].content.parts or []):
            if hasattr(part, "text") and part.text:
                return part.text
    except Exception:
        pass
    return None


def _strip_markdown_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
    return raw


def _fix_single_quoted_keys(raw: str) -> str:
    """Converte chaves JSON com aspas simples para aspas duplas: 'key': -> "key":"""
    return re.sub(r"([{\[,]\s*)'([^']*)'(\s*:)", r'\1"\2"\3', raw)


def _extract_json_array(raw: str) -> str | None:
    raw = _strip_markdown_fence(raw)
    start = raw.find("[")
    if start == -1:
        return None
    depth = 0
    for idx, char in enumerate(raw[start:], start=start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return raw[start:idx + 1]
    return None


def _parse_json(raw: str) -> dict | list:
    raw = _strip_markdown_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(_sanitize_json_strings(raw))
        except json.JSONDecodeError:
            try:
                return json.loads(_sanitize_json_strings(_fix_single_quoted_keys(raw)))
            except json.JSONDecodeError:
                if raw.strip().startswith("[") and raw.strip().endswith("]"):
                    items = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
                    if items:
                        return [bytes(item, "utf-8").decode("unicode_escape") for item in items]
                raise


PROMPT_BUSCA_DADO_CAPA = """Use o Google Search agora para encontrar UMA notícia, estudo ou relatório publicado nos últimos 12 meses que contenha um dado ou estatística numérica concreta sobre "{tema}".

REGRAS CRÍTICAS:
- Copie o dado EXATAMENTE como aparece na fonte — sem parafrasear, sem completar, sem extrapolar
- O dado deve ter um número específico (percentual, valor ou quantidade)
- A fonte deve ser real e verificável (nome da publicação ou organização)
- Se não encontrar nada verificável e concreto, retorne {{"dado": null}}

Responda SOMENTE com JSON:
{{"dado": "texto exato do dado/estatística como aparece na fonte", "fonte": "nome da publicação ou organização", "ano": "2024 ou 2025"}}"""


def _buscar_dado_capa(tema: str, empresa_id: str, url_site: str) -> str | None:
    """Etapa 1: busca isolada via Google Search de um dado real para o slide capa.
    Retorna 'dado (Fonte, Ano)' ou None se não encontrar nada verificável."""
    client = _get_client()
    prompt = PROMPT_BUSCA_DADO_CAPA.format(tema=tema)
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt, config=config
        )
        _text = _get_response_text(response)
        if not _text:
            response = client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
            _text = _get_response_text(response)
        result = _parse_json(_text)
        dado = result.get("dado")
        if dado:
            fonte = result.get("fonte", "")
            ano = result.get("ano", "")
            suffix = f" ({fonte}, {ano})" if fonte else ""
            dado_formatado = f"{dado}{suffix}"
            print(f"[LLM] Dado capa verificado: {dado_formatado[:100]}")
            return dado_formatado
    except Exception as e:
        print(f"[LLM] Busca de dado capa falhou ({e}), prosseguindo sem dado verificado.")
    return None


def _bloco_dado_verificado(dado_capa: str | None) -> str:
    if not dado_capa:
        return ""
    return (
        f'\nDADO VERIFICADO PARA O SLIDE 1 — Copie o texto abaixo LITERALMENTE no campo '
        f'"texto" do slide 1, sem alterar uma única palavra:\n"{dado_capa}"\n'
    )


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
        historico_recente=_bloco_historico(empresa_id),
        padrao_qualidade=PADRAO_QUALIDADE,
        dado_verificado="",
    )

    print(f"[LLM] Gerando conteúdo para: '{tema}' ({empresa}) com Google Search Grounding...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
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
                    contents=prompt + AVISO_SEM_GROUNDING,
                )

            _text = _get_response_text(response)
            if not _text:
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
                )
                _text = _get_response_text(response)

            conteudo = _parse_json(_text)
            conteudo["empresa"] = empresa
            conteudo["tema"] = tema
            conteudo["publico_alvo"] = publico_alvo
            salvar_historico(empresa_id, tema, conteudo.get("carrossel", []))
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
{historico_recente}
{padrao_qualidade}

Escreva um post LinkedIn sobre "{tema}":
- Mín 4 parágrafos separados por linha em branco, máx 3.000 caracteres
- Parágrafo 1: COMEÇE COM UMA PERGUNTA OU GANCHO CONVERSACIONAL que "aqueça" o tema acadêmico, tornando-o mais acessível e menos formal (exemplo: transforme "Eficiência Operacional em GR/RI: Como a IA Libera Equipes para Foco Estratégico" em "Sua equipe de RelGov foi contratada para articular ou para preencher planilhas? Como a automação devolve o tempo estratégico do seu departamento."). Mantenha a sobriedade corporativa, sem exagero.
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
{historico_recente}
{padrao_qualidade}

Escreva uma narração de vídeo de 30-45 segundos (~80-100 palavras) sobre "{tema}":
- Apenas o texto para leitura em voz alta, sem indicações de cena, corte ou visual
- Começa com um gancho forte
- Texto contínuo e fluido

Responda APENAS com o texto da narração, sem JSON, sem markdown."""


PROMPT_SUGESTAO_TEMAS = """Use o Google Search agora para buscar tendências, conceitos e estudos recentes relevantes para {publico_alvo} da empresa {empresa}.

{contexto_compilado}

{historico_recente}

Com base nos resultados encontrados, escreva um parágrafo de análise sobre o que está em debate no setor. Depois liste exatamente 10 temas REAIS, ESPECÍFICOS E SÓBRIOS para posts de carrossel no LinkedIn.

CRITÉRIOS OBRIGATÓRIOS PARA CADA TEMA:
- Título CORPORATIVO e TÉCNICO, nunca metáforas hiperbólicas (evitar: "tsunami", "xeque-mate", "brutal", "engolidos", "apocalipse")
- Ancorado em um case real, tendência verificável ou pressão regulatória atual
- Foco em PAIN POINT concreto ou OPORTUNIDADE de ROI mensurável
- Tom: data-driven, pragmático, de automação/eficiência ou conformidade
- Relevância: conecta com a dor diária e urgente do público-alvo, NÃO apenas nichos acadêmicos
- Evitar promessas futuras impossíveis ou contradições (ex: "prever o imprevisível")
- Evitar temas muito abrangentes ou genéricos (ex: "soberania digital")

ESTRUTURA RECOMENDADA DE TÍTULOS:
- Como [processo tedioso] se torna [operação eficiente] via IA/automação
- O impacto de [tendência/lei] em [setor/operação do público]
- Dados abertos, filtros inteligentes: a transformação que [setor] precisa fazer
- De [estado antes] para [estado depois]: automação em [processo]

Retorne no formato:
ANÁLISE: <parágrafo>
TEMAS: ["tema 1", "tema 2", "tema 3", "tema 4", "tema 5", "tema 6", "tema 7", "tema 8", "tema 9", "tema 10"]"""


def _gerar_texto_simples(prompt: str) -> str:
    """Chama Gemini e retorna texto puro, com fallback sem grounding."""
    client = _get_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt, config=config
        )
    except Exception as e:
        print(f"[LLM] Grounding indisponível ({e}), gerando sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
        )
    _text = _get_response_text(response)
    if not _text:
        print("[LLM] response.text vazio com grounding, retentando sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
        )
        _text = _get_response_text(response)
    return _text.strip()


def sugerir_temas(
    empresa: str,
    empresa_id: str,
    publico_alvo: str,
    url_site: str = "",
) -> list[str]:
    """Usa Gemini com Google Search para sugerir 10 temas relevantes para a empresa."""
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)
    bloco_hist = _bloco_historico(empresa_id, limit=10)

    prompt = PROMPT_SUGESTAO_TEMAS.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        contexto_compilado=bloco_ctx,
        historico_recente=bloco_hist,
    )

    print(f"[LLM] Sugerindo temas para '{empresa}'...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt, config=config
        )
    except Exception as e:
        print(f"[LLM] Grounding indisponível ({e}), sugerindo sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
        )

    _text = _get_response_text(response)
    if not _text:
        print("[LLM] response.text vazio com grounding, retentando sem busca...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
        )
        _text = _get_response_text(response)

    raw = _text.strip()
    
    # Corrige encoding potencial de double UTF-8 (Ã¡ -> á)
    try:
        raw = raw.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    
    # Remove caracteres de controle inválidos que podem aparecer de Google Search
    raw = ''.join(ch if ord(ch) >= 32 or ch in '\n\t\r' else '' for ch in raw)
    
    raw_array = _extract_json_array(raw)
    if raw_array is not None:
        raw = raw_array
    else:
        raw = _strip_markdown_fence(raw)

    try:
        temas = _parse_json(raw)
    except json.JSONDecodeError as e:
        # Fallback: extrai todas as strings entre aspas como temas
        import re
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        if items:
            temas = []
            for item in items:
                # Corrige encoding de cada item também
                try:
                    item = item.encode('latin-1').decode('utf-8')
                except:
                    pass
                temas.append(item)
        else:
            # Último recurso: quebra por vírgulas ou line breaks e limpa
            temas = [linha.strip().strip('"\'[],-').strip() for linha in raw.split('\n') if linha.strip() and len(linha.strip()) > 5]
            if not temas:
                raise ValueError(f"Resposta inesperada do modelo ao sugerir temas: {e}") from e

    if not isinstance(temas, list):
        raise ValueError("Resposta inesperada do modelo ao sugerir temas.")

    return [str(t).strip() for t in temas if str(t).strip() and len(str(t).strip()) > 5][:10]


def gerar_legenda(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    slides: list[dict] = None,
) -> str:
    """Gera uma legenda curta para acompanhar o carrossel na publicação."""
    resumo_slides = ""
    if slides:
        titulos = [s.get("titulo", "") for s in slides if s.get("titulo")]
        resumo_slides = f"\nTítulos dos slides: {' | '.join(titulos[:6])}"

    prompt = f"""Você é um estrategista de conteúdo B2B.
Escreva uma legenda curta para acompanhar um carrossel sobre "{tema}" publicado pela empresa {empresa} para {publico_alvo}.
{resumo_slides}

A legenda deve:
- Ter 2 a 4 frases que complementam o carrossel sem repetir o que já está nos slides
- Começar com um gancho ou pergunta que convida o leitor a ver o carrossel
- Tom direto, sem emojis corporativos, máx 220 palavras
- Ser em português brasileiro

Responda APENAS com o texto da legenda, sem explicações."""
    return _gerar_texto_simples(prompt)


def gerar_linkedin(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
    slides: list[dict] = None,
) -> str:
    bloco_ctx = _bloco_contexto(empresa_id, url_site)
    
    # Se temos slides, cria um resumo para contextualizar o post
    resumo_slides = ""
    if slides:
        titulos = [s.get("titulo", "") for s in slides if s.get("titulo")]
        resumo_slides = f"\nResumo dos slides do carrossel:\n" + "\n".join(f"- {titulo}" for titulo in titulos[:5])  # primeiros 5 slides
    
    prompt = PROMPT_LINKEDIN_ISOLADO.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        contexto_compilado=bloco_ctx,
        historico_recente=_bloco_historico(empresa_id),
        padrao_qualidade=PADRAO_QUALIDADE,
    )
    
    # Adiciona o resumo dos slides ao prompt se disponível
    if resumo_slides:
        prompt = prompt.replace('"{tema}":', f'"{tema}":{resumo_slides}')
    
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
        historico_recente=_bloco_historico(empresa_id),
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
        historico_recente=_bloco_historico(empresa_id),
        padrao_qualidade=PADRAO_QUALIDADE,
    )

    print(f"[LLM] Gerando blog para: '{tema}' ({empresa}) com Google Search Grounding...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
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
            contents=prompt + AVISO_SEM_GROUNDING,
        )

    _text = _get_response_text(response)
    if not _text:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
        )
        _text = _get_response_text(response)

    return _text.strip()


# ─────────────────────────────────────────────
# Carrossel Tweet
# ─────────────────────────────────────────────

ESTRUTURA_CARROSSEL_TWEET = """
Slide 1 — Gancho/Capa: título impactante (máx 6 palavras) — gancho forte, provocador, que gere curiosidade. O TEXTO deve ser uma frase curta e impactante (máx 15 palavras) que amplifique o gancho. SEM dados, SEM estatísticas, SEM fontes. Máx 1 frase.
Slide 2 — O Problema: liste 3 a 5 sintomas/problemas diretos usando EXATAMENTE o formato - (um por linha, iniciando com - seguido de espaço e o texto). Cada item conceitual, sem dados ou percentuais, máx 12 palavras.
Slide 3 — Causa Raiz: por que o problema persiste? Título curto + texto conceitual (1-2 frases, SEM dados, SEM cases, texto corrido simples).
Slide 4 — Impactos: liste 3 a 5 consequências usando EXATAMENTE o formato ✗ (um por linha, iniciando com ✗ seguido de espaço e o texto). Cada item conceitual, sem dados ou percentuais, máx 12 palavras.
Slide 5 — O que NÃO resolve: abordagens paliativas comuns e por que continuam falhando. Texto conceitual, sem dados ou cases.
Slide 6 — A Virada: qual mudança de mentalidade ou abordagem muda o jogo. Título assertivo + texto conceitual (1-2 frases, SEM dados, SEM cases). prompt_imagem deve ser "" (este slide não usa imagem).
Slide 7 — O que funciona: princípios ou práticas que realmente resolvem. Texto conceitual, sem dados ou cases.
Slide 8 — O que considerar: fatores-chave para avaliar qual caminho faz sentido. Texto conceitual, sem dados ou cases.
Slide 9 — Conclusão/CTA: síntese do raciocínio em 1-2 frases que encerram o argumento. Texto conceitual.
"""

PROMPT_CARROSSEL_TWEET = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Você produz conteúdo editorial para a {empresa}.
O público-alvo são {publico_alvo}.
Todo o conteúdo deve ser em português brasileiro.
{contexto_compilado}
{historico_recente}
{dado_verificado}
Gere um Carrossel Tweet de 9 slides sobre o tema "{tema}":
{estrutura}

REGRA CENTRAL: Apenas o slide 1 pode conter dados, estatísticas ou referências a casos reais — e somente se o tema for baseado em notícia ou dado concreto, com fonte obrigatória. Todos os demais slides (2 a 9) devem ser 100% conceituais: sem números, sem percentuais, sem nomes de empresas como case, sem fontes. O valor está no raciocínio, não nos dados.

Cada slide deve ter:
- "titulo": título curto e impactante (máx 8 palavras; slide 1 máx 6 palavras)
- "texto": corpo conforme a instrução de cada slide — direto e objetivo, máx 2-3 frases curtas
- "prompt_imagem": descrição objetiva em inglês da cena de fundo (1-2 frases). REGRAS: (a) cenas físicas concretas, visualmente distintas entre slides; (b) PROIBIDO qualquer texto, letras, números ou elementos tipográficos; (c) vazio ("") no slide 6.

Gere também uma legenda para acompanhar o carrossel na publicação:
- 2 a 4 frases que complementam o carrossel sem repetir o que já está nos slides
- Começa com um gancho ou pergunta que convida o leitor a ver o carrossel
- Tom direto, sem emojis corporativos, máx 220 palavras

Responda SOMENTE com JSON válido, sem markdown, sem texto fora do JSON.
Estrutura exata:
{{
  "carrossel": [
    {{"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."}},
    ... (9 slides)
  ],
  "legenda": "..."
}}"""


def gerar_carrossel_tweet(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> dict:
    """Gera 9 slides + legenda para o Carrossel Tweet com prompt próprio (sem dados exceto slide 1)."""
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)

    prompt = PROMPT_CARROSSEL_TWEET.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        estrutura=ESTRUTURA_CARROSSEL_TWEET,
        contexto_compilado=bloco_ctx,
        historico_recente=_bloco_historico(empresa_id),
        dado_verificado="",
    )

    print(f"[LLM] Gerando Carrossel Tweet para: '{tema}' ({empresa})...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    for tentativa in range(3):
        try:
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt, config=config
                )
            except Exception as e:
                print(f"[LLM] Grounding indisponível ({e}), gerando sem busca...")
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
                )
            _text = _get_response_text(response)
            if not _text:
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
                )
                _text = _get_response_text(response)
            conteudo = _parse_json(_text)
            slides = conteudo.get("carrossel", [])
            if slides:
                return {"slides": slides, "legenda": conteudo.get("legenda", "")}
            raise ValueError("JSON retornado sem campo 'carrossel'")
        except Exception as e:
            print(f"[LLM] Tentativa {tentativa + 1}/3 falhou ({e}). Retentando...")

    raise RuntimeError("Falha ao gerar Carrossel Tweet após 3 tentativas.")


# ─────────────────────────────────────────────
# Carrossel Misto DD
# ─────────────────────────────────────────────

ESTRUTURA_CARROSSEL_MISTO_DD = """
Slide 1 — Capa/Gancho: APENAS título (máx 18 palavras, gancho imediato e impactante). NÃO pule este slide! O campo "texto" deve receber EXATAMENTE uma string vazia "". prompt_imagem: cena física de negócios/logística sem texto.
Slide 2 — Contexto: apresente o problema de forma conceitual. Título curto + texto (1-2 frases diretas, máx 25 palavras, SEM dados ou números, foco no conceito e na realidade do problema). prompt_imagem: cena contextual relacionada ao problema.
Slide 3 — Causa Raiz: por que o problema persiste. Título curto + texto (1-2 frases diretas, máx 25 palavras, SEM BULLET POINTS, sem listas, texto corrido simples, foco na ideia central sem dados). prompt_imagem: cena que ilustre a causa.
Slide 4 — Impactos: liste 3 a 5 consequências operacionais conceituais usando EXATAMENTE o formato ✗ (um por linha, iniciando com ✗ seguido de espaço e o texto, máx 10 palavras por item). SEM números, percentuais ou fontes — apenas os conceitos e impactos. prompt_imagem: cena de ambiente impactado negativamente.
Slide 5 — A Virada: destaque um insight que muda a perspectiva. Título assertivo + texto (1-2 frases diretas, máx 30 palavras, SEM BULLET POINTS, sem listas, texto corrido simples, SEM dados, percentuais ou fontes — foco na ideia transformadora). Sem imagem (prompt_imagem vazio).
Slide 6 — O que Funciona: liste 3 a 5 práticas ou abordagens usando EXATAMENTE o formato ✓ (um por linha, iniciando com ✓ seguido de espaço e o texto, máx 10 palavras por item). SEM números ou fontes — apenas as práticas e conceitos. prompt_imagem: cena positiva/produtiva.
Slide 7 — Antes vs Depois: o campo "texto" deve ter EXATAMENTE este formato: "ANTES: [descrição do estado problemático em 1 frase]\n---\nDEPOIS: [descrição do estado melhorado em 1 frase]". SEM dados ou fontes — foque na transformação conceitual. O título deve ser o tema central da comparação (máx 6 palavras). prompt_imagem: cena de transformação ou ambiente melhorado.
Slide 8 — CTA: título fixo "SE VOCÊ QUER UMA OPERAÇÃO 5 ESTRELAS, TESTE AGORA O DELIVERYDASH." + texto (descrição gerada, 1-2 frases, máx 25 palavras). prompt_imagem: um prato delicioso de restaurante profissional.
"""

PROMPT_MISTO_DD = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Você produz conteúdo editorial para a {empresa}.
O público-alvo são {publico_alvo}.
Todo o conteúdo deve ser em português brasileiro.
{contexto_compilado}
{historico_recente}
{padrao_qualidade}

Gere um Carrossel Misto DD de 8 slides sobre o tema "{tema}":
{estrutura}

Cada slide deve ter:
- "titulo": título curto e impactante (máx 8 palavras; slide 1 deve ter máx 18 palavras; slides 5 e 8 devem ter máx 6 palavras)
- "texto": corpo do slide conforme a instrução. No Slide 1 OBRIGATORIAMENTE deve ser "". Nos demais, seja direto e objetivo, máx 2-3 frases curtas; evite introduções, conectivos desnecessários e contexto redundante; NÃO use dados numéricos, percentuais, estatísticas ou citações de fontes — foque apenas nos conceitos e ideias
- "prompt_imagem": descrição objetiva em inglês do que deve aparecer na imagem de fundo (1-2 frases). REGRAS OBRIGATÓRIAS: (a) cenas visualmente distintas entre slides; (b) cenas físicas concretas com pessoas, objetos ou ambientes reais; (c) ABSOLUTAMENTE PROIBIDO: qualquer texto, letras, números, letreiros, telas com escrita ou elementos tipográficos; (d) deixe vazio ("") no slide 5.

Gere também uma legenda para acompanhar o carrossel na publicação:
- 2 a 4 frases que complementam o carrossel sem repetir o que já está nos slides
- Começa com um gancho ou pergunta que convida o leitor a ver o carrossel
- Tom direto, sem emojis corporativos, máx 220 palavras

Responda SOMENTE com JSON válido, sem markdown, sem texto fora do JSON.
Estrutura exata:
{{
  "slides": [
    {{"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."}},
    ... (8 slides)
  ],
  "legenda": "..."
}}"""


def gerar_carrossel_misto_dd(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> dict:
    """Gera 8 slides + legenda para o Carrossel Misto DD."""
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)

    prompt = PROMPT_MISTO_DD.format(
        empresa=empresa,
        publico_alvo=publico_alvo,
        tema=tema,
        estrutura=ESTRUTURA_CARROSSEL_MISTO_DD,
        contexto_compilado=bloco_ctx,
        historico_recente=_bloco_historico(empresa_id),
        padrao_qualidade=PADRAO_QUALIDADE,
    )

    print(f"[LLM] Gerando Carrossel Misto DD para: '{tema}' ({empresa})...")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_budget=0),
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
                    contents=prompt + AVISO_SEM_GROUNDING,
                )
            _text = _get_response_text(response)
            if not _text:
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING
                )
                _text = _get_response_text(response)
            conteudo = _parse_json(_text)
            slides = conteudo.get("slides", [])
            if slides:
                return {"slides": slides, "legenda": conteudo.get("legenda", "")}
            raise ValueError("JSON retornado sem campo 'slides'")
        except Exception as e:
            print(f"[LLM] Tentativa {tentativa + 1}/3 falhou ({e}). Retentando...")

    raise RuntimeError("Falha ao gerar Carrossel Misto DD após 3 tentativas.")


# ─────────────────────────────────────────────
# Carrossel OldSchool
# ─────────────────────────────────────────────

ESTRUTURA_CARROSSEL_OLDSCHOOL = """
Slide 1 — Capa: APENAS texto (máx 14 palavras, gancho imediato). prompt_imagem: cena rotineira de decisão de governo/poder público sem texto.
Slide 2 — Problema: Texto com no máximo 25 palavras. prompt_imagem: cena contextual em escritório de governo, plenário ou judiciário.
Slide 3 — Complicação: Texto com no máximo 25 palavras. prompt_imagem: OBRIGATÓRIO incluir na descrição que a parte DIREITA da imagem deve ser mais escura/limpa para receber texto. Cena no legislativo/executivo.
Slide 4 — Impacto: Texto com no máximo 25 palavras. prompt_imagem: OBRIGATÓRIO incluir na descrição que a parte SUPERIOR ESQUERDA deve ser mais escura/limpa para receber texto.
Slide 5 — Agravante: Texto com no máximo 25 palavras. prompt_imagem: cena contextual de rotina governamental.
Slide 6 — Consequência: Texto com no máximo 25 palavras. prompt_imagem: OBRIGATÓRIO incluir na descrição que a parte SUPERIOR ESQUERDA deve ser mais escura/limpa.
Slide 7 — Transição: Texto com no máximo 25 palavras. prompt_imagem: cena contextual de rotina de relações governamentais.
Slide 8 — Solução: Explicação super objetiva (máx 25 palavras) de como a empresa resolve o problema (ex: "Na [Nome], o [Produto] cruza os dados..."). prompt_imagem: cena de análise de dados no contexto de governo/legislativo.
Slide 9 — CTA: Texto CTA (ex: "Leve dados para sua próxima reunião. Conheça a [Nome]."). OBRIGATÓRIO incluir um campo "texto_botao" (padrão: "CADASTRE-SE AGORA"). prompt_imagem: cena de escritório governamental conclusiva.
"""

PROMPT_OLDSCHOOL = """Você é um estrategista de conteúdo B2B especializado em tecnologia corporativa.
Você produz conteúdo editorial para a {empresa}.
O público-alvo são {publico_alvo}.
Todo o conteúdo deve ser em português brasileiro.
{contexto_compilado}
{historico_recente}
{padrao_qualidade}

Gere um Carrossel OldSchool de 9 slides sobre o tema "{tema}":
{estrutura}

Cada slide deve ter:
- "titulo": título muito curto (2-3 palavras) apenas para identificação interna.
- "texto": o texto principal do slide conforme as regras da estrutura. NO MÁXIMO 25 PALAVRAS (Slide 1: máx 14 palavras).
- "texto_botao": apenas para o slide 9 (padrão: "CADASTRE-SE AGORA"). Nos demais slides, omita este campo ou deixe vazio.
- "prompt_imagem": descrição objetiva em inglês da cena de fundo (1-2 frases). REGRAS DE IMAGEM: OBRIGATÓRIO focar em cenas rotineiras de pessoas que tomam decisões de governo (escritórios, plenários, tribunais, gabinetes legislativos) para gerar forte identificação. PROIBIDO usar texto, letras ou números na imagem.

Gere também uma legenda:
- 2 a 4 frases complementares ao carrossel.
- Tom direto, máx 220 palavras.

Responda SOMENTE com JSON válido, sem markdown, sem texto fora do JSON.
Estrutura exata:
{{
  "slides": [
    {{"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."}},
    ... (9 slides, o slide 9 deve conter "texto_botao")
  ],
  "legenda": "..."
}}"""

def gerar_carrossel_oldschool(
    tema: str,
    empresa: str = "Tecnosolve",
    empresa_id: str = "tecnosolve",
    publico_alvo: str = "CIOs e CTOs do varejo brasileiro",
    url_site: str = "",
) -> dict:
    client = _get_client()
    bloco_ctx = _bloco_contexto(empresa_id, url_site)
    prompt = PROMPT_OLDSCHOOL.format(
        empresa=empresa, publico_alvo=publico_alvo, tema=tema,
        estrutura=ESTRUTURA_CARROSSEL_OLDSCHOOL, contexto_compilado=bloco_ctx,
        historico_recente=_bloco_historico(empresa_id), padrao_qualidade=PADRAO_QUALIDADE,
    )
    print(f"[LLM] Gerando Carrossel OldSchool para: '{tema}' ({empresa})...")
    config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], thinking_config=types.ThinkingConfig(thinking_budget=0))
    for tentativa in range(3):
        try:
            try: response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=config)
            except Exception: response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING)
            _text = _get_response_text(response)
            if not _text: response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt + AVISO_SEM_GROUNDING); _text = _get_response_text(response)
            conteudo = _parse_json(_text)
            slides = conteudo.get("slides", [])
            if slides: return {"slides": slides, "legenda": conteudo.get("legenda", "")}
            raise ValueError("JSON sem 'slides'")
        except Exception as e: print(f"[LLM] Tentativa {tentativa + 1}/3 falhou ({e}). Retentando...")
    raise RuntimeError("Falha ao gerar Carrossel OldSchool após 3 tentativas.")
