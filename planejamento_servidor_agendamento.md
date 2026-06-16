# Planejamento — Servidor GCP + Módulo de Agendamento

Criado em: 11 de junho de 2026

---

## Visão geral

Subir o projeto BOB em um servidor Google Cloud gratuito (e2-micro) para
desenvolvimento remoto via celular com Claude Code, e construir o módulo de
agendamento de postagens para TikTok e YouTube Shorts.

**Custo estimado:** R$ 0/mês (dentro do Always Free do GCP)

---

## Fase 1 — Servidor (e2-micro no GCP)

### 1.1 Criar a VM

- [ ] Criar projeto separado no Google Cloud Console (ex: `bob-server`)
- [ ] Ativar a API do Compute Engine no projeto
- [ ] Criar instância e2-micro:
  - Tipo: `e2-micro`
  - Região: `us-east1` (Carolina do Sul) — obrigatório para ser grátis
  - Disco: 30 GB padrão (HDD, não SSD)
  - SO: Ubuntu 24.04 LTS
  - Firewall: habilitar HTTP e HTTPS
- [ ] Reservar IP externo estático (para não mudar a cada reinicialização)
- [ ] Adicionar chave SSH pública (gerada no Termius)

### 1.2 Configurar o ambiente

Rodar o `setup.sh` na VM (a gerar):

- [ ] Atualizar o sistema
- [ ] Instalar Python 3.12 + pip
- [ ] Instalar Node.js 20 LTS
- [ ] Instalar Claude Code CLI (`npm install -g @anthropic/claude-code`)
- [ ] Instalar Google Cloud CLI
- [ ] Clonar o repositório do GitHub
- [ ] Instalar dependências Python (`pip install -r requirements.txt`)
- [ ] Criar arquivo `.env` com as variáveis de ambiente

### 1.3 Credenciais necessárias

**Variáveis de ambiente (`.env` na raiz do projeto):**
```
GEMINI_API_KEY=...
MONGODB_URI=...
GOOGLE_DRIVE_FOLDER_ID=...
```

**Arquivos a copiar do PC local para o servidor (via scp):**
```bash
scp config/oauth_client.json usuario@ip-do-servidor:~/bob/config/
scp config/drive_token.json  usuario@ip-do-servidor:~/bob/config/
```

> Esses arquivos gerenciam o OAuth do Google Drive. O `drive_token.json`
> precisa existir para o Drive funcionar sem precisar de browser no servidor.

### 1.4 Conectar pelo celular

- [ ] Instalar Termius (iOS ou Android)
- [ ] Adicionar host com o IP da VM e a chave SSH
- [ ] Testar conexão: `ssh usuario@ip-do-servidor`
- [ ] Testar Claude Code: `cd bob && claude`

---

## Fase 2 — Módulo de Agendamento

### 2.1 Visão geral do fluxo

```
PC local
  └── BOB gera o vídeo (.mp4)
  └── Faz upload para Cloud Storage

Cloud Scheduler (cron)
  └── No horário agendado, dispara Cloud Run

Cloud Run
  └── Baixa o vídeo do Cloud Storage
  └── Faz upload para TikTok / YouTube Shorts
  └── Registra o resultado no MongoDB
```

### 2.2 Estrutura de dados (MongoDB)

Nova collection: `agenda`

```json
{
  "_id": "...",
  "empresa_id": "tecnosolve",
  "titulo": "Ruptura na Gôndola",
  "video_path": "gs://bucket/tecnosolve/videos/arquivo.mp4",
  "plataformas": ["tiktok", "youtube_shorts"],
  "agendado_para": "2026-06-15T09:00:00Z",
  "status": "pendente",
  "resultado": null,
  "criado_em": "2026-06-11T..."
}
```

Status possíveis: `pendente` → `processando` → `publicado` | `erro`

### 2.3 Arquivos a criar

```
modulos/
  agendamento.py        # CRUD de agenda no MongoDB
  publicador.py         # upload para TikTok e YouTube Shorts
  cloud_storage.py      # upload/download de vídeos no GCS

cloud_run/
  main.py               # entrypoint do Cloud Run (chama publicador)
  Dockerfile
  requirements.txt
```

### 2.4 APIs externas necessárias

| Plataforma | API | Autenticação |
|---|---|---|
| **YouTube Shorts** | YouTube Data API v3 | OAuth 2.0 (já temos oauth_client.json) |
| **TikTok** | Content Posting API | OAuth 2.0 (conta de desenvolvedor TikTok) |

**Passos de autenticação:**
- YouTube: reutiliza o OAuth do Google já configurado
- TikTok: criar conta em developers.tiktok.com, criar app, obter `client_key` e `client_secret`

### 2.5 Infraestrutura GCP a configurar

- [ ] Ativar Cloud Storage → criar bucket `bob-videos-{seu-id}`
- [ ] Ativar Cloud Run
- [ ] Ativar Cloud Scheduler
- [ ] Criar Service Account com permissões:
  - Storage Object Viewer
  - Cloud Run Invoker

### 2.6 Ordem de implementação

1. `cloud_storage.py` — upload e download de vídeos no GCS
2. `agendamento.py` — CRUD de agendamentos no MongoDB
3. `publicador.py` — integração YouTube Shorts (mais fácil, OAuth já existe)
4. `publicador.py` — integração TikTok (nova autenticação)
5. `cloud_run/main.py` + Dockerfile — empacotar o publicador
6. Deploy no Cloud Run + configurar Cloud Scheduler
7. Integrar com o `app.py` (botão "Agendar Postagem" na UI)

---

## Fase 3 — Integração com a UI (Streamlit)

Nova aba ou seção na UI do BOB:

- Calendário de postagens por empresa
- Status de cada item (pendente / publicado / erro)
- Botão "Agendar" após gerar o vídeo
- Seleção de plataforma e horário

---

## Dependências e bloqueios

| Item | Status | Desbloqueio |
|---|---|---|
| Conta GCP com e2-micro free | Disponível | Criar VM |
| Repositório no GitHub | Disponível | Clonar no servidor |
| OAuth YouTube (Drive) | Disponível | Copiar token do PC |
| Conta TikTok Developer | Pendente | Cadastrar em developers.tiktok.com |
| Vídeo gerado pelo BOB | Em progresso (módulo de vídeo) | Finalizar teste_video.py |

---

## Próximos comandos práticos

```bash
# No celular (Termius), após VM configurada:
ssh gabriel@ip-da-vm
cd bob
claude "implemente o módulo cloud_storage.py para upload de vídeos no GCS"
```

```bash
# Para agendar uma postagem manualmente (teste):
python -c "
from modulos.agendamento import criar_agendamento
criar_agendamento('tecnosolve', 'outputs/.../video.mp4', ['youtube_shorts'], '2026-06-15T09:00:00')
"
```
