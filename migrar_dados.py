"""
Script de migração única: popula o MongoDB com dados dos arquivos locais.

Executa:
  1. empresas.json          -> coleção `empresas`
  2. config/contextos/*.md  -> campo `contexto_compilado` em cada empresa
  3. config/historico/*.json -> coleção `historico`

Seguro para rodar mais de uma vez (upsert + checagem de duplicatas).
"""

import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from modulos.db import (
    salvar_empresa,
    salvar_contexto_empresa,
    carregar_contexto_empresa,
    col_historico,
    salvar_entrada_historico,
)

CONFIG_PATH   = Path("config/empresas.json")
CONTEXTOS_DIR = Path("config/contextos")
HISTORICO_DIR = Path("config/historico")


def migrar_empresas():
    if not CONFIG_PATH.exists():
        print("[SKIP] config/empresas.json não encontrado.")
        return
    empresas = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for emp in empresas:
        salvar_empresa(emp)
        print(f"  [OK] Empresa '{emp['nome']}' ({emp['id']}) salva.")
    print(f"-> {len(empresas)} empresa(s) migrada(s).\n")


def migrar_contextos():
    if not CONTEXTOS_DIR.exists():
        print("[SKIP] Pasta config/contextos não encontrada.")
        return
    arquivos = list(CONTEXTOS_DIR.glob("*.md"))
    if not arquivos:
        print("[SKIP] Nenhum arquivo .md em config/contextos.")
        return
    for arq in arquivos:
        empresa_id = arq.stem
        # Só migra se o banco ainda não tiver contexto para essa empresa
        if carregar_contexto_empresa(empresa_id):
            print(f"  [SKIP] Contexto de '{empresa_id}' já existe no banco.")
            continue
        texto = arq.read_text(encoding="utf-8").strip()
        if texto:
            salvar_contexto_empresa(empresa_id, texto)
            print(f"  [OK] Contexto de '{empresa_id}' migrado ({len(texto)} chars).")
    print(f"-> Contextos migrados.\n")


def migrar_historico():
    if not HISTORICO_DIR.exists():
        print("[SKIP] Pasta config/historico não encontrada.")
        return
    arquivos = list(HISTORICO_DIR.glob("*.json"))
    if not arquivos:
        print("[SKIP] Nenhum arquivo .json em config/historico.")
        return
    for arq in arquivos:
        empresa_id = arq.stem
        # Verifica se já há entradas no banco para essa empresa
        existentes = col_historico().count_documents({"empresa_id": empresa_id})
        if existentes > 0:
            print(f"  [SKIP] Histórico de '{empresa_id}' já existe no banco ({existentes} entradas).")
            continue
        entradas = json.loads(arq.read_text(encoding="utf-8"))
        for entrada in entradas:
            salvar_entrada_historico(
                empresa_id=empresa_id,
                tema=entrada.get("tema", ""),
                dados_usados=entrada.get("dados_usados", []),
            )
        print(f"  [OK] {len(entradas)} entradas de histórico de '{empresa_id}' migradas.")
    print(f"-> Históricos migrados.\n")


if __name__ == "__main__":
    print("=== MIGRAÇÃO DE DADOS PARA MONGODB ===\n")

    print("1. Migrando empresas...")
    migrar_empresas()

    print("2. Migrando contextos compilados...")
    migrar_contextos()

    print("3. Migrando histórico de temas...")
    migrar_historico()

    print("=== CONCLUÍDO ===")
