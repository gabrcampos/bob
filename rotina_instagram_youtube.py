"""
PC local: lê o JSON gerado por rotina_listar.py, baixa os vídeos,
sobe para o GCS e agenda publicação no YouTube Shorts.

Uso:
    python rotina_instagram_youtube.py --lista lista_<handle>.json

Fluxo completo (sem servidor):
    python rotina_instagram_youtube.py --perfil <handle>
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SLOTS_UTC = [10, 15, 20, 0, 3]
POSTS_POR_DIA = len(SLOTS_UTC)
_SLOT_PROX_DIA = {0, 3}  # madrugada — pertencem ao dia seguinte


def proximos_slots(a_partir: datetime, quantidade: int) -> list[datetime]:
    slots = []
    dia = a_partir.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(slots) < quantidade:
        for hora in SLOTS_UTC:
            candidato = dia.replace(hour=hora)
            if hora in _SLOT_PROX_DIA:
                candidato += timedelta(days=1)
            if candidato > a_partir:
                slots.append(candidato)
                if len(slots) == quantidade:
                    break
        dia += timedelta(days=1)
    return slots


def processar(lista: list[dict]):
    from modulos.instagram import baixar_video
    from modulos.cloud_storage import upload_video
    from modulos.db import agendar_post, ja_agendado

    agendados = 0
    erros = 0
    slots_usados = []

    for i, item in enumerate(lista, 1):
        shortcode = item["shortcode"]
        slot = datetime.fromisoformat(item["slot"])
        empresa_id = item["empresa_id"]

        print(f"\n[{i}/{len(lista)}] {shortcode} ({item['views']:,} views) → {slot.strftime('%d/%m/%Y %H:%M')} UTC")

        if ja_agendado(shortcode):
            print("  – já agendado, pulando.")
            continue

        try:
            local_path = baixar_video(item)
            print(f"  ↓ Baixado: {local_path.name}")

            gcs_uri = upload_video(local_path, empresa_id, local_path.name)
            print(f"  ↑ GCS: {gcs_uri}")

            agendar_post(
                conteudo_id=shortcode,
                empresa_id=empresa_id,
                plataforma="youtube_shorts",
                data_hora=slot,
                texto=item["titulo"],
                video_path=gcs_uri,
                source_id=shortcode,
            )
            print(f"  ✓ Agendado para {slot.strftime('%d/%m %H:%M')} UTC")
            agendados += 1
            slots_usados.append(slot)

            local_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"  ✗ Erro: {e}", file=sys.stderr)
            erros += 1

    print(f"\n{'='*50}")
    print(f"Concluído: {agendados} agendados, {erros} erros.")
    if slots_usados:
        print(f"Primeiro post: {slots_usados[0].strftime('%d/%m/%Y %H:%M')} UTC")
        print(f"Último post:   {slots_usados[-1].strftime('%d/%m/%Y %H:%M')} UTC")


def main():
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--lista",   help="JSON gerado por rotina_listar.py (modo recomendado)")
    grupo.add_argument("--perfil",  help="Handle do Instagram — varre e processa tudo localmente")
    parser.add_argument("--usuario", default=None,  help="Seu handle do Instagram para autenticação (sem @)")
    parser.add_argument("--empresa", default=None,  help="empresa_id (padrão: mesmo que --perfil)")
    parser.add_argument("--desde",   default="2023-07-29", help="Data de corte YYYY-MM-DD (só com --perfil)")
    parser.add_argument("--dias",    type=int, default=7, help="Dias de conteúdo por rodada (só com --perfil)")
    parser.add_argument("--destino", default="outputs/instagram", help="Pasta local para downloads")
    args = parser.parse_args()

    if args.lista:
        caminho = Path(args.lista)
        if not caminho.exists():
            print(f"Arquivo não encontrado: {caminho}")
            sys.exit(1)
        lista = json.loads(caminho.read_text(encoding="utf-8"))
        print(f"[Rotina] {len(lista)} vídeos no JSON.")
        processar(lista)

    else:
        from modulos.instagram import listar_videos_perfil
        from modulos.db import ja_agendado

        empresa_id = args.empresa or args.perfil
        desde = datetime.strptime(args.desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        destino = Path(args.destino) / args.perfil
        destino.mkdir(parents=True, exist_ok=True)

        videos = listar_videos_perfil(args.perfil, desde, destino, usuario=args.usuario)
        if not videos:
            print("Nenhum vídeo encontrado.")
            sys.exit(0)

        limite = args.dias * POSTS_POR_DIA
        novos = [v for v in videos if not ja_agendado(v["shortcode"])][:limite]
        print(f"[Rotina] {len(novos)} vídeos novos (limite: {limite}).")
        if not novos:
            print("Nada a fazer.")
            sys.exit(0)

        slots = proximos_slots(datetime.now(timezone.utc), len(novos))
        lista = [
            {
                "shortcode":  v["shortcode"],
                "views":      v["views"],
                "titulo":     v["caption"].split("\n")[0][:100] if v["caption"] else v["shortcode"],
                "video_url":  v["video_url"],
                "filename":   v["filename"],
                "empresa_id": empresa_id,
                "slot":       s.isoformat(),
            }
            for v, s in zip(novos, slots)
        ]
        processar(lista)


if __name__ == "__main__":
    main()
