# Spec: Carrossel Misto DD

## Visão geral

Novo tipo de conteúdo com 8 slides, cada um com layout visual distinto. "Misto" porque alterna entre fundos de cor primária sólida, cards brancos e imagem de fundo escurecida. "DD" = DeliveryDash (empresa-origem do design).

Dimensões padrão: **1080 × 1350 px** (mesmo das outras variantes).

---

## 1. Estrutura de slides e layouts

| Slide | Nome interno       | Fundo                        | Imagem IA          | Bullets |
|-------|--------------------|------------------------------|--------------------|---------|
| 1     | `capa`             | Cor primária + imagem direita| Metade direita     | —       |
| 2     | `card_imagem`      | Branco + imagem topo         | Full-width, ~400px | —       |
| 3     | `primaria_split`   | Cor primária + imagem direita| Faixa direita 42%  | —       |
| 4     | `dark_bullets`     | Imagem de fundo escurecida   | Fundo full         | ✗       |
| 5     | `card_destaque`    | Branco                       | —                  | —       |
| 6     | `primaria_bullets` | Cor primária + strip direita | Faixa direita 28%  | ✓       |
| 7     | `antes_depois`     | Esquerda dark / Direita prim | Tint na metade dir | —       |
| 8     | `cta_final`        | Cor primária                 | —                  | —       |

**Slides que precisam de imagem IA:** `{1, 2, 3, 4, 6, 7}`

---

## 2. Layout de cada slide

### Slide 1 — Capa
- Canvas inteiro: cor primária
- Imagem IA colada na metade direita (x = 540), com gradiente de fade lateral da esquerda (cor primária) cobrindo a junção
- Logo pequena (h=60px) no topo-esquerdo (PAD, PAD)
- Título (branco, bold) + texto (branco 90%) no lado esquerdo, verticalmente centrado considerando espaço para "Arraste"
- "Arraste para o lado" + ícone PNG, alinhado à direita, próximo ao rodapé (mesmo estilo do tweet)

### Slide 2 — Card Branco + Imagem Topo
- Fundo branco
- Imagem IA full-width sem bordas nos primeiros 400px (topo)
- Badge `"02"` cor primária (rounded rectangle) abaixo da imagem, alinhado à esquerda
- Título bold (cor escura) + texto cinza
- Logo pequena (h=48px) no canto inferior-direito

### Slide 3 — Cor Primária + Split Imagem Direita
- Fundo: cor primária
- Imagem IA ocupa 42% da largura direita; gradiente fade da cor primária cobre a borda esquerda da imagem
- Número decorativo grande (`"03"`, cor levemente mais escura que a primária) no canto superior-esquerdo, quase fora da tela
- Título (branco, bold) + linha separadora branca (80px) + texto (branco 90%) no lado esquerdo
- Logo pequena (h=50px) no rodapé-esquerdo

### Slide 4 — Dark Bullets (✗)
- Imagem IA como fundo full-slide, com overlay preto `rgba(0,0,0,200)`
- Barra vertical da cor primária (8px) na borda esquerda
- Título (branco, bold) no topo, centralizado verticalmente com os bullets
- Bullets ✗ (vermelho-claro `(255,100,100)`) ou • ponto (cor primária) para linhas de continuação

### Slide 5 — Card Branco com Destaque
- Fundo branco
- Barra horizontal da cor primária (12px) no topo do slide
- Número decorativo enorme (`"05"`, cor primária com alpha 20) no fundo, semi-transparente, deslocado para a direita
- Título (escuro, bold) + linha separadora (120px, cor primária) + texto cinza
- Logo pequena (h=48px) no canto inferior-direito

### Slide 6 — Cor Primária + Bullets (✓) + Strip Imagem
- Fundo: cor primária
- Imagem IA em faixa de 28% na borda direita, com gradiente fade cobrindo a borda esquerda
- Indicador de slide `"— 06"` no topo-esquerdo (cor ligeiramente mais clara)
- Título (branco, bold) + linha separadora (80px) + bullets ✓ (verde-claro `(120,255,140)`)

