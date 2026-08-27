# Planejamento — @doisbe.tv → Facebook (lote semanal)

Criado em: 21 de julho de 2026

**Branch de desenvolvimento:** `marcos`
**Divisão de responsabilidades:** Gabriel faz a parte do Meta Developers (tokens). Marcos implementa o código.

---

## Objetivo

Baixar todos os vídeos do perfil Instagram `@doisbe.tv` e publicar automaticamente
na **Página do Facebook** vinculada a esse Instagram, em lotes semanais de **3 vídeos/dia**.

---

## O que já existe (reaproveitável)

| Componente | Arquivo | Status |
|---|---|---|
| Download de vídeos do Instagram | `modulos/instagram.py` | ✅ Pronto |
| Upload para GCS | `modulos/cloud_storage.py` | ✅ Pronto |
| CRUD de agendamento (MongoDB) | `modulos/db.py` | ✅ Pronto |
| Worker Cloud Run | `cloud_run/main.py` | ⚠️ Com problema |
| Cloud Scheduler | GCP Console | ⚠️ A verificar |
| Publicador YouTube | `modulos/publicador.py` | ✅ (não usar aqui) |

**O que NÃO existe e precisa ser criado:**
- Publicador para **Facebook Page** (Graph API)
- Rotina específica para `@doisbe.tv`
- Script de diagnóstico do agendamento na VM

---

## Fase 0 — Diagnóstico do agendamento atual

> O agendamento via Cloud Run "não funcionou bem" — precisamos entender o problema
> antes de construir em cima.

### 0.1 Verificar logs do Cloud Run
```bash
gcloud run services logs read bob-worker --region=us-east1 --limit=100
```

Sinais a procurar:
- `Error` ou `Exception` nos últimos dias
- Timeout (Cloud Run tem limite de 60s por padrão — pode ser curto para upload de vídeo)
- Token expirado (YouTube OAuth `invalid_grant`)

### 0.2 Verificar Cloud Scheduler
```bash
gcloud scheduler jobs list --location=us-east1
gcloud scheduler jobs describe bob-worker-job --location=us-east1
```

Verificar:
- Se o job está ativo (`state: ENABLED`)
- Histórico de execuções (successes vs. failures)

### 0.3 Verificar agendamentos no MongoDB
```bash
python3 -c "
from modulos.db import listar_agenda
items = listar_agenda()
for a in items[:20]:
    print(a.get('status'), a.get('plataforma'), a.get('data_hora'), a.get('empresa_id'))
"
```

### 0.4 Decisão: Cloud Run vs. cron na VM

| Opção | Prós | Contras |
|---|---|---|
| **Cloud Run + Cloud Scheduler** | Sem custo, escala, resiliente | Timeout curto, depende de deploy |
| **Cron diretamente na VM** | Simples, fácil de debugar, sem limite de tempo | VM precisa estar sempre ativa |

**Recomendação:** usar cron na VM enquanto diagnosticamos o Cloud Run.
Upload de vídeo para Facebook pode levar vários minutos — Cloud Run com timeout padrão falha.

---

## Fase 1 — Autenticação Facebook

> **Responsável: Gabriel** — etapa manual no Meta Developers, sem código.

### 1.1 App Meta

Usar o **mesmo app Meta já existente** (o que publica Tecnosolve e DeliveryDash no Instagram).
Não é necessário criar um novo app.

Adicionar permissões ao app (cumulativo — não afeta tokens já gerados):
- `pages_manage_posts`
- `publish_video`
- `pages_read_engagement` (provavelmente já existe)

### 1.2 Gerar Page Access Token para o doisbe.tv

1. Abrir o **Graph API Explorer** com o mesmo app
2. Trocar a página selecionada para a Página do Facebook vinculada ao `@doisbe.tv`
3. Selecionar permissões: `pages_manage_posts`, `publish_video`, `pages_read_engagement`
4. Gerar token de curta duração
5. Trocar por token de **longa duração** (60 dias):
   ```
   GET /oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={app_id}
     &client_secret={app_secret}
     &fb_exchange_token={token_curto}
   ```
6. Pegar o `page_id` da página:
   ```
   GET /me/accounts
   ```

### 1.3 Salvar na VM

Criar `config/facebook_doisbe.json` na VM:
```json
{
  "page_id": "...",
  "page_access_token": "...",
  "app_id": "...",
  "app_secret": "...",
  "token_expiry": "YYYY-MM-DD"
}
```

> Quando esse arquivo existir na VM, o Marcos pode testar a publicação.

---

## Fase 2 — Publicador Facebook

Criar `modulos/publicador_facebook.py` com:

```python
def publicar_video_facebook(
    video_path: str,   # arquivo local ou GCS URI
    descricao: str,
    page_id: str,
    page_access_token: str,
    scheduled_publish_time: int | None = None,  # unix timestamp
) -> str:
    # Retorna o video_id publicado
    ...
```

### Endpoint da Graph API

```
POST /{page_id}/videos
  ?access_token={page_access_token}
  
Body (multipart/form-data):
  source: <arquivo de vídeo>
  description: <texto do post>
  published: false  (se agendado)
  scheduled_publish_time: <unix timestamp>  (se agendado)
```

**Limites do Facebook:**
- Tamanho máximo: 10 GB (sem problema para Reels curtos)
- Duração máxima para Reels: 90 segundos
- Formatos: MP4, MOV
- O agendamento tem janela mínima de 10 minutos no futuro e máxima de 30 dias

### Tratamento de Reels vs. Vídeo regular

Vídeos até 90s publicados verticalmente são tratados como **Reels** automaticamente.
Para forçar Reels usar o endpoint alternativo:
```
POST /{page_id}/video_reels
```

---

## Fase 3 — Rotina semanal @doisbe.tv → Facebook

