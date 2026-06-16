"""
Publicador de vídeos em plataformas de short-form.
Suporte: YouTube Shorts (OAuth 2.0) e TikTok (Content Posting API).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_YT_TOKEN_FILE = Path("config/youtube_token.json")
_CLIENT_SECRET = Path("config/oauth_client.json")
_YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ──────────────────────────────────────────────
# YouTube Shorts
# ──────────────────────────────────────────────

def _yt_creds():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if _YT_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_YT_TOKEN_FILE), _YT_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CLIENT_SECRET.exists():
                raise FileNotFoundError(
                    f"'{_CLIENT_SECRET}' não encontrado. "
                    "Baixe o OAuth 2.0 Client ID no Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRET), _YT_SCOPES)
            creds = flow.run_local_server(port=0)
        _YT_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _YT_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def yt_esta_autenticado() -> bool:
    if not _YT_TOKEN_FILE.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(_YT_TOKEN_FILE), _YT_SCOPES)
        if creds and creds.valid:
            return True
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _YT_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def yt_autenticar() -> bool:
    """Abre o fluxo OAuth do YouTube no navegador."""
    _yt_creds()
    return True


def publicar_youtube_shorts(
    video_path: str | Path,
    titulo: str,
    descricao: str = "",
    privacidade: str = "public",
) -> str:
    """
    Faz upload para o YouTube Shorts.
    Retorna o ID do vídeo publicado.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _yt_creds()
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)

    if "#Shorts" not in descricao and "#shorts" not in descricao:
        descricao = f"{descricao}\n#Shorts".strip()

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacidade,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=256 * 1024,
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    print(f"[YouTube] Publicado: https://youtube.com/shorts/{video_id}")
    return video_id


# ──────────────────────────────────────────────
# TikTok
# ──────────────────────────────────────────────

def _tiktok_token() -> str:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("TIKTOK_ACCESS_TOKEN não definida no .env")
    return token


def publicar_tiktok(
    video_path: str | Path,
    titulo: str,
    privacidade: str = "PUBLIC_TO_EVERYONE",
) -> str:
    """
    Faz upload para o TikTok via Content Posting API.
    Retorna o publish_id.
    privacidade: PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR | SELF_ONLY
    """
    import requests

    token = _tiktok_token()
    video_path = Path(video_path)
    video_size = video_path.stat().st_size

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # 1. Inicializar upload
    init_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": titulo[:150],
                "privacy_level": privacidade,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    data = init_resp.json()["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]

    # 2. Upload binário
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = requests.put(
        upload_url,
        data=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            "Content-Length": str(video_size),
        },
        timeout=120,
    )
    upload_resp.raise_for_status()

    print(f"[TikTok] Publicado: publish_id={publish_id}")
    return publish_id