### Slide 7 — Antes/Depois (Split vertical)
- Metade esquerda: `(30,30,35)` (dark)
- Metade direita: cor primária (com imagem IA tintada pela cor primária como fundo)
- Linha separadora branca de 4px no meio
- Labels "ANTES" (fundo cinza-escuro, texto acinzentado) e "DEPOIS" (fundo semitransparente branco, texto branco) no topo de cada metade
- `texto` no JSON deve ter formato obrigatório: `"ANTES: [texto]\n---\nDEPOIS: [texto]"`; o composer split em `"\n---\n"`
- Título exibido no rodapé full-width (texto branco, centralizado)

### Slide 8 — CTA Final
- Fundo: cor primária com gradiente preto sutil na metade inferior
- Logo centralizada no topo (h=80px)
- Título (branco, bold, grande) + texto (branco 90%) centralizados verticalmente
- URL do site no rodapé centralizado (se disponível)

---

## 3. Prompt LLM — estrutura dos 8 slides

```
Slide 1 — Capa/Gancho: título (máx 6 palavras, impacto imediato) + texto (1 frase curta com dado ou estatística marcante, cite fonte). prompt_imagem: cena de ambiente físico de negócios/logística.

Slide 2 — Contexto: apresente o problema com dados concretos. Título curto + texto (2-3 frases com case real). prompt_imagem: cena contextual relacionada ao problema.

Slide 3 — Causa Raiz: por que o problema persiste. Título curto + texto direto (2 frases com argumento). prompt_imagem: cena que ilustre a causa.

Slide 4 — Impactos: liste 3 a 5 consequências operacionais/financeiras concretas usando EXATAMENTE o formato ✗ (um por linha, iniciando com ✗ seguido de espaço). Use dados reais com fonte. prompt_imagem: cena de ambiente impactado negativamente.

Slide 5 — A Virada: destaque um insight ou dado que muda a perspectiva. Título assertivo + texto com case real e resultado mensurável. Sem imagem.

Slide 6 — O que Funciona: liste 3 a 5 práticas ou resultados usando EXATAMENTE o formato ✓ (um por linha, iniciando com ✓ seguido de espaço). prompt_imagem: cena positiva/produtiva.

Slide 7 — Antes vs Depois: o texto deve ter EXATAMENTE este formato:
"ANTES: [descrição do estado problemático, 1-2 frases]\n---\nDEPOIS: [descrição do estado melhorado, 1-2 frases com dado]"
O título deve ser o tema central da comparação (máx 6 palavras). prompt_imagem: cena de transformação ou melhoria.

Slide 8 — Conclusão: fechamento com perspectiva estratégica. Título assertivo (máx 6 palavras) + texto final (2 frases com o princípio por trás, sem CTA, sem menção à empresa). Sem imagem.
```

JSON de resposta esperado:
```json
{
  "slides": [
    {"slide": 1, "titulo": "...", "texto": "...", "prompt_imagem": "..."},
    ...
    {"slide": 8, "titulo": "...", "texto": "...", "prompt_imagem": "..."}
  ]
}
```
Slides 5 e 8 podem ter `prompt_imagem` vazio (`""`).

---

## 4. Arquivos a modificar

### `modulos/gerador_imagens.py`

**Constantes a adicionar** (após `_SLIDEFINAL_TWEET_PATH`):
```python
_SLIDES_MISTO_DD_COM_IMAGEM = frozenset({1, 2, 3, 4, 6, 7})
_MISTO_DD_BULLETS_FAIL  = frozenset({4})   # ✗
_MISTO_DD_BULLETS_CHECK = frozenset({6})   # ✓
_MISTO_DD_BULLETS       = _MISTO_DD_BULLETS_FAIL | _MISTO_DD_BULLETS_CHECK
```

**Funções a adicionar** (no final do arquivo):
- `compor_slide_misto_dd(titulo, texto, empresa_nome, nome_fonte, *, logo_path, url_site, cor_primaria, imagem_bytes, slide_num) -> Image.Image`
  - Switch por `slide_num` (1–8), implementa cada layout descrito acima
