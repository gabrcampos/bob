"""
Camada de acesso ao MongoDB (banco: bob_content).

Coleções:
  - conteudos   : peças de conteúdo geradas (slides, textos, status)
  - agenda      : agendamentos por plataforma
  - empresas    : cadastro de clientes (migrado de config/empresas.json)
  - historico   : temas gerados por empresa (migrado de config/historico/*.json)
"""

import os
from datetime import datetime
from functools import lru_cache

from bson import ObjectId
from pymongo import MongoClient, DESCENDING
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Conexão
# ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _client() -> MongoClient:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI não definida no .env")
    return MongoClient(uri, serverSelectionTimeoutMS=20000)


def _db():
    return _client()["bob_content"]


def col_conteudos():
    return _db()["conteudos"]


def col_agenda():
    return _db()["agenda"]


def col_empresas():
    return _db()["empresas"]


def col_historico():
    return _db()["historico"]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _agora() -> datetime:
    return datetime.utcnow()


def _doc_para_dict(doc: dict) -> dict:
    """Converte ObjectId → string para exibição no Streamlit."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ─────────────────────────────────────────────
# CONTEÚDOS — escrita
# ─────────────────────────────────────────────

def _gerar_stem(tema: str) -> str:
    """Gera um identificador de pasta para imagens: slug_YYYYMMDD_HHMMSS."""
    import re
    slug = tema.lower().strip()
    for src, dst in [("àáâãä","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u"),("ç","c")]:
        for c in src:
            slug = slug.replace(c, dst)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")[:60]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{slug}_{ts}"


def salvar_conteudo(
    empresa_id: str,
    tipo: str,
    tema: str,
    *,
    slides: list[dict] | None = None,
    legenda: str = "",
    post_linkedin: str = "",
    narracao_video: str = "",
    blog: str = "",
    empresa_nome: str = "",
    publico_alvo: str = "",
) -> str:
    """Insere uma peça de conteúdo. Retorna o _id como string."""
    doc = {
        "empresa_id":    empresa_id,
        "empresa_nome":  empresa_nome,
        "publico_alvo":  publico_alvo,
        "tipo":          tipo,
        "tema":          tema,
        "stem":          _gerar_stem(tema),
        "slides":        slides or [],
        "legenda":       legenda,
        "post_linkedin": post_linkedin,
        "narracao_video": narracao_video,
        "blog":          blog,
        "status":        "em_producao",  # em_producao, no_drive, ta_no_doc
        "drive_link":    None,
        "doc_link":      None,
        "criado_em":     _agora(),
        "atualizado_em": _agora(),
    }
    result = col_conteudos().insert_one(doc)
    return str(result.inserted_id)


def atualizar_conteudo(conteudo_id: str, campos: dict):
    """Atualiza campos de um documento. Sempre toca atualizado_em."""
    campos["atualizado_em"] = _agora()
    col_conteudos().update_one(
        {"_id": ObjectId(conteudo_id)},
        {"$set": campos},
    )


def excluir_conteudo(conteudo_id: str):
    col_conteudos().delete_one({"_id": ObjectId(conteudo_id)})
    col_agenda().delete_many({"conteudo_id": conteudo_id})


# ─────────────────────────────────────────────
# CONTEÚDOS — leitura
# ─────────────────────────────────────────────

def listar_conteudos(
    empresa_id: str,
    tipo: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Lista conteúdos de uma empresa, mais recentes primeiro."""
    filtro: dict = {"empresa_id": empresa_id}
    if tipo:
        filtro["tipo"] = tipo
    docs = (
        col_conteudos()
        .find(filtro)
        .sort("criado_em", DESCENDING)
        .limit(limit)
    )
    return [_doc_para_dict(d) for d in docs]


def buscar_conteudo(conteudo_id: str) -> dict | None:
    doc = col_conteudos().find_one({"_id": ObjectId(conteudo_id)})
    return _doc_para_dict(doc) if doc else None


