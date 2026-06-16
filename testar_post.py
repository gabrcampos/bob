"""
Posta o próximo agendamento pendente imediatamente (teste manual).
Rode no PC local.
"""
import os
import tempfile
from modulos.db import col_agenda, atualizar_agendamento, _doc_para_dict
from datetime import datetime, timezone

# Busca o próximo pendente (o de data_hora mais próxima)
doc = col_agenda().find_one(
    {"status": "pendente", "empresa_id": "fs_negao"},
    sort=[("data_hora", 1)]
)

if not doc:
    print("Nenhum agendamento pendente encontrado.")
    exit()

doc = _doc_para_dict(doc)
agenda_id = doc["_id"]
print(f"Postando: {doc['source_id']} agendado para {doc['data_hora']}")
print(f"Vídeo: {doc['video_path']}")

atualizar_agendamento(agenda_id, {"status": "processando"})

tmp_path = None
try:
    # Baixar do GCS
    from modulos.cloud_storage import download_video
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    tmp_path = tmp.name
    local_path = download_video(doc["video_path"], tmp_path)
    print(f"Download concluído: {local_path}")

    # Postar no YouTube
    from modulos.publicador import publicar_youtube_shorts
    titulo = doc.get("texto") or doc["source_id"]
    video_id = publicar_youtube_shorts(local_path, titulo, titulo)

    atualizar_agendamento(agenda_id, {
        "status": "publicado",
        "platform_post_id": video_id,
        "erro_msg": None,
    })
    print(f"Publicado: https://youtube.com/shorts/{video_id}")

except Exception as e:
    atualizar_agendamento(agenda_id, {"status": "erro", "erro_msg": str(e)})
    print(f"Erro: {e}")
    raise

finally:
    if tmp_path:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
