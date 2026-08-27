"""
Rotina semanal: busca todos os vídeos do perfil @doisbe.tv no Instagram
e agenda publicação na Página do Facebook vinculada.

Os vídeos são agendados em ordem cronológica (mais antigo primeiro),
mantendo a mesma sequência em que foram publicados no Instagram,
com a mesma legenda/descrição original de cada post.

Uso:
    # Gerar lote semanal (rodar toda segunda-feira):
    python3 rotina_doisbe_facebook.py

    # Buscar todos os vídeos sem limite de dias:
    python3 rotina_doisbe_facebook.py --todos

    # Ver o que está agendado para Facebook:
    python3 rotina_doisbe_facebook.py --listar

    # Simular sem agendar no banco:
    python3 rotina_doisbe_facebook.py --dry-run
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PERFIL = "doisbe.tv"
EMPRESA_ID = "doisbe"

# 3 slots/dia em UTC = BRT 9h, 14h, 19h
SLOTS_UTC = [12, 17, 22]
POSTS_POR_DIA = len(SLOTS_UTC)

# Quantos dias de conteúdo por rodada semanal padrão
DIAS_PADRAO = 7


def proximos_slots(a_partir: datetime, quantidade: int) -> list[datetime]:
    slots = []
    dia = a_partir.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(slots) < quantidade:
        for hora in SLOTS_UTC:
            candidato = dia.replace(hour=hora, minute=0, second=0, microsecond=0)
            if candidato > a_partir:
                slots.append(candidato)
                if len(slots) == quantidade:
                    break
        dia += timedelta(days=1)
    return slots


def listar_agendados():
    from modulos.db import listar_agenda
    posts = listar_agenda(plataforma="facebook")
    if not posts:
        print("Nenhum post agendado para Facebook.")
        return
    print(f"\n{'='*60}")
    print(f"{'DATA/HORA UTC':<22} {'STATUS':<12} {'SHORTCODE':<15} {'DESCRIÇÃO'}")
    print(f"{'='*60}")
    for p in posts:
        dt = p.get("data_hora")
        dt_str = dt.strftime("%d/%m/%Y %H:%M") if isinstance(dt, datetime) else str(dt)
        desc = (p.get("texto") or "")[:40]
        print(f"{dt_str:<22} {p.get('status', ''):<12} {p.get('source_id', ''):<15} {desc}")
    print(f"\nTotal: {len(posts)} agendamentos.")


def main():
    parser = argparse.ArgumentParser(description="Rotina @doisbe.tv → Facebook")
    parser.add_argument("--listar", action="store_true", help="Listar agendamentos Facebook no banco")
    parser.add_argument("--todos", action="store_true", help="Buscar todos os vídeos (sem limite de dias)")
    parser.add_argument("--dias", type=int, default=DIAS_PADRAO, help=f"Dias de conteúdo por rodada (padrão: {DIAS_PADRAO})")
    parser.add_argument("--desde", default="2010-01-01", help="Data de corte YYYY-MM-DD para varrer o Instagram")
    parser.add_argument("--cookies", default="cookies.txt", help="Arquivo cookies.txt do browser")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem agendar no banco")
    args = parser.parse_args()

    if args.listar:
        listar_agendados()
        return

    from modulos.instagram import listar_videos_perfil, baixar_video
    from modulos.cloud_storage import upload_video
    from modulos.db import ja_agendado, agendar_post

    destino = Path("outputs/instagram") / PERFIL
    destino.mkdir(parents=True, exist_ok=True)

    cookies = args.cookies if Path(args.cookies).exists() else None
    if not cookies:
        print(f"[Aviso] {args.cookies} não encontrado — tentando sem autenticação.")

    desde = datetime.strptime(args.desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    limite = None if args.todos else args.dias * POSTS_POR_DIA

    print(f"[Rotina] Varrendo @{PERFIL} desde {args.desde}...")
    videos = listar_videos_perfil(PERFIL, desde, destino, cookies=cookies)

    if not videos:
        print("Nenhum vídeo encontrado no Instagram.")
        sys.exit(0)

    # Ordenar por data_post ascendente para replicar sequência do Instagram
    videos.sort(key=lambda v: v["data_post"])

    # Filtrar apenas os não agendados no Facebook
    novos = [v for v in videos if not ja_agendado(v["shortcode"], plataforma="facebook")]
    if limite:
        novos = novos[:limite]

    print(f"[Rotina] {len(videos)} vídeos no perfil | {len(novos)} novos para Facebook" +
          (f" (limite: {limite})" if limite else "") + ".")

    if not novos:
        print("Nada a fazer — todos já agendados.")
        return

    agora_utc = datetime.now(timezone.utc)
    slots = proximos_slots(agora_utc, len(novos))

    print(f"\n{'SHORTCODE':<15} {'DATA_POST':<22} {'SLOT FACEBOOK':<22} LEGENDA")
    print("-" * 90)
    for v, slot in zip(novos, slots):
        data_ig = v["data_post"].strftime("%d/%m/%Y") if v.get("data_post") else "?"
        desc_resumo = (v.get("caption") or "")[:50].replace("\n", " ")
        print(f"  {v['shortcode']:<13} {data_ig:<22} {slot.strftime('%d/%m/%Y %H:%M UTC'):<22} {desc_resumo}")

    if args.dry_run:
        print("\n[Dry-run] Nenhum agendamento criado.")
        return

    print(f"\n[Rotina] Iniciando download + upload + agendamento de {len(novos)} vídeos...")
    agendados = 0
    erros = 0

    for i, (video, slot) in enumerate(zip(novos, slots), 1):
        shortcode = video["shortcode"]
        descricao = video.get("caption") or shortcode
        print(f"\n[{i}/{len(novos)}] {shortcode} ({video.get('views', 0):,} views) → {slot.strftime('%d/%m/%Y %H:%M')} UTC")

        try:
            local_path = baixar_video(video, destino, cookies=cookies)
            print(f"  ↓ Baixado: {local_path.name}")

            gcs_uri = upload_video(local_path, EMPRESA_ID, local_path.name)
            print(f"  ↑ GCS: {gcs_uri}")

            if not args.dry_run:
                agendar_post(
                    conteudo_id=shortcode,
                    empresa_id=EMPRESA_ID,
                    plataforma="facebook",
                    data_hora=slot,
                    texto=descricao,
                    video_path=gcs_uri,
                    source_id=shortcode,
                )
                print(f"  ✓ Agendado para {slot.strftime('%d/%m/%Y %H:%M')} UTC")
                agendados += 1

            local_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"  ✗ Erro em {shortcode}: {e}", file=sys.stderr)
            erros += 1

    print(f"\n{'='*50}")
    print(f"Concluído: {agendados} agendados, {erros} erros.")
    if agendados:
        print(f"Primeiro post: {slots[0].strftime('%d/%m/%Y %H:%M')} UTC")
        print(f"Último post:   {slots[agendados - 1].strftime('%d/%m/%Y %H:%M')} UTC")


if __name__ == "__main__":
    main()