def contar_conteudos(empresa_id: str) -> dict[str, int]:
    """Retorna contagem por tipo para uma empresa."""
    pipeline = [
        {"$match": {"empresa_id": empresa_id}},
        {"$group": {"_id": "$tipo", "total": {"$sum": 1}}},
    ]
    return {r["_id"]: r["total"] for r in col_conteudos().aggregate(pipeline)}


def contar_conteudos_por_status(empresa_id: str) -> dict[str, dict[str, int]]:
    """
    Retorna contagem por tipo e depois por status para uma empresa.
    Ex: {'carrossel': {'em_producao': 10, 'no_drive': 5}}
    Trata status nulo como 'em_producao' e status legados (dict).
    """
    pipeline = [
        {"$match": {"empresa_id": empresa_id}},
        {"$project": {
            "tipo": "$tipo",
            "status": {
                "$let": {
                    "vars": {"s": {"$ifNull": ["$status", "em_producao"]}},
                    "in": {
                        "$cond": {
                            "if": {"$eq": [{"$type": "$$s"}, "object"]},
                            "then": {"$cond": {"if": {"$eq": ["$$s.drive_enviado", True]}, "then": "no_drive", "else": "em_producao"}},
                            "else": "$$s"
                        }
                    }
                }
            }
        }},
        {"$group": {"_id": {"tipo": "$tipo", "status": "$status"}, "total": {"$sum": 1}}},
        {"$group": {"_id": "$_id.tipo", "statuses": {"$push": {"k": "$_id.status", "v": "$total"}}}},
        {"$project": {"_id": 0, "tipo": "$_id", "contagens": {"$arrayToObject": "$statuses"}}}
    ]
    resultados = col_conteudos().aggregate(pipeline)
    return {r["tipo"]: r["contagens"] for r in resultados if r.get("tipo")}


def migrar_status_legado() -> int:
    """Migra os status antigos (formato dict) para o novo formato string."""
    docs = col_conteudos().find()
    count = 0
    for d in docs:
        status_atual = d.get("status")
        if isinstance(status_atual, dict):
            novo_status = "em_producao"
            atualizacao = {}
            
            if status_atual.get("drive_enviado"):
                novo_status = "no_drive"
                
            if status_atual.get("drive_link") and not d.get("drive_link"):
                atualizacao["drive_link"] = status_atual.get("drive_link")
            
            tipo = d.get("tipo", "")
            if tipo in ("linkedin", "video", "blog") and d.get("doc_link"):
                novo_status = "ta_no_doc"
                
            atualizacao["status"] = novo_status
            col_conteudos().update_one({"_id": d["_id"]}, {"$set": atualizacao})
            count += 1
            
    return count

# ─────────────────────────────────────────────
# AGENDA — escrita
# ─────────────────────────────────────────────

def agendar_post(
    conteudo_id: str,
    empresa_id: str,
    plataforma: str,
    data_hora: datetime,
    texto: str = "",
    video_path: str = "",
) -> str:
    """Cria um agendamento. Retorna o _id como string."""
    doc = {
        "conteudo_id":      conteudo_id,
        "empresa_id":       empresa_id,
        "plataforma":       plataforma,
        "data_hora":        data_hora,
        "texto":            texto,
        "video_path":       video_path,
        "status":           "pendente",
        "platform_post_id": None,
        "erro_msg":         None,
        "criado_em":        _agora(),
        "atualizado_em":    _agora(),
    }
    result = col_agenda().insert_one(doc)
    return str(result.inserted_id)


def atualizar_agendamento(agenda_id: str, campos: dict):
    campos["atualizado_em"] = _agora()
    col_agenda().update_one(
        {"_id": ObjectId(agenda_id)},
        {"$set": campos},
    )


def excluir_agendamento(agenda_id: str):
    col_agenda().delete_one({"_id": ObjectId(agenda_id)})


