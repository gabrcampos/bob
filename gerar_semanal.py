#!/usr/bin/env python3
"""
Script de geração semanal de posts.
Executado automaticamente pelo cloud agent toda segunda-feira.
NÃO publica — apenas gera, revisa e manda pro Telegram para aprovação.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modulos.db import col_conteudos, buscar_empresa
from gerar_post import gerar_e_subir
from modulos import gerador_imagens
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

BOT   = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")


def temas_recentes(empresa_id: str, n: int = 8) -> list[str]:
    docs = list(col_conteudos().find(
        {"empresa_id": empresa_id}, {"tema": 1}
    ).sort("criado_em", -1).limit(n))
    return [d.get("tema", "") for d in docs]


def telegram_msg(texto: str):
    requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",
        data={"chat_id": CHAT, "text": texto})


def telegram_pdf(pdf_path: Path, caption: str):
    with open(pdf_path, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendDocument",
            data={"chat_id": CHAT, "caption": caption[:1024]},
            files={"document": f})


def listar_imagens_por_tipo(empresa_id: str, tipo: str, stem: str) -> list[Path]:
    if tipo == "carrossel_tweet":
        return gerador_imagens.listar_imagens_tweet(empresa_id, stem)
    elif tipo == "carrossel_misto_dd":
        return gerador_imagens.listar_imagens_misto_dd(empresa_id, stem)
    return gerador_imagens.listar_imagens(empresa_id, stem)


def gerar_post_semanal(empresa_id: str, tipo: str, tema: str, logo_index: int = 1) -> dict:
    """Gera post, sobe pro Drive e retorna info para revisão."""
    print(f"\n{'='*60}")
    print(f"Gerando: {empresa_id} / {tipo}")
    print(f"Tema: {tema}")
    print(f"{'='*60}")

    conteudo_id, stem, drive_link = gerar_e_subir(
        empresa_id=empresa_id,
        tipo=tipo,
        tema=tema,
        logo_index=logo_index,
    )

    emp = buscar_empresa(empresa_id)
    imagens = listar_imagens_por_tipo(empresa_id, tipo, stem)
    pdf_path = Path(f"outputs/{empresa_id}/{stem}.pdf")

    return {
        "empresa_id": empresa_id,
        "tipo": tipo,
        "tema": tema,
        "conteudo_id": conteudo_id,
        "stem": stem,
        "drive_link": drive_link,
        "imagens": imagens,
        "pdf_path": pdf_path,
        "empresa_nome": emp.get("nome", empresa_id),
    }


if __name__ == "__main__":
    # Temas são passados como argumento ou devem ser definidos pelo agente
    if len(sys.argv) >= 3:
        tema_ts = sys.argv[1]
        tema_dd = sys.argv[2]
    else:
        print("Uso: python3 gerar_semanal.py \"<tema_ts>\" \"<tema_dd>\"")
        sys.exit(1)

    resultados = []

    ts = gerar_post_semanal("tecnosolve", "carrossel_tweet", tema_ts, logo_index=2)
    resultados.append(ts)

    dd = gerar_post_semanal("deliverydash", "carrossel_misto_dd", tema_dd, logo_index=1)
    resultados.append(dd)

    # Sinalizar para o agente que os posts estão prontos para revisão visual
    print("\n[Semanal] Posts gerados. Iniciando revisão visual...")
    for r in resultados:
        print(f"\n{r['empresa_nome']} ({r['tipo']}):")
        for img in r["imagens"]:
            print(f"  {img}")
        print(f"  PDF: {r['pdf_path']}")
        print(f"  Drive: {r['drive_link']}")
