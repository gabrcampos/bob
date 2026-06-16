"""
Download de vídeos de perfis do Instagram via yt-dlp.
Usa cookies do Chrome para autenticação (precisa estar logado no Chrome).
"""

from datetime import datetime, timezone
from pathlib import Path


def _ydl_opts_base(cookies: str | None = None) -> dict:
    opts = {"quiet": True, "no_warnings": True}
    if cookies:
        opts["cookiefile"] = cookies
    else:
        opts["cookiesfrombrowser"] = ("chrome",)
    return opts


def listar_videos_perfil(
    perfil: str,
    desde: datetime,
    destino: Path,
    usuario: str | None = None,
    cookies: str | None = None,
) -> list[dict]:
    """
    Retorna metadados dos vídeos/reels do perfil desde `desde`,
    ordenados por visualizações decrescente.
    """
    import yt_dlp

    desde_utc = desde.replace(tzinfo=timezone.utc) if desde.tzinfo is None else desde

    opts = {
        **_ydl_opts_base(cookies),
        "extract_flat": True,
    }

    url = f"https://www.instagram.com/{perfil}/"
    print(f"[Instagram] Varrendo @{perfil} (usando cookies do Chrome)...")

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries", []) if info else []
    videos = []

    for entry in entries:
        if not entry:
            continue

        upload_date = entry.get("upload_date") or ""
        try:
            post_date = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc) if upload_date else None
        except ValueError:
            post_date = None

        if post_date and post_date < desde_utc:
            continue

        video_id = entry.get("id", "")
        if not video_id:
            continue

        videos.append({
            "shortcode":  video_id,
            "views":      entry.get("view_count", 0) or 0,
            "caption":    entry.get("title", "") or entry.get("description", "") or "",
            "data_post":  post_date or desde_utc,
            "video_url":  f"https://www.instagram.com/reel/{video_id}/",
            "filename":   f"{upload_date or 'sem_data'}_{video_id}.mp4",
            "local_path": destino / f"{upload_date or 'sem_data'}_{video_id}.mp4",
        })

    videos.sort(key=lambda v: v["views"], reverse=True)
    print(f"[Instagram] {len(videos)} vídeos encontrados desde {desde.date()}.")
    return videos


def baixar_video(video: dict, destino: Path | None = None, cookies: str | None = None) -> Path:
    """Baixa um vídeo usando yt-dlp (mais robusto que requests direto)."""
    import yt_dlp

    if "local_path" in video:
        path = Path(video["local_path"])
    else:
        pasta = destino or Path("outputs/instagram")
        pasta.mkdir(parents=True, exist_ok=True)
        path = pasta / video["filename"]

    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    opts = {
        **_ydl_opts_base(cookies),
        "outtmpl": str(path.with_suffix("")),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video["video_url"]])

    # yt-dlp pode adicionar extensão
    if not path.exists() and path.with_suffix(".mp4").exists():
        path = path.with_suffix(".mp4")

    return path
