"""
Baixa vídeos do GCS e sobe para o Google Drive.

Uso:
    # Baixar os vídeos com erro (doisbe) e salvar no Drive:
    python3 salvar_videos_drive.py

    # Especificar pasta destino no Drive:
    python3 salvar_videos_drive.py --pasta-id <FOLDER_ID>

    # Incluir também vídeos de outra empresa:
    python3 salvar_videos_drive.py --empresa fs_negao

    # Baixar TODOS (doisbe + fs_negao):
    python3 salvar_videos_drive.py --todos
"""

import argparse
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

BUCKET = "bob-videos-487590427215"


def _drive_client():
    import googleapiclient.discovery
    from google.oauth2.credentials import Credentials
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
    return googleapiclient.discovery.build("drive", "v3", credentials=Credentials(token=token))


def _criar_pasta(drive, nome: str, parent_id: str | None = None) -> str:
    meta = {
        "name": nome,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]
    pasta = drive.files().create(body=meta, fields="id").execute()
    return pasta["id"]


def listar_videos_gcs(empresa: str | None = None) -> list[dict]:
    from google.cloud import storage
    client = storage.Client.from_service_account_json("config/service_account.json")
    blobs = client.list_blobs(BUCKET)
    videos = []
    for b in blobs:
        if not b.name.endswith(".mp4"):
            continue
        partes = b.name.split("/")
        emp = partes[0]
        if empresa and emp != empresa:
            continue
        videos.append({
            "gcs_uri": f"gs://{BUCKET}/{b.name}",
            "blob_name": b.name,
            "filename": partes[-1],
            "empresa": emp,
            "size_mb": round(b.size / 1024 / 1024, 1),
        })
    return videos


def baixar_e_subir(videos: list[dict], pasta_drive_id: str, drive):
    from modulos.cloud_storage import download_video
    from googleapiclient.http import MediaFileUpload

    print(f"\n[Drive] Destino: https://drive.google.com/drive/folders/{pasta_drive_id}")
    print(f"[GCS→Drive] {len(videos)} vídeo(s) para transferir\n")

    ok = 0
    erros = 0

    with tempfile.TemporaryDirectory() as tmp:
        for i, v in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}] {v['filename']} ({v['size_mb']}MB) [{v['empresa']}]")

            local = Path(tmp) / v["filename"]
            try:
                download_video(v["gcs_uri"], local)
            except Exception as e:
                print(f"  ✗ Erro no download do GCS: {e}")
                erros += 1
                continue

            try:
                media = MediaFileUpload(str(local), mimetype="video/mp4", resumable=True)
                arquivo = drive.files().create(
                    body={"name": v["filename"], "parents": [pasta_drive_id]},
                    media_body=media,
                    fields="id,webViewLink",
                ).execute()
                print(f"  ✓ Drive: {arquivo.get('webViewLink', arquivo['id'])}")
                ok += 1
            except Exception as e:
                print(f"  ✗ Erro no upload para Drive: {e}")
                erros += 1

    print(f"\n{'='*50}")
    print(f"Concluído: {ok} enviados, {erros} erros.")
    print(f"Pasta no Drive: https://drive.google.com/drive/folders/{pasta_drive_id}")
    return ok, erros


def main():
    parser = argparse.ArgumentParser(description="GCS → Google Drive")
    parser.add_argument("--pasta-id", default=None, help="ID da pasta no Drive (cria nova se omitido)")
    parser.add_argument("--empresa", default="doisbe", help="empresa_id no GCS (padrão: doisbe)")
    parser.add_argument("--todos", action="store_true", help="Incluir todas as empresas")
    args = parser.parse_args()

    empresa = None if args.todos else args.empresa
    videos = listar_videos_gcs(empresa)

    if not videos:
        print(f"Nenhum vídeo encontrado no GCS" + (f" para empresa '{empresa}'" if empresa else "") + ".")
        return

    drive = _drive_client()

    if args.pasta_id:
        pasta_id = args.pasta_id
    else:
        nome_pasta = f"Videos {empresa or 'Todos'} - {datetime.now().strftime('%Y-%m-%d')}"
        pasta_id = _criar_pasta(drive, nome_pasta)
        print(f"[Drive] Pasta criada: '{nome_pasta}'")

    baixar_e_subir(videos, pasta_id, drive)


if __name__ == "__main__":
    main()
