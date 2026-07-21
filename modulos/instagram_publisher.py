"""
Publicação de carrosséis no Instagram via Instagram Business API (nova, sem Facebook Page).
Documentação: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api
"""

import time
from pathlib import Path

import requests

GRAPH_URL = "https://graph.instagram.com/v21.0"


def _post(endpoint: str, data: dict) -> dict:
    resp = requests.post(f"{GRAPH_URL}/{endpoint}", data=data, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"Instagram API: {result['error'].get('message', result['error'])}")
    return result


def _get(endpoint: str, params: dict) -> dict:
    resp = requests.get(f"{GRAPH_URL}/{endpoint}", params=params, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"Instagram API: {result['error'].get('message', result['error'])}")
    return result


def _criar_container_item(image_url: str, access_token: str) -> str:
    """Cria container para um slide do carrossel. Retorna creation_id."""
    result = _post("me/media", {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": access_token,
    })
    return result["id"]


def _criar_container_carrossel(item_ids: list[str], caption: str, access_token: str) -> str:
    result = _post("me/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
        "access_token": access_token,
    })
    return result["id"]


def _publicar_container(creation_id: str, access_token: str) -> str:
    result = _post("me/media_publish", {
        "creation_id": creation_id,
        "access_token": access_token,
    })
    return result["id"]


def _aguardar_pronto(creation_id: str, access_token: str, tentativas: int = 12, intervalo: int = 5):
    for _ in range(tentativas):
        data = _get(creation_id, {"fields": "status_code", "access_token": access_token})
        status = data.get("status_code", "")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Container {creation_id} em estado ERROR")
        time.sleep(intervalo)
    raise RuntimeError(f"Container {creation_id} não ficou FINISHED após {tentativas} tentativas")


def upload_imagens_para_gcs(imagens: list[Path], empresa_id: str, stem: str) -> list[str]:
    """Faz upload das imagens para GCS e retorna URLs assinadas (1h)."""
    from modulos.cloud_storage import upload_imagem_publica
    urls = []
    for i, img_path in enumerate(imagens):
        blob_name = f"{empresa_id}/carrossel/{stem}/slide_{i+1:02d}{img_path.suffix}"
        url = upload_imagem_publica(img_path, blob_name)
        print(f"  [GCS] slide {i+1}: {blob_name}")
        urls.append(url)
    return urls


def publicar_carrossel_instagram(
    imagens: list[Path],
    caption: str,
    access_token: str,
    empresa_id: str,
    stem: str,
    ig_user_id: str = "",  # mantido por compatibilidade, não usado na nova API
) -> str:
    """
    Publica um carrossel de imagens no Instagram via nova Business API.
    Retorna o media_id do post publicado.
    """
    print(f"[Instagram] Fazendo upload de {len(imagens)} imagens para GCS...")
    image_urls = upload_imagens_para_gcs(imagens, empresa_id, stem)

    print("[Instagram] Criando containers de item...")
    item_ids = []
    for i, url in enumerate(image_urls):
        cid = _criar_container_item(url, access_token)
        print(f"  Slide {i+1}: container_id={cid}")
        item_ids.append(cid)
        time.sleep(1)

    print("[Instagram] Criando container do carrossel...")
    carousel_id = _criar_container_carrossel(item_ids, caption, access_token)
    print(f"  carousel_id={carousel_id}")

    print("[Instagram] Aguardando container ficar pronto...")
    _aguardar_pronto(carousel_id, access_token)

    print("[Instagram] Publicando...")
    media_id = _publicar_container(carousel_id, access_token)
    print(f"[Instagram] Publicado: media_id={media_id}")
    return media_id


def renovar_token_instagram(access_token: str, app_id: str = "", app_secret: str = "") -> str:
    """
    Renova um token de longa duração da nova Instagram Business API.
    Estende por mais 60 dias. Não precisa de app_id/app_secret.
    """
    resp = requests.get(
        f"{GRAPH_URL}/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": access_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Instagram API: {data['error'].get('message', data['error'])}")
    return data["access_token"]


def ig_esta_autenticado(empresa: dict) -> bool:
    ig = empresa.get("instagram", {}) or {}
    return bool(ig.get("ig_user_id") and ig.get("access_token"))


def verificar_token(access_token: str) -> dict:
    """Retorna info do token: id, username, expires_in (segundos)."""
    return _get("me", {"fields": "id,username", "access_token": access_token})
