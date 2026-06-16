# Onde Paramos

Atualizado em: 16 de junho de 2026

---

## Status geral

Pipeline Instagram → YouTube Shorts 100% funcional, incluindo publicação automática via Cloud Run.

26 vídeos do perfil @fs_negao agendados de 17/06 a 23/06/2026 (2 já publicados hoje).
O Cloud Run publica automaticamente a cada 5 minutos quando chega o horário.

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
| Cloud Run | `https://bob-worker-487590427215.us-east1.run.app` |
| Cloud Scheduler | `bob-worker-job` — a cada 5 minutos |
| Bucket GCS | `gs://bob-videos-487590427215` |
| Secret Manager | `mongodb-uri` |
| YouTube OAuth | `config/youtube_token.json` — conta do canal destino |

---

## Horários de postagem

4 posts por dia, nos melhores horários para YouTube Shorts:

| BRT | UTC |
|---|---|
| 07:00 | 10:00 |
| 12:00 | 15:00 |
| 17:00 | 20:00 |
| 21:00 | 00:00 (dia seguinte) |

---

## Pendências / próximos passos

- [ ] **Automatizar a rotina semanal** — rodar `rotina_listar.py` + `rotina_instagram_youtube.py`
  toda semana para abastecer a fila com os próximos 28 vídeos
  (sugestão: toda segunda-feira de manhã)

- [ ] **Migrar para Instagram Basic Display API** — usar a conta @fs_negao diretamente
  para evitar risco de bloqueio da conta usada hoje para scraping via cookies.txt

---

## Credenciais importantes

| Arquivo | O que é | Onde está |
|---|---|---|
| `config/youtube_token.json` | OAuth do canal YouTube destino | Servidor + PC local |
| `config/service_account.json` | Service Account GCP para GCS | Servidor + PC local |
| `.env` | MONGODB_URI | Servidor (não está no git) |
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

# Listar vídeos do Instagram e gerar JSON (PC local)
python rotina_listar.py --perfil fs_negao

# Baixar, subir e agendar a partir do JSON (PC local)
python rotina_instagram_youtube.py --lista lista_fs_negao.json
```
