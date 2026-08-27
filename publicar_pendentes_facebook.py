"""
Worker do Facebook — roda a cada 5 minutos via cron na VM.
Busca no MongoDB agendamentos pendentes para Facebook cujo horário já passou,
baixa o vídeo do GCS e publica na Página do Facebook.

Configuração do cron (rodar: crontab -e):
    */5 * * * * cd /home/campos_1122/bob && python3 publicar_pendentes_facebook.py >> logs/facebook_cron.log 2>&1
    0 3 * * 1 truncate -s 0 /home/campos_1122/bob/logs/facebook_cron.log

Uso manual:
    python3 publicar_pendentes_facebook.py            # processa pendentes normalmente
    python3 publicar_pendentes_facebook.py --forcar   # força publicação do próximo pendente
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def processar_pendentes(forcar: bool = False):
    from modulos.db import atualizar_agendamento, col_agenda
    from modulos.publicador_facebook import carregar_config, publicar_video_facebook
    from modulos.cloud_storage import download_video, delete_video

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    filtro = {"plataforma": "facebook", "status": "pendente"}
    if not forcar:
        filtro["data_hora"] = {"$lte": agora}

    pendentes = list(col_agenda().find(filtro).sort("data_hora", 1))
    if forcar and pendentes:
        pendentes = pendentes[:1]

    if not pendentes:
        print(f"[Facebook] {agora.strftime('%Y-%m-%d %H:%M')} UTC — nenhum agendamento pendente.")
        return

    print(f"[Facebook] {agora.strftime('%Y-%m-%d %H:%M')} UTC — {len(pendentes)} post(s) para publicar.")

    try:
        config = carregar_config()
        page_id = config["page_id"]
        page_access_token = config["page_access_token"]
    except FileNotFoundError as e:
        print(f"[Facebook] ✗ Configuração não encontrada: {e}", file=sys.stderr)
        return

    publicados = 0
    erros = 0

    for doc in pendentes:
        agenda_id = str(doc["_id"])
        shortcode = doc.get("source_id", agenda_id)
        print(f"[Facebook] → {shortcode} | {doc.get('data_hora')}")
        atualizar_agendamento(agenda_id, {"status": "processando"})

        tmp_path = None
        video_path = doc.get("video_path", "")

        try:
            if not video_path:
                raise ValueError("video_path não definido no agendamento")

            if str(video_path).startswith("gs://"):
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                tmp.close()
                tmp_path = tmp.name
                local_path = download_video(video_path, tmp_path)
            else:
                local_path = Path(video_path)
                if not local_path.exists():
                    raise FileNotFoundError(f"Arquivo não encontrado: {local_path}")

            descricao = doc.get("texto") or shortcode

            post_id = publicar_video_facebook(
                video_path=str(local_path),
                descricao=descricao,
                page_id=page_id,
                page_access_token=page_access_token,
            )

            atualizar_agendamento(agenda_id, {
                "status": "publicado",
                "platform_post_id": post_id,
                "erro_msg": None,
            })
            publicados += 1
            print(f"[Facebook] ✓ {shortcode} → post_id={post_id}")

            # Remove do GCS se não há mais agendamentos pendentes usando esse arquivo
            if str(video_path).startswith("gs://"):
                restantes = col_agenda().count_documents({
                    "video_path": video_path,
                    "status": {"$in": ["pendente", "processando"]},
                })
                if restantes == 0:
                    try:
                        delete_video(video_path)
                    except Exception as e:
                        print(f"[GCS] Falha ao remover {video_path}: {e}", file=sys.stderr)

        except Exception as e:
            erros += 1
            atualizar_agendamento(agenda_id, {
                "status": "erro",
                "erro_msg": str(e),
            })
            print(f"[Facebook] ✗ {shortcode}: {e}", file=sys.stderr)

        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    print(f"[Facebook] Concluído: {publicados} publicados, {erros} erros.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar", action="store_true",
                        help="Publica o próximo pendente independente do horário (para testes)")
    args = parser.parse_args()
    processar_pendentes(forcar=args.forcar)


if __name__ == "__main__":
    main()
