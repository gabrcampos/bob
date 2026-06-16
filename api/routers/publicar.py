import os
import tempfile

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException

from modulos.db import atualizar_agendamento, col_agenda

router = APIRouter(prefix="/publicar", tags=["Publicar"])


def _executar_publicacao(agenda_id: str):
    doc = col_agenda().find_one({"_id": ObjectId(agenda_id)})
    if not doc:
        return

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

    except Exception as e:
        atualizar_agendamento(agenda_id, {
            "status": "erro",
            "erro_msg": str(e),
        })
        print(f"[Publicador] Erro em {agenda_id}: {e}")

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


@router.post("/{agenda_id}", status_code=202)
def publicar(agenda_id: str, background_tasks: BackgroundTasks):
    """Dispara a publicação imediata de um agendamento (em background)."""
    doc = col_agenda().find_one({"_id": ObjectId(agenda_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    if doc["status"] not in ("pendente", "erro"):
        raise HTTPException(
            status_code=409,
            detail=f"Status '{doc['status']}' não permite nova publicação",
        )
    background_tasks.add_task(_executar_publicacao, agenda_id)
    return {"message": "Publicação iniciada", "agenda_id": agenda_id}
