# Onde Paramos — Rotina Semanal de Posts

## Status atual: aguardando conexão do GitHub

---

## O que foi feito nessa sessão

### Posts publicados hoje (13/07/2026)
- **Tecnosolve** `carrossel_tweet` — "Infraestrutura de TI no varejo: de centro de custo a ativo estratégico" — media_id `18157079287473084`
- **DeliveryDash** `carrossel_misto_dd` — "Taxa de cancelamento alta? O problema raramente é o prato" — media_id `18016941758857287`

### Melhorias implementadas no código

**`modulos/llm_brain.py`**
- `_revisar_conteudo()`: roda após cada geração de carrossel. Detecta clichês, verifica repetição de tema, corrige legenda automaticamente (CTA por empresa, remove travessão, garante 2+ quebras de linha, aplica hashtags fixas).

**`modulos/gerador_imagens.py`**
- `_reescrever_prompt_dd()`: usa Gemini 2.5 Flash para reescrever prompts sem contexto de restaurante antes de gerar imagem no carrossel_misto_dd.
- `gerar_imagens_carrossel_tweet`: `logo_index` default alterado de 1 → 2 (logo escura para TS).
- `gerar_imagem_slide_tweet`: idem.

**`gerar_post.py`**
- `_drive_client()`: removida dependência de `gcloud auth print-access-token`. Agora usa `token=None` e deixa a biblioteca auto-renovar via `refresh_token`. Funciona sem gcloud CLI (necessário para o cloud agent).

**`gerar_semanal.py`** *(novo)*
- Script que o cloud agent executa toda segunda. Recebe dois temas como argumento, gera ambos os posts, faz upload pro Drive e lista os caminhos das imagens para revisão visual.

**`CLAUDE.md`** *(novo)*
- Regras de revisão visual por empresa/tipo, regras de legenda, clichês proibidos, fluxo completo de geração.

---

## Próximo passo: ativar a rotina semanal

### O que falta
1. **Conectar GitHub** ao Claude Code:
   - Acesse: https://claude.ai/code/onboarding?magic=github-app-setup
   - Instale o Claude GitHub App no repositório `gabrcampos/bob`

2. **Depois disso**, abrir esta conversa e pedir: `"crie a rotina semanal"` — o prompt já está pronto.

### O que a rotina faz (toda segunda-feira às 09h BRT)
1. Clona o repositório `gabrcampos/bob`
2. Cria o `.env` com as credenciais
3. Instala dependências
4. Consulta os últimos posts no MongoDB e escolhe temas novos
5. Gera `carrossel_tweet` para Tecnosolve e `carrossel_misto_dd` para DeliveryDash
6. Faz revisão visual de cada PNG (Claude lê as imagens e corrige o que estiver errado)
7. Envia PDFs + legendas + links do Drive para o Telegram
8. **Não publica** — aguarda aprovação manual

### Credenciais necessárias (já embutidas no prompt da rotina)
- `GEMINI_API_KEY`, `MONGODB_URI`, `FACEBOOK_APP_ID/SECRET`, `TELEGRAM_BOT_TOKEN/CHAT_ID`
- `config/service_account.json` (GCS) e `config/youtube_token.json` (Drive) — já estão no repositório

---

## Regras fixas por empresa (resumo)

| Empresa | Tipo | Logo | CTA |
|---|---|---|---|
| Tecnosolve | carrossel_tweet | index 2 (escura) | "Fale com um especialista - link na bio." |
| DeliveryDash | carrossel_misto_dd | index 1 | "Teste gratuitamente o DeliveryDash por 7 dias - link na bio." |

**Clichês proibidos:** apagar incêndio, modo crise, no mundo de hoje, descubra como, transformação digital (genérico).