- `_gerar_fundo_misto_dd(slide, identidade_visual) -> bytes | None`
  - Mesmo padrão de `_gerar_fundo_tweet`
- `gerar_imagens_carrossel_misto_dd(slides, empresa_id, empresa_nome, stem, identidade_visual, logo_index, callback) -> list[Path]`
  - Salva em `outputs/{empresa_id}/imagens_misto_dd/{stem}/slide_XX.png`
  - Gera imagem IA para slides em `_SLIDES_MISTO_DD_COM_IMAGEM`
- `gerar_imagem_slide_misto_dd(slide, empresa_id, empresa_nome, stem, identidade_visual, logo_index) -> Path`
  - Regeneração de slide único
- `listar_imagens_misto_dd(empresa_id, stem) -> list[Path]`
  - Mesmo padrão de `listar_imagens_tweet`

### `modulos/llm_brain.py`

**Constantes a adicionar:**
- `ESTRUTURA_CARROSSEL_MISTO_DD` — string com a estrutura dos 8 slides (ver seção 3)
- `PROMPT_MISTO_DD` — prompt completo (mesmo padrão de `SYSTEM_PROMPT` mas só para os 8 slides, resposta JSON `{"slides": [...]}`)

**Função a adicionar:**
- `gerar_carrossel_misto_dd(tema, empresa, empresa_id, publico_alvo, url_site) -> list[dict]`
  - Chama Gemini, parseia `response["slides"]`

**Função de save em `app.py`** (padrão de `salvar_carrossel_tweet`):
- `salvar_carrossel_misto_dd(slides, empresa_id, tema) -> Path`
  - Salva em `outputs/{empresa_id}/carrossel_misto_dd/{slug}_{ts}.json`

### `app.py`

**TIPOS dict:**
```python
TIPOS = {
    "carrossel":          "Carrossel",
    "carrossel_tweet":    "Carrossel Tweet",
    "carrossel_misto_dd": "Carrossel Misto DD",   # ← novo
    "linkedin":           "Post LinkedIn",
    "video":              "Narração Vídeo",
    "blog":               "Blog",
}
```

**`aba_gerar`:** Adicionar botão "Gerar Carrossel Misto DD" na linha de botões (col_btn3 ou nova linha), seguindo o padrão do botão "Gerar Carrossel Tweet".

**`aba_conteudos`:** Adicionar `sub_misto_dd` na lista de tabs, com UI idêntica ao bloco `sub_tweet`:
- Excluir / Regenerar texto
- Seletor de logo
- Gerar Imagens / Regenerar tudo / Baixar tudo
- Grid 3 colunas com ↓ Baixar e ↺ Slide por imagem
- Seção de texto dos slides abaixo

---

## 5. Decisões de design

| Decisão | Escolha |
|---------|---------|
| PAD (margem lateral) | 72px (igual ao tweet) |
| Gradiente na junção cor+imagem | `_gradiente_lateral()` existente |
| Semi-transparência | Sempre via `Image.alpha_composite` (canvas RGBA), não via tupla RGBA no draw |
| Bullets sem ✓/✗ no texto | Dot bullet (ellipse cor primária) como fallback |
| Fonte | `nome_fonte` da identidade visual da empresa |
| Pasta de saída imagens | `outputs/{empresa_id}/imagens_misto_dd/{stem}/` |
| Pasta de saída JSON | `outputs/{empresa_id}/carrossel_misto_dd/` |
| Slide estático final | Não há (diferente do tweet que tem slide 10 estático) |

---

## 6. Ordem de implementação recomendada

1. `llm_brain.py` — constantes + `gerar_carrossel_misto_dd()`
2. `gerador_imagens.py` — constantes + `compor_slide_misto_dd()` (slide por slide, testar visualmente)
3. `gerador_imagens.py` — `gerar_imagens_carrossel_misto_dd()` + `gerar_imagem_slide_misto_dd()` + `listar_imagens_misto_dd()`
4. `app.py` — `salvar_carrossel_misto_dd()` + TIPOS + botão em `aba_gerar` + bloco em `aba_conteudos`
