import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]

_CLIENT_SECRET = Path("config/oauth_client.json")
_TOKEN_FILE    = Path("config/drive_token.json")


def _get_service():
    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CLIENT_SECRET.exists():
                raise FileNotFoundError(
                    f"Arquivo '{_CLIENT_SECRET}' não encontrado. "
                    "Baixe o OAuth 2.0 Client ID (Desktop app) no Google Cloud Console "
                    "e salve como config/oauth_client.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)

        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def esta_autenticado() -> bool:
    """Retorna True se já existe token válido salvo."""
    if not _TOKEN_FILE.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            return True
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def autenticar() -> bool:
    """Abre o fluxo OAuth no navegador. Retorna True se bem-sucedido."""
    if not _CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f"Arquivo '{_CLIENT_SECRET}' não encontrado. "
            "Baixe o OAuth 2.0 Client ID (Desktop app) no Google Cloud Console "
            "e salve como config/oauth_client.json."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return True


def _proximo_numero(service, parent_id: str) -> str:
    """Lista subpastas numéricas em parent_id e retorna o próximo número com zero-padding."""
    query = (
        f"'{parent_id}' in parents"
        " and mimeType = 'application/vnd.google-apps.folder'"
        " and trashed = false"
    )

    numeros = []
    page_token = None
    while True:
        kwargs = dict(
            q=query,
            fields="nextPageToken, files(name)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        resultado = service.files().list(**kwargs).execute()

        for item in resultado.get("files", []):
            try:
                numeros.append(int(item["name"]))
            except ValueError:
                pass

        page_token = resultado.get("nextPageToken")
        if not page_token:
            break

    proximo = max(numeros) + 1 if numeros else 0
    largura = max(len(str(max(numeros))) if numeros else 0, 2)
    return str(proximo).zfill(largura)


def _criar_pasta(service, nome: str, parent_id: str) -> str:
    """Cria uma subpasta e retorna seu ID."""
    metadata = {
        "name": nome,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    pasta = service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    return pasta["id"]


def enviar_carrossel_drive(imagens: list[Path], folder_id: str) -> tuple[list[dict], str]:
    """
    Cria uma subpasta numerada (00, 01, 02…) dentro de folder_id
    e envia as imagens nomeadas 1.png, 2.png, ...
    Retorna (lista de dicts com 'name' e 'url', nome da pasta criada).
    """
    if not folder_id:
        raise ValueError(
            "ID da pasta do Google Drive não configurado. "
            "Adicione o ID na aba Empresas."
        )

    service = _get_service()

    nome_pasta = _proximo_numero(service, folder_id)
    subfolder_id = _criar_pasta(service, nome_pasta, folder_id)
    print(f"[Drive] Pasta criada: {nome_pasta} (id={subfolder_id})")

    resultados = []
    for idx, img_path in enumerate(imagens):
        nome_arquivo = f"{idx + 1}.png"
        metadata = {"name": nome_arquivo, "parents": [subfolder_id]}
        media = MediaFileUpload(str(img_path), mimetype="image/png", resumable=True)
        arquivo = (
            service.files()
            .create(body=metadata, media_body=media, fields="id,webViewLink,name",
                    supportsAllDrives=True)
            .execute()
        )
        print(f"[Drive] Enviado: {nome_pasta}/{nome_arquivo}")
        resultados.append({
            "name": arquivo.get("name"),
            "url": arquivo.get("webViewLink", ""),
        })

    folder_link = f"https://drive.google.com/drive/folders/{subfolder_id}"
    return resultados, nome_pasta, folder_link
