"""
Rotina semanal: baixa vídeos de um perfil público do Instagram,
sobe para o GCS e agenda publicação no YouTube Shorts.

Uso:
    python rotina_instagram_youtube.py --perfil <handle> --empresa <empresa_id>

Opções:
    --perfil    Handle do Instagram sem @ (ex: tecnosolve)
    --empresa   ID da empresa no MongoDB (ex: tecnosolve)
    --desde     Data de corte no formato YYYY-MM-DD (padrão: 2023-07-29)
    --destino   Pasta local para os vídeos baixados (padrão: outputs/instagram)
"""

import argparse
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Horários de postagem no YouTube Shorts — BRT (UTC-3) → UTC
# 7h, 12h, 17h, 21h BRT  =  10h, 15h, 20h, 00h UTC
SLOTS_UTC = [10, 15, 20, 0]  # horas UTC


def proximos_slots(a_partir: datetime, quantidade: int) -> list[datetime]:
    """Gera os próximos `quantidade` slots de postagem a partir de `a_partir`."""
    slots = []
    dia = a_partir.replace(hour=0, minute=0, second=0, microsecond=0)

    while len(slots) < quantidade:
        for hora in SLOTS_UTC:
            candidato = dia.replace(hour=hora)
            if hora == 0:
                candidato += timedelta(days=1)
            if candidato > a_partir:
                slots.append(candidato)
                if len(slots) == quantidade:
                    break
        dia += timedelta(days=1)

    return slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--perfil",  required=True, help="Handle do Instagram (sem @)")
    parser.add_argument("--empresa", default=None,  help="ID para organizar no GCS/MongoDB (padrão: mesmo que --perfil)")
    parser.add_argument("--desde",   default="2023-07-29", help="Data de corte YYYY-MM-DD")
    parser.add_argument("--destino", default="outputs/instagram", help="Pasta local para downloads")
    args = parser.parse_args()

    empresa_id = empresa_id or args.perfil
    desde = datetime.strptime(args.desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    destino = Path(args.destino) / args.perfil
    destino.mkdir(parents=True, exist_ok=True)

    from modulos.instagram import baixar_video, listar_videos_perfil
    from modulos.cloud_storage import upload_video
    from modulos.db import agendar_post, ja_agendado

    # 1. Listar vídeos do Instagram (mais vistos primeiro)
    videos = listar_videos_perfil(args.perfil, desde, destino)
    if not videos:
        print("Nenhum vídeo encontrado. Encerrando.")
        sys.exit(0)

    # 2. Filtrar os que já foram agendados
    novos = [v for v in videos if not ja_agendado(v["shortcode"])]
    print(f"[Rotina] {len(novos)} vídeos novos para agendar (de {len(videos)} encontrados).")
    if not novos:
        print("Nada a fazer.")
        sys.exit(0)

    # 3. Calcular slots a partir de agora
    agora_utc = datetime.now(timezone.utc)
    slots = proximos_slots(agora_utc, len(novos))

    # 4. Processar cada vídeo
    agendados = 0
    erros = 0

    for video, slot in zip(novos, slots):
        shortcode = video["shortcode"]
        print(f"\n[{agendados + erros + 1}/{len(novos)}] {shortcode} ({video['views']:,} views) → {slot.strftime('%d/%m/%Y %H:%M')} UTC")

        try:
            # Baixar
            local_path = baixar_video(video)
            print(f"  ↓ Baixado: {local_path.name}")

            # Upload GCS
            gcs_uri = upload_video(local_path, empresa_id, local_path.name)
            print(f"  ↑ GCS: {gcs_uri}")

            # Agendar
            titulo = (video["caption"].split("\n")[0][:100] if video["caption"] else shortcode)
            agendar_post(
                conteudo_id=shortcode,
                empresa_id=empresa_id,
                plataforma="youtube_shorts",
                data_hora=slot,
                texto=titulo,
                video_path=gcs_uri,
                source_id=shortcode,
            )
            print(f"  ✓ Agendado para {slot.strftime('%d/%m %H:%M')} UTC")
            agendados += 1

            # Apagar local após upload para economizar espaço
            local_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"  ✗ Erro: {e}", file=sys.stderr)
            erros += 1

    print(f"\n{'='*50}")
    print(f"Concluído: {agendados} agendados, {erros} erros.")
    if agendados:
        print(f"Primeiro post: {slots[0].strftime('%d/%m/%Y %H:%M')} UTC")
        print(f"Último post:   {slots[agendados - 1].strftime('%d/%m/%Y %H:%M')} UTC")


if __name__ == "__main__":
    main()