Criar `rotina_doisbe_facebook.py` (espelho do `rotina_instagram_youtube.py`):

### Fluxo

```
1. Listar vídeos do @doisbe.tv com instaloader
2. Filtrar: só os não agendados ainda (por shortcode no MongoDB)
3. Ordenar: por views (mais assistidos primeiro) ou cronológico
4. Selecionar: 3 vídeos/dia × 7 dias = 21 vídeos por lote
5. Para cada vídeo:
   a. Baixar localmente
   b. Upload para GCS (backup + evita baixar de novo)
   c. Agendar no MongoDB (status: pendente)
6. Imprimir resumo do lote gerado
```

### Slots de horário (BRT → UTC)

```python
# Horários em UTC:
SLOTS_UTC = [12, 17, 22]  # = 9h, 14h, 19h BRT
POSTS_POR_DIA = 3
```

### Comando de uso

```bash
# Gerar lote semanal (rodar manualmente toda segunda-feira):
python3 rotina_doisbe_facebook.py --perfil doisbe.tv --dias 7

# Ver o que está agendado:
python3 rotina_doisbe_facebook.py --listar
```

---

## Fase 4 — Agendamento na VM (cron)

Substituir Cloud Run pelo cron da VM enquanto o problema do Cloud Run não está resolvido.

### 4.1 Script de execução

Criar `publicar_pendentes_facebook.py`:
```python
"""Roda a cada 5 minutos via cron. Publica posts que estão no horário."""
# Busca no MongoDB: status=pendente, data_hora <= agora, plataforma=facebook
# Para cada um: baixa GCS → publica Facebook Graph API → atualiza status
```

### 4.2 Configurar cron na VM

```bash
crontab -e
```

Adicionar:
```cron
# Publicador Facebook — a cada 5 minutos
*/5 * * * * cd /home/campos_1122/bob && python3 publicar_pendentes_facebook.py >> logs/facebook_cron.log 2>&1

# Limpeza de log semanal
0 3 * * 1 truncate -s 0 /home/campos_1122/bob/logs/facebook_cron.log
```

### 4.3 Criar pasta de logs
```bash
mkdir -p /home/campos_1122/bob/logs
```

### 4.4 Monitoramento

- Log em `logs/facebook_cron.log`
- Em caso de erro, enviar alerta via Telegram (reutilizar `modulos/telegram_bot.py` se existir)

---

## Fase 5 — Renovação de token Facebook

Token de longa duração expira em 60 dias. Solução:

### Opção A — Renovação manual (simples)
- Alerta via Telegram 7 dias antes do vencimento
- Renovar manualmente no Graph API Explorer

### Opção B — Renovação automática (ideal a longo prazo)
- System User token (não expira) via Meta Business Manager
- Requer configurar no painel de negócios da Meta

**Recomendação inicial:** Opção A. Se virar rotina, migrar para Opção B.

---

## Ordem de implementação

| # | Tarefa | Responsável | Depende de | Estimativa |
|---|---|---|---|---|
| 1 | Diagnóstico do agendamento atual (Fase 0) | Marcos | — | 30 min |
| 2 | Adicionar permissões ao app Meta + gerar token doisbe.tv (Fase 1) | **Gabriel** | — | 45 min |
| 3 | Criar `publicador_facebook.py` (Fase 2) | Marcos | Token de Gabriel | 2h |
| 4 | Criar `rotina_doisbe_facebook.py` (Fase 3) | Marcos | Publicador | 1h |
| 5 | Configurar cron na VM (Fase 4) | Marcos | Rotina | 30 min |
| 6 | Testar ponta-a-ponta com 1 vídeo | Marcos + Gabriel | Tudo acima | 1h |
| 7 | Gerar primeiro lote de 21 vídeos | Marcos | Teste OK | — |
| 8 | Renovação de token (Fase 5, Opção A) | Gabriel | Token próximo de expirar | — |

> Todo o desenvolvimento acontece na branch `marcos`. Merge para `main` só após teste ponta-a-ponta aprovado.

---

## Dependências externas

| Item | Status | Ação necessária |
|---|---|---|
| App no Meta / Facebook Developers | ❌ Pendente | Criar em developers.facebook.com |
| Page Access Token @doisbe.tv | ❌ Pendente | Gerado pelo app acima |
| `page_id` da página Facebook | ❌ Pendente | Via `GET /me/accounts` |
| instaloader autenticado | ⚠️ Verificar | Sessão pode ter expirado |
| GCS bucket | ✅ Existe | `gs://bob-videos-487590427215` |
| MongoDB Atlas | ✅ Existe | Collection `agenda` já tem índice por `source_id` |

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Instagram bloqueia download (rate limit / conta privada) | Usar sessão autenticada no instaloader; adicionar delay entre downloads |
| Token Facebook expira sem aviso | Salvar `token_expiry` e alertar via Telegram com antecedência |
| Cron não dispara se VM reiniciar | Verificar `crontab -l` após reinicialização; considerar `@reboot` como garantia |
| Vídeo duplicado no Facebook | Deduplicação por `shortcode` no MongoDB antes de agendar |
| Vídeo > 90s virar post comum (não Reel) | Filtrar no download ou usar endpoint `/video_reels` explicitamente |

---

## Referência rápida (após implementado)

```bash
# Diagnóstico rápido
python3 -c "from modulos.db import listar_agenda; [print(a['status'], a['data_hora']) for a in listar_agenda(plataforma='facebook')]"

# Ver log do cron
tail -f /home/campos_1122/bob/logs/facebook_cron.log

# Forçar publicação agora (teste)
python3 publicar_pendentes_facebook.py --forcar

# Gerar lote semanal
python3 rotina_doisbe_facebook.py --perfil doisbe.tv --dias 7
```
