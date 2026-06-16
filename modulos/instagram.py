"""
Download de vídeos de perfis do Instagram via gallery-dl.
Usa cookies.txt exportado do browser para autenticação.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _gallery_dl_cmd(cookies: str | None) -> list[str]:
    cmd = ["gallery-dl"]
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", cookies]
    return cmd


def listar_videos_perfil(
    perfil: str,
    desde: datetime,
    destino: Path,
    usuario: str | None = None,
    cookies: str | None = None,
) -> list[dict]:
    """
    Retorna metadados dos vídeos do perfil desde `desde`,
    ordenados por visualizações decrescente.
    """
    desde_utc = desde.replace(tzinfo=timezone.utc) if desde.tzinfo is None else desde

    cmd = _gallery_dl_cmd(cookies) + ["--dump-json", f"https://www.instagram.com/{perfil}/"]
    print(f"[Instagram] Varrendo @{perfil}...")

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(f"gallery-dl falhou:\n{proc.stderr}")

    # Debug: mostrar primeiras linhas do output
    linhas = proc.stdout.strip().splitlines()
    if not linhas:
        print(f"[Debug] Nenhuma saída do gallery-dl. stderr:\n{proc.stderr[:500]}")
    else:
        print(f"[Debug] {len(linhas)} linhas recebidas. Primeira:")
        print(linhas[0][:300])

    videos = []
    for line in linhas:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # gallery-dl retorna listas [version, index, {data}] ou dicts diretos
        if isinstance(data, list):
            data = data[-1] if data else {}
        if not isinstance(data, dict):
            continue

        video_url = data.get("video_url") or data.get("url", "")
        if not video_url or not video_url.endswith(".mp4") and "video" not in video_url:
            continue

        shortcode = data.get("shortcode") or data.get("post_shortcode", "")
        if not shortcode:
            continue

        # Data do post
        raw_date = data.get("date") or data.get("upload_date")
        post_date = None
        if raw_date:
            try:
                if isinstance(raw_date, str) and len(raw_date) == 8:
                    post_date = datetime.strptime(raw_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                elif isinstance(raw_date, (int, float)):
                    post_date = datetime.fromtimestamp(raw_date, tz=timezone.utc)
                elif isinstance(raw_date, str):
                    post_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except Exception:
                pass

        if post_date and post_date < desde_utc:
            continue

        date_prefix = post_date.strftime("%Y%m%d") if post_date else "sem_data"
        filename = f"{date_prefix}_{shortcode}.mp4"

        videos.append({
            "shortcode":  shortcode,
            "views":      data.get("view_count", 0) or data.get("views", 0) or 0,
            "caption":    data.get("description", "") or data.get("caption", "") or "",
            "data_post":  post_date or desde_utc,
            "video_url":  video_url,
            "filename":   filename,
            "local_path": destino / filename,
        })

    videos.sort(key=lambda v: v["views"], reverse=True)
    print(f"[Instagram] {len(videos)} vídeos encontrados desde {desde.date()}.")
    return videos


def baixar_video(video: dict, destino: Path | None = None, cookies: str | None = None) -> Path:
    """Baixa um vídeo usando gallery-dl."""
    if "local_path" in video:
        path = Path(video["local_path"])
    else:
        pasta = destino or Path("outputs/instagram")
        pasta.mkdir(parents=True, exist_ok=True)
        path = pasta / video["filename"]

    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    cmd = _gallery_dl_cmd(cookies) + [
        "--output", str(path.with_suffix("")),
        video["video_url"],
    ]

    subprocess.run(cmd, check=True)

    if not path.exists() and path.with_suffix(".mp4").exists():
        path = path.with_suffix(".mp4")

    return path
