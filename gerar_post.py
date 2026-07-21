#!/usr/bin/env python3
"""
Gera carrossel para uma empresa e sobe para o Drive.
Uso: python3 gerar_post.py <empresa_id> <tipo> "<tema>"

Tipos: carrossel | carrossel_misto_dd | carrossel_tweet | carrossel_oldschool
"""
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, "/home/campos_1122/bob")

from modulos.db import buscar_empresa, salvar_conteudo, atualizar_conteudo, buscar_conteudo
from modulos import llm_brain, gerador_imagens
from googleapiclient.http import MediaFileUpload


def _drive_client():
    from google.oauth2.credentials import Credentials
    import googleapiclient.discovery

    # Tenta refresh_token do youtube_token.json primeiro
    try:
        with open("config/youtube_token.json") as f:
            yt = json.load(f)
        creds = Credentials(
            token=None, refresh_token=yt["refresh_token"], token_uri=yt["token_uri"],
            client_id=yt["client_id"], client_secret=yt["client_secret"],
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        # Força refresh imediato para detectar token inválido antes de usar
        import google.auth.transport.requests
        creds.refresh(google.auth.transport.requests.Request())
        return googleapiclient.discovery.build("drive", "v3", credentials=creds)
    except Exception:
        # Fallback: gcloud auth (disponível localmente)
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
        return googleapiclient.discovery.build("drive", "v3", credentials=Credentials(token=token))


# Logo index padrão por (empresa_id, tipo) — sobrepõe qualquer valor passado externamente
_LOGO_INDEX_FIXO = {
    ("tecnosolve", "carrossel_tweet"): 2,
}

def gerar_e_subir(empresa_id: str, tipo: str, tema: str, logo_index: int = 1):
    # Aplica regra fixa de logo antes de qualquer outra lógica
    logo_index = _LOGO_INDEX_FIXO.get((empresa_id, tipo), logo_index)

    emp = buscar_empresa(empresa_id)
    if not emp:
        raise ValueError(f"Empresa '{empresa_id}' não encontrada")

    # Identidade visual completa (igual ao app.py)
    iv = {
        **emp.get("identidade_visual", {}),
        "estilo_imagem": emp.get("estilo_imagem", ""),
        "url_site": emp.get("url_site", ""),
    }

    # ── 1. Gerar conteúdo via LLM ──────────────────────────────
    print(f"[1/4] Gerando conteúdo: '{tema}' ({emp['nome']})")
    if tipo == "carrossel_misto_dd":
        raw = llm_brain.gerar_carrossel_misto_dd(
            tema=tema, empresa=emp["nome"], empresa_id=empresa_id,
            publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""),
        )
    elif tipo == "carrossel_tweet":
        raw = llm_brain.gerar_carrossel_tweet(
            tema=tema, empresa=emp["nome"], empresa_id=empresa_id,
            publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""),
        )
    elif tipo == "carrossel_oldschool":
        raw = llm_brain.gerar_carrossel_oldschool(
            tema=tema, empresa=emp["nome"], empresa_id=empresa_id,
            publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""),
        )
    else:
        raw = llm_brain.gerar_conteudo(
            tema=tema, empresa=emp["nome"], empresa_id=empresa_id,
            publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""),
        )

    slides = raw.get("slides") or raw.get("carrossel") or []
    print(f"   {len(slides)} slides gerados")

    conteudo_id = salvar_conteudo(
        empresa_id=empresa_id,
        empresa_nome=emp["nome"],
        tipo=tipo,
        tema=tema,
        slides=slides,
        legenda=raw.get("legenda", ""),
        post_linkedin=raw.get("post_linkedin", ""),
        narracao_video=raw.get("narracao_video", ""),
        publico_alvo=emp["publico_alvo"],
    )
    doc = buscar_conteudo(conteudo_id)
    stem = doc["stem"]
    print(f"   Salvo: {conteudo_id} | stem: {stem}")

    # ── 2. Gerar imagens ───────────────────────────────────────
    print(f"[2/4] Gerando imagens...")

    def prog(i, total):
        print(f"   [{i}/{total}]")

    if tipo == "carrossel_misto_dd":
        gerador_imagens.gerar_imagens_carrossel_misto_dd(
            slides=slides, empresa_id=empresa_id, empresa_nome=emp["nome"],
            stem=stem, identidade_visual=iv, logo_index=logo_index, callback=prog,
        )
        imagens = gerador_imagens.listar_imagens_misto_dd(empresa_id, stem)
    elif tipo == "carrossel_tweet":
        cor_hex = (iv.get("primarias") or [{}])[0].get("hex", "#000000")
        gerador_imagens.gerar_imagens_carrossel_tweet(
            slides=slides, empresa_id=empresa_id, empresa_nome=emp["nome"],
            stem=stem, identidade_visual=iv, logo_index=logo_index,
            cor_circulo_hex=cor_hex, callback=prog,
        )
        imagens = gerador_imagens.listar_imagens_tweet(empresa_id, stem)
    elif tipo == "carrossel_oldschool":
        gerador_imagens.gerar_imagens_carrossel_oldschool(
            slides=slides, empresa_id=empresa_id, stem=stem,
            identidade_visual=iv, logo_index=logo_index, callback=prog,
        )
        imagens = gerador_imagens.listar_imagens_oldschool(empresa_id, stem)
    else:
        gerador_imagens.gerar_imagens_carrossel(
            slides=slides, empresa_id=empresa_id, stem=stem,
            identidade_visual=iv, logo_index=logo_index, callback=prog,
        )
        imagens = gerador_imagens.listar_imagens(empresa_id, stem)

    print(f"   {len(imagens)} imagens geradas")

    # ── 3. Gerar PDF ───────────────────────────────────────────
    print("[3/4] Gerando PDF...")
    pdf_bytes = gerador_imagens.imagens_para_pdf(imagens)
    pdf_path = Path(f"outputs/{empresa_id}/{stem}.pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    print(f"   {pdf_path}")

    # ── 4. Upload para Drive ────────────────────────────────────
    print("[4/4] Subindo para Drive...")
    folder_id = emp.get("drive_folder_id")
    if not folder_id:
        print("   AVISO: drive_folder_id não configurado — pulando upload")
        return conteudo_id, stem, None

    drive = _drive_client()
    pasta = drive.files().create(body={
        "name": tema[:60],
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [folder_id],
    }, fields="id").execute()
    sub_id = pasta["id"]

    for img in imagens:
        media = MediaFileUpload(str(img), mimetype="image/png")
        drive.files().create(
            body={"name": img.name, "parents": [sub_id]},
            media_body=media, fields="id",
        ).execute()

    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf")
    drive.files().create(
        body={"name": pdf_path.name, "parents": [sub_id]},
        media_body=media, fields="id",
    ).execute()

    drive_link = f"https://drive.google.com/drive/folders/{sub_id}"
    atualizar_conteudo(conteudo_id, {"status": "no_drive", "drive_link": drive_link})
    print(f"   {drive_link}")

    return conteudo_id, stem, drive_link


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python3 gerar_post.py <empresa_id> <tipo> \"<tema>\"")
        sys.exit(1)

    _empresa_id = sys.argv[1]
    _tipo = sys.argv[2]
    _tema = sys.argv[3]

    _cid, _stem, _link = gerar_e_subir(_empresa_id, _tipo, _tema)
    print(f"\n✓ conteudo_id: {_cid}")
    if _link:
        print(f"✓ Drive: {_link}")
