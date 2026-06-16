"""
Download de vídeos do Instagram via API interna (endpoints mobile/web).
Usa cookies.txt exportado do browser para autenticação.
"""

import http.cookiejar
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
}


def _session(cookies: str | None) -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    if cookies and Path(cookies).exists():
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(cookies, ignore_discard=True, ignore_expires=True)
        for c in jar:
            if "instagram" in c.domain:
                s.cookies.set(c.name, c.value, domain=c.domain)
        print(f"[Instagram] Cookies carregados de {cookies}.")
    else:
        print("[Instagram] Aviso: cookies.txt não encontrado. Tentando sem autenticação.")
    return s


def _user_id(session: requests.Session, perfil: str) -> str:
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={perfil}"
    resp = session.get(url, headers={"Referer": f"https://www.instagram.com/{perfil}/"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["user"]["id"]


def listar_videos_perfil(
    perfil: str,
    desde: datetime,
    destino: Path,
    usuario: str | None = None,
    cookies: str | None = None,
) -> list[dict]:
    desde_utc = desde.replace(tzinfo=timezone.utc) if desde.tzinfo is None else desde
    session = _session(cookies)

    print(f"[Instagram] Buscando user_id de @{perfil}...")
    user_id = _user_id(session, perfil)
    print(f"[Instagram] user_id: {user_id} — varrendo posts...")

    videos = []
    max_id = None
    pagina = 0

    while True:
        pagina += 1
        params: dict = {"count": 50}
        if max_id:
            params["max_id"] = max_id

        resp = session.get(
            f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
            params=params,
            headers={"Referer": f"https://www.instagram.com/{perfil}/"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            break

        parar = False
        for item in items:
            taken_at = item.get("taken_at", 0)
            post_date = datetime.fromtimestamp(taken_at, tz=timezone.utc) if taken_at else None

            if post_date and post_date < desde_utc:
                parar = True
                break

            # media_type: 1=foto, 2=vídeo, 3=clip/reel
            if item.get("media_type") not in (2, 3):
                continue

            code = item.get("code", "")
            video_versions = item.get("video_versions", [])
            if not video_versions:
                continue

            video_url = video_versions[0]["url"]
            caption_obj = item.get("caption") or {}
            caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
            views = item.get("view_count") or item.get("play_count") or 0
            date_prefix = post_date.strftime("%Y%m%d") if post_date else "sem_data"
            filename = f"{date_prefix}_{code}.mp4"

            videos.append({
                "shortcode":  code,
                "views":      views,
                "caption":    caption,
                "data_post":  post_date or desde_utc,
                "video_url":  video_url,
                "filename":   filename,
                "local_path": destino / filename,
            })

        if parar or not data.get("more_available"):
            break

        max_id = data.get("next_max_id")
        if not max_id:
            break

        print(f"[Instagram] Página {pagina}: {len(videos)} vídeos coletados...")
        time.sleep(1.5)

    videos.sort(key=lambda v: v["views"], reverse=True)
    print(f"[Instagram] {len(videos)} vídeos encontrados desde {desde.date()}.")
    return videos


def baixar_video(video: dict, destino: Path | None = None, cookies: str | None = None) -> Path:
    """Baixa o vídeo direto da URL do CDN (não precisa de auth)."""
    if "local_path" in video:
        path = Path(video["local_path"])
    else:
        pasta = destino or Path("outputs/instagram")
        pasta.mkdir(parents=True, exist_ok=True)
        path = pasta / video["filename"]

    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(video["video_url"], stream=True, timeout=60, headers={
        "User-Agent": _HEADERS["User-Agent"],
        "Referer": "https://www.instagram.com/",
    })
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            f.write(chunk)
    return path
