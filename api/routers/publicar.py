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
        plataforma = doc["plataforma"]
        titulo = doc.get("texto") or "Vídeo"
        post_id = None

        if plataforma == "instagram":
            from pathlib import Path as _Path
            from modulos.db import buscar_credencial_instagram, buscar_conteudo
            from modulos.instagram_publisher import publicar_carrossel_instagram

            cred = buscar_credencial_instagram(doc["empresa_id"])
            if not cred:
                raise ValueError(f"Credenciais Instagram não configuradas para '{doc['empresa_id']}'")

            conteudo = buscar_conteudo(doc["conteudo_id"])
            if not conteudo:
                raise ValueError(f"Conteúdo {doc['conteudo_id']} não encontrado")

            imagens_paths = doc.get("imagens_paths") or []
            if not imagens_paths:
                stem = conteudo["stem"]
                empresa_id = conteudo["empresa_id"]
                tipo = conteudo.get("tipo", "carrossel")
                if tipo == "carrossel_misto_dd":
                    from modulos.gerador_imagens import listar_imagens_misto_dd
                    imagens = listar_imagens_misto_dd(empresa_id, stem)
                elif tipo == "carrossel_tweet":
                    from modulos.gerador_imagens import listar_imagens_tweet
                    imagens = listar_imagens_tweet(empresa_id, stem)
                elif tipo == "carrossel_oldschool":
                    from modulos.gerador_imagens import listar_imagens_oldschool
                    imagens = listar_imagens_oldschool(empresa_id, stem)
                else:
                    from modulos.gerador_imagens import listar_imagens
                    imagens = listar_imagens(empresa_id, stem)
                imagens_paths = [str(p) for p in imagens]

            if not imagens_paths:
                raise ValueError("Nenhuma imagem encontrada para publicar")

            caption = doc.get("texto") or conteudo.get("legenda") or ""
            post_id = publicar_carrossel_instagram(
                imagens=[_Path(p) for p in imagens_paths],
                caption=caption,
                access_token=cred["access_token"],
                empresa_id=doc["empresa_id"],
                stem=conteudo["stem"],
            )

        else:
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
