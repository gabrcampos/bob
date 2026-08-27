"""
Baixa vídeos do @doisbe.tv e envia para uma pasta do Google Drive.
Lembra quais já foram baixados (config/doisbe_estado.json) e continua de onde parou.
Exporta as legendas em legendas_<data>.txt na mesma pasta do Drive.

Uso:
    python3 baixar_doisbe_drive.py                     # próximos 14 não baixados
    python3 baixar_doisbe_drive.py --dry-run           # lista sem baixar
    python3 baixar_doisbe_drive.py --pasta-id <ID>     # usa pasta existente
    python3 baixar_doisbe_drive.py --limite 20         # outro limite
"""

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

PERFIL = "doisbe.tv"
USER_ID = "77425940729"
COOKIES = "cookies.txt"
ESTADO = Path("config/doisbe_estado.json")
DESDE = datetime(2025, 10, 11, tzinfo=timezone.utc)
CORTE = datetime(2026, 7, 22, tzinfo=timezone.utc)


def _carregar_estado() -> set[str]:
    if ESTADO.exists():
        return set(json.loads(ESTADO.read_text())["baixados"])
    return set()


def _salvar_estado(baixados: set[str]):
    ESTADO.write_text(json.dumps({"baixados": sorted(baixados)}, ensure_ascii=False, indent=2))


def _drive_client():
    import googleapiclient.discovery
    from google.oauth2.credentials import Credentials
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
    return googleapiclient.discovery.build("drive", "v3", credentials=Credentials(token=token),
                                           cache_discovery=False)


def _criar_pasta(drive, nome: str) -> str:
    pasta = drive.files().create(
        body={"name": nome, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return pasta["id"]


def _upload(drive, local_path: Path, filename: str, folder_id: str) -> str:
    from googleapiclient.http import MediaFileUpload
    mimetype = "text/plain" if filename.endswith(".txt") else "video/mp4"
    media = MediaFileUpload(str(local_path), mimetype=mimetype, resumable=True)
    arquivo = drive.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id,webViewLink",
    ).execute()
    return arquivo.get("webViewLink", arquivo["id"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta-id", default=None, help="ID de pasta existente no Drive (cria nova se omitido)")
    parser.add_argument("--limite", type=int, default=14, help="Máximo de vídeos a enviar (padrão: 14)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from modulos.instagram import listar_videos_perfil, baixar_video

    ja_baixados = _carregar_estado()
    print(f"[Estado] {len(ja_baixados)} vídeo(s) já baixados anteriormente.")

    print(f"\n[1/3] Buscando vídeos de @{PERFIL} de {DESDE.strftime('%d/%m/%Y')} até {CORTE.strftime('%d/%m/%Y')}...")
    with tempfile.TemporaryDirectory() as tmp:
        videos = listar_videos_perfil(
            perfil=PERFIL,
            desde=DESDE,
            destino=Path(tmp),
            cookies=COOKIES,
            user_id=USER_ID,
        )

    # filtra intervalo, exclui já baixados, ordena por data e limita
    videos = [v for v in videos if v["data_post"] < CORTE and v["shortcode"] not in ja_baixados]
    videos.sort(key=lambda v: v["data_post"])
    videos = videos[:args.limite]

    if not videos:
        print("Nenhum vídeo novo encontrado no intervalo.")
        return

    print(f"\nPróximos {len(videos)} vídeos a baixar:")
    for v in videos:
        print(f"  {v['filename']}  ({v.get('views', 0):,} views)")

    if args.dry_run:
        return

    drive = _drive_client()

    if args.pasta_id:
        pasta_id = args.pasta_id
    else:
        nome_pasta = f"Videos doisbe.tv - {datetime.now().strftime('%Y-%m-%d')}"
        pasta_id = _criar_pasta(drive, nome_pasta)
        print(f"\nPasta criada: '{nome_pasta}'")
        print(f"https://drive.google.com/drive/folders/{pasta_id}")

    print(f"\n[2/3] Baixando e enviando para Drive...")
    print(f"      Pasta: https://drive.google.com/drive/folders/{pasta_id}\n")

    ok = erros = 0
    enviados = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, v in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}] {v['filename']}  ({v.get('views', 0):,} views)")
            local = Path(tmp) / v["filename"]
            v["local_path"] = local
            try:
                baixar_video(v, cookies=COOKIES)
                link = _upload(drive, local, v["filename"], pasta_id)
                print(f"  ✓  {link}")
                ok += 1
                enviados.append(v)
                ja_baixados.add(v["shortcode"])
                _salvar_estado(ja_baixados)
            except Exception as e:
                print(f"  ✗  {e}")
                erros += 1

        # gera e envia arquivo de legendas
        if enviados:
            print(f"\n[3/3] Exportando legendas...")
            nome_legendas = f"legendas_{datetime.now().strftime('%Y-%m-%d')}.txt"
            arquivo_legendas = Path(tmp) / nome_legendas
            linhas = []
            for v in enviados:
                linhas.append(f"=== {v['filename']} ===")
                linhas.append(v.get("caption", "").strip() or "(sem legenda)")
                linhas.append("")
            arquivo_legendas.write_text("\n".join(linhas), encoding="utf-8")
            link_legendas = _upload(drive, arquivo_legendas, nome_legendas, pasta_id)
            print(f"  ✓  {link_legendas}")

    print(f"\n{'='*50}")
    print(f"Concluído: {ok} vídeos enviados, {erros} erros.")
    print(f"Pasta: https://drive.google.com/drive/folders/{pasta_id}")


if __name__ == "__main__":
    main()
