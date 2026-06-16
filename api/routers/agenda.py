from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    AgendamentoCreate,
    AgendamentoLoteCreate,
    AgendamentoResponse,
    AgendamentoUpdate,
    LoteResponse,
)
from modulos.db import (
    _doc_para_dict,
    agenda_da_semana,
    agendar_post,
    atualizar_agendamento,
    col_agenda,
    excluir_agendamento,
    listar_agenda,
)

router = APIRouter(prefix="/agenda", tags=["Agenda"])


def _to_response(doc: dict) -> dict:
    doc = _doc_para_dict(dict(doc))
    doc["id"] = doc.pop("_id")
    doc.setdefault("platform_post_id", None)
    doc.setdefault("erro_msg", None)
    doc.setdefault("video_path", "")
    doc.setdefault("texto", "")
    return doc


@router.post("", response_model=AgendamentoResponse, status_code=201)
def criar_agendamento(body: AgendamentoCreate):
    agenda_id = agendar_post(
        conteudo_id=body.conteudo_id,
        empresa_id=body.empresa_id,
        plataforma=body.plataforma,
        data_hora=body.data_hora,
        texto=body.texto,
        video_path=body.video_path,
    )
    doc = col_agenda().find_one({"_id": ObjectId(agenda_id)})
    return _to_response(doc)


@router.post("/lote", response_model=LoteResponse, status_code=201)
def criar_agendamentos_lote(body: AgendamentoLoteCreate):
    """Cria múltiplos agendamentos em uma única chamada."""
    ids = []
    for item in body.agendamentos:
        agenda_id = agendar_post(
            conteudo_id=item.conteudo_id,
            empresa_id=item.empresa_id,
            plataforma=item.plataforma,
            data_hora=item.data_hora,
            texto=item.texto,
            video_path=item.video_path,
        )
        ids.append(agenda_id)
    return {"criados": len(ids), "ids": ids}


@router.get("", response_model=list[AgendamentoResponse])
def listar(
    empresa_id: Optional[str] = Query(None),
    plataforma: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    docs = listar_agenda(empresa_id=empresa_id, plataforma=plataforma, status=status)
    return [_to_response(d) for d in docs]


@router.get("/semana", response_model=list[AgendamentoResponse])
def agenda_semana(empresa_id: Optional[str] = Query(None)):
    docs = agenda_da_semana(empresa_id=empresa_id)
    return [_to_response(d) for d in docs]


@router.get("/{agenda_id}", response_model=AgendamentoResponse)
def buscar(agenda_id: str):
    doc = col_agenda().find_one({"_id": ObjectId(agenda_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return _to_response(doc)


@router.put("/{agenda_id}", response_model=AgendamentoResponse)
def atualizar(agenda_id: str, body: AgendamentoUpdate):
    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    atualizar_agendamento(agenda_id, campos)
    doc = col_agenda().find_one({"_id": ObjectId(agenda_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return _to_response(doc)


@router.delete("/{agenda_id}", status_code=204)
def deletar(agenda_id: str):
    excluir_agendamento(agenda_id)
