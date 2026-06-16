"""
Roda no servidor: varre o perfil do Instagram, seleciona os próximos
vídeos a agendar e salva um JSON para o PC local processar.

Uso:
    python rotina_listar.py --perfil <handle>

Saída:
    lista_<handle>.json  — lista de vídeos com URL e horário de postagem
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SLOTS_UTC = [10, 15, 20, 0]
POSTS_POR_DIA = len(SLOTS_UTC)


def proximos_slots(a_partir: datetime, quantidade: int) -> list[datetime]:
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
    parser.add_argument("--perfil", required=True, help="Handle do Instagram (sem @)")
    parser.add_argument("--empresa", default=None, help="empresa_id (padrão: mesmo que --perfil)")
    parser.add_argument("--desde",  default="2023-07-29", help="Data de corte YYYY-MM-DD")
    parser.add_argument("--dias",   type=int, default=7, help="Dias de conteúdo a selecionar (padrão: 7)")
    args = parser.parse_args()

    empresa_id = args.empresa or args.perfil
    desde = datetime.strptime(args.desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    limite = args.dias * POSTS_POR_DIA
    destino = Path("outputs/instagram") / args.perfil

    from modulos.instagram import listar_videos_perfil
    from modulos.db import ja_agendado

    videos = listar_videos_perfil(args.perfil, desde, destino)
    if not videos:
        print("Nenhum vídeo encontrado.")
        sys.exit(0)

    novos = [v for v in videos if not ja_agendado(v["shortcode"])][:limite]
    print(f"[Listar] {len(novos)} vídeos selecionados para os próximos {args.dias} dias.")

    if not novos:
        print("Nada a fazer.")
        sys.exit(0)

    agora_utc = datetime.now(timezone.utc)
    slots = proximos_slots(agora_utc, len(novos))

    lista = []
    for video, slot in zip(novos, slots):
        titulo = video["caption"].split("\n")[0][:100] if video["caption"] else video["shortcode"]
        lista.append({
            "shortcode":  video["shortcode"],
            "views":      video["views"],
            "titulo":     titulo,
            "video_url":  video["video_url"],
            "filename":   video["filename"],
            "empresa_id": empresa_id,
            "slot":       slot.isoformat(),
        })
        print(f"  {video['shortcode']} | {video['views']:>10,} views → {slot.strftime('%d/%m %H:%M')} UTC")

    saida = Path(f"lista_{args.perfil}.json")
    saida.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Listar] Salvo em: {saida}")
    print(f"         Copie para o PC local e rode:")
    print(f"         python rotina_instagram_youtube.py --lista {saida}")


if __name__ == "__main__":
    main()
