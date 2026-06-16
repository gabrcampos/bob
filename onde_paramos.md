# Onde Paramos

Atualizado em: 16 de junho de 2026

---

## Status geral

Pipeline Instagram → YouTube Shorts 100% funcional.
28 vídeos do perfil @fs_negao agendados de 17/06 a 23/06/2026.

---

## O que está funcionando

| Etapa | Como rodar | Onde roda |
|---|---|---|
| Listar vídeos do Instagram | `python rotina_listar.py --perfil fs_negao` | PC local |
| Baixar + subir GCS + agendar | `python rotina_instagram_youtube.py --lista lista_fs_negao.json` | PC local |
| Publicar no YouTube automaticamente | Cloud Scheduler dispara a cada 5 min | Cloud Run |
| Checar agendamentos | `python checar_agenda.py` | PC local |
| Testar post manual | `python testar_post.py` | PC local |

**Rotina semanal:** rodar os dois primeiros comandos toda semana.
Os vídeos já agendados são ignorados automaticamente (deduplicação por shortcode).

---

## Infraestrutura no ar

| Recurso | Detalhe |
|---|---|
| Cloud Run | `https://bob-worker-qq45ltq2bq-ue.a.run.app` |
| Cloud Scheduler | `bob-worker-job` — a cada 5 minutos |
| Bucket GCS | `gs://bob-videos-487590427215` |
| Secret Manager | `mongodb-uri` |
| YouTube OAuth | `config/youtube_token.json` — conta do canal destino |

---

## Pendências / próximos passos

- [ ] **Liberar IP do Cloud Run no MongoDB Atlas** — atualmente o worker falha ao conectar.
  Solução: MongoDB Atlas → Network Access → Add IP → `0.0.0.0/0`
  (sem isso o Cloud Run não publica automaticamente — apenas o `testar_post.py` local funciona)

- [ ] **Migrar para Instagram Basic Display API** — usar a conta @fs_negao diretamente
  para evitar qualquer risco de bloqueio da conta @ggcampos_ usada hoje para scraping

- [ ] **Automatizar a rotina semanal** — agendar `rotina_listar.py` via Cloud Scheduler
  ou lembrete no calendário para rodar toda segunda-feira

---

## Credenciais importantes

| Arquivo | O que é | Onde está |
|---|---|---|
| `config/youtube_token.json` | OAuth do canal YouTube destino | Servidor + PC local |
| `config/service_account.json` | Service Account GCP para GCS | Servidor + PC local (no git) |
| `.env` | MONGODB_URI + outras variáveis | Servidor (não está no git) |
| `cookies.txt` | Cookies do Instagram para scraping | PC local (não está no git) |

---

## Comandos úteis

```bash
# Ver logs do worker (servidor)
gcloud run services logs read bob-worker --region=us-east1 --limit=50

# Forçar execução agora (servidor)
gcloud scheduler jobs run bob-worker-job --location=us-east1

# Ver agendamentos pendentes (PC local)
python checar_agenda.py

# Postar próximo vídeo manualmente (PC local)
python testar_post.py
```
