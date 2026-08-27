"""Publicação de vídeos em Página do Facebook via Graph API."""

import json
from pathlib import Path

import requests

GRAPH_URL = "https://graph.facebook.com/v21.0"
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "facebook_doisbe.json"


def carregar_config() -> dict:
    """Lê config/facebook_doisbe.json e retorna page_id + page_access_token."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {_CONFIG_PATH}\n"
            "Gabriel precisa gerar o token no Graph API Explorer e salvar o arquivo."
        )
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def publicar_video_facebook(
    video_path: str,
    descricao: str,
    page_id: str,
    page_access_token: str,
    scheduled_publish_time: int | None = None,
) -> str:
    """
    Publica (ou agenda) um vídeo em uma Página do Facebook.

    Args:
        video_path: caminho local do arquivo de vídeo (.mp4 ou .mov)
        descricao: texto/legenda do post
        page_id: ID da Página do Facebook
        page_access_token: token de acesso da página (longa duração)
        scheduled_publish_time: unix timestamp para agendamento (opcional)
            - mínimo: 10 minutos no futuro
            - máximo: 30 dias no futuro

    Returns:
        video_id: ID do vídeo publicado no Facebook
    """
    url = f"{GRAPH_URL}/{page_id}/videos"

    data: dict = {
        "access_token": page_access_token,
        "description": descricao,
    }

    if scheduled_publish_time:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(scheduled_publish_time)
    else:
        data["published"] = "true"

    video_path = Path(video_path)
    with open(video_path, "rb") as f:
        resp = requests.post(
            url,
            data=data,
            files={"source": (video_path.name, f, "video/mp4")},
            timeout=300,
        )

    if not resp.ok:
        raise RuntimeError(
            f"Erro Facebook API {resp.status_code}: {resp.text}"
        )

    resultado = resp.json()
    if "id" not in resultado:
        raise RuntimeError(f"Resposta inesperada da API: {resultado}")

    return resultado["id"]
