# Status — Módulo de Agendamento Instagram → YouTube

Atualizado em: 16 de junho de 2026

---

## O que está no ar

| Componente | Status | Detalhe |
|---|---|---|
| Cloud Run Worker | ✅ Rodando | `https://bob-worker-qq45ltq2bq-ue.a.run.app` |
| Cloud Scheduler | ✅ Ativo | Dispara a cada 5 min, verifica pendentes |
| Bucket GCS | ✅ Criado | `gs://bob-videos-487590427215` |
| Secret Manager | ✅ | `mongodb-uri` armazenado |
| YouTube OAuth | ✅ | `config/youtube_token.json` no servidor (no .gitignore) |

## O que está implementado (código)

| Arquivo | Função |
|---|---|
| `modulos/instagram.py` | Baixa vídeos de perfil público via instaloader |
| `modulos/publicador.py` | Publica no YouTube Shorts e TikTok |
| `modulos/cloud_storage.py` | Upload/download no GCS (bucket `bob-videos-487590427215`) |
| `modulos/db.py` | CRUD de agendamentos + `ja_agendado()` para deduplicação |
| `cloud_run/main.py` | Worker: processa agendamentos pendentes |
| `rotina_instagram_youtube.py` | Script local — orquestra tudo (ver uso abaixo) |

---

## Como usar a rotina

Rodar **localmente** (PC com Python + pip):

```bash
pip install instaloader
python rotina_instagram_youtube.py --perfil <handle_instagram>
```

O que o script faz:
1. Varre o perfil desde **29/07/2023**, filtra só vídeos
2. Ordena pelos **mais assistidos** primeiro
3. Pula os que já estão no MongoDB (deduplicação pelo shortcode)
4. Baixa → sobe pro GCS → agenda no MongoDB
5. Distribui **4 por dia**: 7h, 12h, 17h, 21h (BRT)
6. Cloud Run publica no YouTube automaticamente no horário certo

Rodar toda semana — só agenda os vídeos novos.

---

## Pendências

### Bloqueio imediato
- [ ] **Push pro GitHub bloqueado** — token do remote expirou/sem permissão de escrita.
  Gerar novo PAT em `github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)` (permissão `repo`) e rodar:
  ```bash
  git remote set-url origin https://SEU_TOKEN@github.com/gabrcampos/bob.git
  git push origin main
  ```
  Após isso, fazer `git pull` no PC local para ter os arquivos novos.

### Próximos passos (quando quiser)
- [ ] Testar a rotina com um perfil real (`python rotina_instagram_youtube.py --perfil handle`)
- [ ] Verificar logs do Cloud Run após o primeiro post (`gcloud run services logs read bob-worker --region=us-east1 --limit=50`)
- [ ] TikTok: criar conta em `developers.tiktok.com`, obter `TIKTOK_ACCESS_TOKEN` e adicionar no `.env`

---

## Referência rápida

```bash
# Ver logs do worker
gcloud run services logs read bob-worker --region=us-east1 --limit=50

# Forçar execução do scheduler agora
gcloud scheduler jobs run bob-worker-job --location=us-east1

# Ver agendamentos no MongoDB (via Python)
python3 -c "from modulos.db import listar_agenda; [print(a) for a in listar_agenda()]"
```
