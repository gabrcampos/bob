"""
Camada de acesso ao MongoDB (banco: bob_content).

Coleções:
  - conteudos   : peças de conteúdo geradas (slides, textos, status)
  - agenda      : agendamentos por plataforma
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
    return MongoClient(uri, serverSelectionTimeoutMS=8000)


def _db():
    return _client()["bob_content"]


def col_conteudos():
    return _db()["conteudos"]


def col_agenda():
    return _db()["agenda"]


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
        "status": {
            "slides_gerados":   bool(slides),
            "imagens_geradas":  False,
            "drive_enviado":    False,
            "drive_link":       None,
        },
        "aprovado":      False,
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


def marcar_imagens_geradas(conteudo_id: str):
    atualizar_conteudo(conteudo_id, {"status.imagens_geradas": True})


def marcar_drive_enviado(conteudo_id: str, link: str):
    atualizar_conteudo(conteudo_id, {
        "status.drive_enviado": True,
        "status.drive_link":    link,
    })


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


# ─────────────────────────────────────────────
# AGENDA — escrita
# ─────────────────────────────────────────────

def agendar_post(
    conteudo_id: str,
    empresa_id: str,
    plataforma: str,
    data_hora: datetime,
    texto: str = "",
) -> str:
    """Cria um agendamento. Retorna o _id como string."""
    doc = {
        "conteudo_id":      conteudo_id,
        "empresa_id":       empresa_id,
        "plataforma":       plataforma,
        "data_hora":        data_hora,
        "texto":            texto,
        "status":           "pendente",
        "platform_post_id": None,
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
