"""
Operações de vídeo no Google Cloud Storage.
Requer: google-cloud-storage, GOOGLE_APPLICATION_CREDENTIALS ou ADC configurado.
"""

import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "bob-videos-487590427215")


def _client():
    from google.cloud import storage
    return storage.Client()


def upload_video(local_path: str | Path, empresa_id: str, filename: str | None = None) -> str:
    """Faz upload de um vídeo para o GCS. Retorna o URI gs://."""
    client = _client()
    bucket = client.bucket(BUCKET_NAME)
    local_path = Path(local_path)
    filename = filename or local_path.name
    blob_name = f"{empresa_id}/videos/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path), content_type="video/mp4")
    gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
    print(f"[GCS] Upload concluído: {gcs_uri}")
    return gcs_uri


def download_video(gcs_uri: str, destino: str | Path) -> Path:
    """Baixa um vídeo do GCS para um path local. Retorna o Path do arquivo."""
    sem_prefixo = gcs_uri.removeprefix("gs://")
    bucket_name, blob_name = sem_prefixo.split("/", 1)
    client = _client()
    blob = client.bucket(bucket_name).blob(blob_name)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(destino))
    print(f"[GCS] Download concluído: {destino}")
    return destino


def delete_video(gcs_uri: str):
    """Remove um vídeo do GCS."""
    sem_prefixo = gcs_uri.removeprefix("gs://")
    bucket_name, blob_name = sem_prefixo.split("/", 1)
    _client().bucket(bucket_name).blob(blob_name).delete()
    print(f"[GCS] Removido: {gcs_uri}")


def url_publica(gcs_uri: str, expiracao_horas: int = 1) -> str:
    """Gera uma URL assinada temporária para download do vídeo."""
    sem_prefixo = gcs_uri.removeprefix("gs://")
    bucket_name, blob_name = sem_prefixo.split("/", 1)
    client = _client()
    blob = client.bucket(bucket_name).blob(blob_name)
    return blob.generate_signed_url(
        expiration=timedelta(hours=expiracao_horas),
        method="GET",
    )
