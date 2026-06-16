"""
Download de vídeos de perfis públicos do Instagram via instaloader.
"""

from datetime import datetime, timezone
from pathlib import Path


def listar_videos_perfil(
    perfil: str,
    desde: datetime,
    destino: Path,
) -> list[dict]:
    """
    Retorna metadados de todos os vídeos do perfil desde `desde`,
    ordenados por visualizações decrescente.
    Não baixa o arquivo — só coleta metadados.
    """
    import instaloader

    loader = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    profile = instaloader.Profile.from_username(loader.context, perfil)
    desde_utc = desde.replace(tzinfo=timezone.utc) if desde.tzinfo is None else desde

    videos = []
    print(f"[Instagram] Varrendo @{perfil}... (pode demorar)")
    for post in profile.get_posts():
        if post.date_utc < desde_utc:
            break
        if not post.is_video:
            continue
        videos.append({
            "shortcode":  post.shortcode,
            "views":      post.video_view_count or 0,
            "caption":    post.caption or "",
            "data_post":  post.date_utc,
            "video_url":  post.video_url,
            "filename":   f"{post.date_utc.strftime('%Y%m%d')}_{post.shortcode}.mp4",
            "local_path": destino / f"{post.date_utc.strftime('%Y%m%d')}_{post.shortcode}.mp4",
        })

    videos.sort(key=lambda v: v["views"], reverse=True)
    print(f"[Instagram] {len(videos)} vídeos encontrados desde {desde.date()}.")
    return videos


def baixar_video(video: dict) -> Path:
    """Baixa um único vídeo já listado por `listar_videos_perfil`."""
    import requests

    path: Path = video["local_path"]
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(video["video_url"], stream=True, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)
    return path