# ─────────────────────────────────────────────
# AGENDA — leitura
# ─────────────────────────────────────────────

def listar_agenda(
    empresa_id: str | None = None,
    plataforma: str | None = None,
    status: str | None = None,
) -> list[dict]:
    filtro: dict = {}
    if empresa_id:
        filtro["empresa_id"] = empresa_id
    if plataforma:
        filtro["plataforma"] = plataforma
    if status:
        filtro["status"] = status
    docs = col_agenda().find(filtro).sort("data_hora", 1)
    return [_doc_para_dict(d) for d in docs]


def agenda_da_semana(empresa_id: str | None = None) -> list[dict]:
    """Retorna agendamentos dos próximos 7 dias."""
    from datetime import timedelta
    agora = _agora()
    filtro: dict = {"data_hora": {"$gte": agora, "$lte": agora + timedelta(days=7)}}
    if empresa_id:
        filtro["empresa_id"] = empresa_id
    docs = col_agenda().find(filtro).sort("data_hora", 1)
    return [_doc_para_dict(d) for d in docs]


# ─────────────────────────────────────────────
# EMPRESAS
# ─────────────────────────────────────────────

def listar_empresas() -> list[dict]:
    """Retorna todas as empresas cadastradas."""
    return [_doc_para_dict(d) for d in col_empresas().find().sort("nome", 1)]


def buscar_empresa(empresa_id: str) -> dict | None:
    doc = col_empresas().find_one({"id": empresa_id})
    return _doc_para_dict(doc) if doc else None


def salvar_empresa(empresa: dict):
    """Upsert de empresa pelo campo 'id'."""
    empresa_id = empresa["id"]
    col_empresas().update_one(
        {"id": empresa_id},
        {"$set": empresa},
        upsert=True,
    )


def atualizar_empresa(empresa_id: str, campos: dict):
    col_empresas().update_one({"id": empresa_id}, {"$set": campos})


def deletar_empresa(empresa_id: str):
    col_empresas().delete_one({"id": empresa_id})


def salvar_contexto_empresa(empresa_id: str, contexto: str):
    col_empresas().update_one(
        {"id": empresa_id},
        {"$set": {"contexto_compilado": contexto}},
        upsert=True,
    )


def carregar_contexto_empresa(empresa_id: str) -> str:
    doc = col_empresas().find_one({"id": empresa_id}, {"contexto_compilado": 1})
    if doc:
        return doc.get("contexto_compilado", "")
    return ""


# ─────────────────────────────────────────────
# HISTÓRICO DE TEMAS
# ─────────────────────────────────────────────

def salvar_entrada_historico(empresa_id: str, tema: str, dados_usados: list[str]):
    """Insere uma entrada de histórico. Mantém as últimas 20 por empresa."""
    col_historico().insert_one({
        "empresa_id": empresa_id,
        "data": datetime.utcnow().strftime("%Y-%m-%d"),
        "tema": tema,
        "dados_usados": dados_usados,
        "criado_em": _agora(),
    })
    # Garante no máximo 20 entradas por empresa — remove as mais antigas se necessário
    total = col_historico().count_documents({"empresa_id": empresa_id})
    if total > 20:
        mais_antigos = (
            col_historico()
            .find({"empresa_id": empresa_id})
            .sort("criado_em", 1)
            .limit(total - 20)
        )
        ids_remover = [d["_id"] for d in mais_antigos]
        col_historico().delete_many({"_id": {"$in": ids_remover}})


def listar_historico(empresa_id: str, limit: int = 5) -> list[dict]:
    """Retorna as últimas `limit` entradas de histórico de uma empresa."""
    docs = (
        col_historico()
        .find({"empresa_id": empresa_id})
        .sort("criado_em", -1)
        .limit(limit)
    )
    # Retorna em ordem cronológica (mais antigas primeiro) para o prompt
    return list(reversed([_doc_para_dict(d) for d in docs]))
