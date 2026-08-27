"""
Cloud Run job: processa agendamentos pendentes cujo data_hora já passou.
Acionado pelo Cloud Scheduler a cada minuto via HTTP POST.
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modulos.db import atualizar_agendamento, col_agenda


def processar_pendentes():
    agora = datetime.utcnow()
    pendentes = list(col_agenda().find({
        "status": "pendente",
        "data_hora": {"$lte": agora},
        "plataforma": {"$in": ["youtube_shorts", "tiktok"]},
    }))

    if not pendentes:
        print("[Worker] Nenhum agendamento pendente.")
        return

    print(f"[Worker] {len(pendentes)} agendamento(s) para processar.")
    publicados = 0
    erros = 0

    for doc in pendentes:
        agenda_id = str(doc["_id"])
        print(f"[Worker] → {agenda_id} | {doc['plataforma']} | {doc['data_hora']}")
        atualizar_agendamento(agenda_id, {"status": "processando"})
        tmp_path = None

        try:
            video_path = doc.get("video_path", "")
            if not video_path:
                raise ValueError("video_path não definido no agendamento")

            local_path = video_path
            if str(video_path).startswith("gs://"):
                from modulos.cloud_storage import download_video
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                tmp.close()
                tmp_path = tmp.name
                local_path = download_video(video_path, tmp_path)

            titulo = doc.get("texto") or "Vídeo"
            plataforma = doc["plataforma"]
            post_id = None

            if plataforma == "youtube_shorts":
                from modulos.publicador import publicar_youtube_shorts
                post_id = publicar_youtube_shorts(local_path, titulo, titulo)
            elif plataforma == "tiktok":
                from modulos.publicador import publicar_tiktok
                post_id = publicar_tiktok(local_path, titulo)
            else:
                raise ValueError(f"Plataforma não suportada: {plataforma}")

            atualizar_agendamento(agenda_id, {
                "status": "publicado",
                "platform_post_id": post_id,
                "erro_msg": None,
            })
            publicados += 1
            print(f"[Worker] ✓ {agenda_id}")

            # Apaga do GCS se não há mais agendamentos usando esse arquivo
            if str(video_path).startswith("gs://"):
                restantes = col_agenda().count_documents({
                    "video_path": video_path,
                    "status": {"$in": ["pendente", "processando"]},
                })
                if restantes == 0:
                    try:
                        from modulos.cloud_storage import delete_video
                        delete_video(video_path)
                        print(f"[GCS] Removido: {video_path}")
                    except Exception as e:
                        print(f"[GCS] Falha ao remover {video_path}: {e}", file=sys.stderr)

        except Exception as e:
            erros += 1
            atualizar_agendamento(agenda_id, {
                "status": "erro",
                "erro_msg": str(e),
            })
            print(f"[Worker] ✗ {agenda_id}: {e}", file=sys.stderr)

        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    print(f"[Worker] Concluído: {publicados} publicados, {erros} erros.")


# Suporte a HTTP (Cloud Run Jobs usa HTTP ou invocação direta)
try:
    from flask import Flask, jsonify
    _flask_app = Flask(__name__)

    @_flask_app.route("/", methods=["POST", "GET"])
    def run():
        processar_pendentes()
        return jsonify({"status": "ok"})

    def create_app():
        return _flask_app

except ImportError:
    pass

if __name__ == "__main__":
    processar_pendentes()
