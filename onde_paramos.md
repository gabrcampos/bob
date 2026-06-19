# Onde Paramos

Atualizado em: 19 de junho de 2026

---

## Status geral

Pipeline Instagram → YouTube Shorts 100% funcional, incluindo publicação automática via Cloud Run.
19 vídeos com agendamentos futuros. O Cloud Run publica automaticamente a cada 5 minutos quando chega o horário.

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
| Secret Manager | `mongodb-uri`, `youtube-token` |
| IP estático do servidor | `35.190.152.94` (fixo, nunca muda) |
| YouTube OAuth | montado via Secret Manager em `/app/config/youtube_token.json` |

---

## Horários de postagem

5 posts por dia, nos melhores horários para YouTube Shorts:

| BRT | UTC |
|---|---|
| 07:00 | 10:00 |
| 12:00 | 15:00 |
| 17:00 | 20:00 |
| 21:00 | 00:00 (dia seguinte) |
| 00:00 | 03:00 (dia seguinte) |

---

## Comportamento do worker

- Após publicar, deleta automaticamente o arquivo do GCS **se não houver mais agendamentos pendentes** usando aquele arquivo
- Vídeos com múltiplos agendamentos (ex: reposts) são mantidos no bucket até o último post

---

## Agendamentos especiais

- **C_BGSqdRfX9** ("Você se dá bem com criança?") agendado toda terça e sábado às 17h BRT até 14/07/2026

---

## Pendências / próximos passos

- [ ] **Reabastecer a fila** — rodar `rotina_listar.py` + `rotina_instagram_youtube.py` no PC local
  para agendar os slots de 00h BRT (03:00 UTC) que ainda estão vazios para a semana atual,
  e agendar a próxima semana completa (5 posts/dia)

- [ ] **Migrar para Instagram Basic Display API** — usar a conta @fs_negao diretamente
  para evitar risco de bloqueio da conta usada hoje para scraping via cookies.txt

---

## Credenciais importantes

| Arquivo | O que é | Onde está |
|---|---|---|
| `config/youtube_token.json` | OAuth do canal YouTube destino | Secret Manager + PC local |
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

# Deletar do GCS arquivos sem agendamentos pendentes (servidor)
# (feito manualmente quando necessário)
```
