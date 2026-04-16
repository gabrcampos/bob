"""
Geração de Google Docs com posts LinkedIn e narrações de vídeo.
Reutiliza o mesmo token OAuth do drive.py (token precisa ter o scope documents).
"""

from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from modulos import db

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]

_TOKEN_FILE    = Path("config/drive_token.json")
_CLIENT_SECRET = Path("config/oauth_client.json")


def _get_services():
    """Retorna (docs_service, drive_service) usando o token salvo."""
    if not _TOKEN_FILE.exists():
        raise RuntimeError(
            "Autenticação Google não encontrada. "
            "Clique em 'Autenticar com Google' na barra lateral."
        )
    creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                "Token expirado. Re-autentique pelo botão na barra lateral."
            )
    docs_svc  = build("docs",  "v1", credentials=creds, cache_discovery=False)
    drive_svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    return docs_svc, drive_svc


def _formatar_conteudos(empresa_nome: str, conteudos: list[dict]) -> str:
    """Monta o texto completo do documento."""
    linhas = []
    linhas.append(f"{empresa_nome}")
    linhas.append(f"Posts LinkedIn e Narração de Vídeo")
    linhas.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("")

    teve_conteudo = False
    for doc in conteudos:
        post_li   = (doc.get("post_linkedin") or "").strip()
        narracao  = (doc.get("narracao_video") or "").strip()
        if not post_li and not narracao:
            continue

        teve_conteudo = True
        tema = doc.get("tema", "—")
        data = doc["criado_em"].strftime("%d/%m/%Y") if doc.get("criado_em") else "—"
        tipo = doc.get("tipo", "")

        linhas.append("─" * 60)
        linhas.append(f"TEMA: {tema}")
        linhas.append(f"Tipo: {tipo}  |  Data: {data}")
        linhas.append("")

        if post_li:
            linhas.append("POST LINKEDIN:")
            linhas.append(post_li)
            linhas.append("")

        if narracao:
            linhas.append("NARRAÇÃO DE VÍDEO:")
            linhas.append(narracao)
            linhas.append("")

    if not teve_conteudo:
        linhas.append("Nenhum post LinkedIn ou narração de vídeo encontrados.")

    return "\n".join(linhas)


def criar_doc_posts(empresa_id: str, empresa_nome: str, folder_id: str | None = None) -> tuple[str, str]:
    """
    Busca todos os conteúdos da empresa que tenham post_linkedin ou narracao_video,
    cria um Google Doc formatado e retorna (doc_id, doc_url).

    Se folder_id for fornecido, move o doc para aquela pasta do Drive.
    """
    docs_svc, drive_svc = _get_services()

    # Busca conteúdos com texto de LinkedIn ou vídeo
    todos = db.listar_conteudos(empresa_id, limit=200)
    conteudos = [
        d for d in todos
        if (d.get("post_linkedin") or "").strip() or (d.get("narracao_video") or "").strip()
    ]

    titulo = f"{empresa_nome} — Posts LinkedIn e Narração — {datetime.now().strftime('%d/%m/%Y')}"

    # Cria o documento
    doc = docs_svc.documents().create(body={"title": titulo}).execute()
    doc_id = doc["documentId"]

    # Popula com o conteúdo
    texto = _formatar_conteudos(empresa_nome, conteudos)
    docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": texto}}]},
    ).execute()

    # Move para a pasta do Drive se fornecida
    if folder_id:
        file_meta = drive_svc.files().get(fileId=doc_id, fields="parents").execute()
        parents_atuais = ",".join(file_meta.get("parents", []))
        drive_svc.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents=parents_atuais,
            supportsAllDrives=True,
            fields="id, parents",
        ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[Docs] Documento criado: {titulo} — {doc_url}")
    return doc_id, doc_url


def _formatar_conteudo_individual(empresa_nome: str, doc: dict) -> str:
    """Monta o texto do documento para um único conteúdo."""
    linhas = []
    linhas.append(f"{empresa_nome}")
    
    tipo_label = doc.get("tipo", "").replace("_", " ").title()
    linhas.append(f"{tipo_label}")
    linhas.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("")
    linhas.append("─" * 60)
    linhas.append(f"TEMA: {doc.get('tema', '—')}")
    linhas.append("")

    post_li   = (doc.get("post_linkedin") or "").strip()
    narracao  = (doc.get("narracao_video") or "").strip()
    blog_post = (doc.get("blog") or "").strip()

    if post_li:
        linhas.append("POST LINKEDIN:")
        linhas.append(post_li)
        linhas.append("")
    if narracao:
        linhas.append("NARRAÇÃO DE VÍDEO:")
        linhas.append(narracao)
        linhas.append("")
    if blog_post:
        linhas.append("POST DE BLOG:")
        linhas.append(blog_post)
        linhas.append("")
    if not any([post_li, narracao, blog_post]):
        linhas.append("Nenhum texto encontrado para este conteúdo.")

    return "\n".join(linhas)


def criar_doc_individual(doc_conteudo: dict, folder_id: str) -> tuple[str, str]:
    """Cria um Google Doc para um único conteúdo e o move para a pasta especificada."""
    docs_svc, drive_svc = _get_services()
    empresa_nome = doc_conteudo.get("empresa_nome", "Empresa")
    tema = doc_conteudo.get("tema", "Sem Tema")
    titulo = f"{empresa_nome} — {tema} — {datetime.now().strftime('%d/%m')}"
    doc = docs_svc.documents().create(body={"title": titulo}).execute()
    doc_id = doc["documentId"]
    texto = _formatar_conteudo_individual(empresa_nome, doc_conteudo)
    docs_svc.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": texto}}]}).execute()
    file_meta = drive_svc.files().get(fileId=doc_id, fields="parents").execute()
    parents_atuais = ",".join(file_meta.get("parents", []))
    drive_svc.files().update(fileId=doc_id, addParents=folder_id, removeParents=parents_atuais, supportsAllDrives=True, fields="id, parents").execute()
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[Docs] Documento individual criado: {titulo} — {doc_url}")
    db.atualizar_conteudo(doc_conteudo["_id"], {"status": "ta_no_doc", "doc_link": doc_url})
    return doc_id, doc_url


def criar_doc_carrosseis(empresa_id: str, empresa_nome: str, conteudo: str, folder_id: str | None = None) -> tuple[str, str]:
    """
    Cria um Google Doc com os textos dos carrosseis marcados como 'copy-ok'.
    Retorna (doc_id, doc_url).

    Se folder_id for fornecido, move o doc para aquela pasta do Drive.
    """
    docs_svc, drive_svc = _get_services()

    titulo = f"{empresa_nome} — Textos dos Carrosseis — {datetime.now().strftime('%d/%m/%Y')}"

    # Cria o documento
    doc = docs_svc.documents().create(body={"title": titulo}).execute()
    doc_id = doc["documentId"]

    # Popula com o conteúdo
    docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": conteudo}}]},
    ).execute()

    # Move para a pasta do Drive se fornecida
    if folder_id:
        file_meta = drive_svc.files().get(fileId=doc_id, fields="parents").execute()
        parents_atuais = ",".join(file_meta.get("parents", []))
        drive_svc.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents=parents_atuais,
            supportsAllDrives=True,
            fields="id, parents",
        ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[Docs] Documento de carrosseis criado: {titulo} — {doc_url}")
    return doc_id, doc_url
