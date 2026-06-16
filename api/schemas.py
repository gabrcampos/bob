from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class AgendamentoCreate(BaseModel):
    conteudo_id: str
    empresa_id: str
    plataforma: Literal["youtube_shorts", "tiktok"]
    data_hora: datetime
    texto: str = ""
    video_path: str = ""


class AgendamentoLoteCreate(BaseModel):
    agendamentos: list[AgendamentoCreate]


class AgendamentoUpdate(BaseModel):
    plataforma: Optional[Literal["youtube_shorts", "tiktok"]] = None
    data_hora: Optional[datetime] = None
    texto: Optional[str] = None
    video_path: Optional[str] = None
    status: Optional[Literal["pendente", "processando", "publicado", "erro"]] = None


class AgendamentoResponse(BaseModel):
    id: str
    conteudo_id: str
    empresa_id: str
    plataforma: str
    data_hora: datetime
    texto: str
    video_path: str
    status: str
    platform_post_id: Optional[str] = None
    erro_msg: Optional[str] = None
    criado_em: datetime
    atualizado_em: datetime


class LoteResponse(BaseModel):
    criados: int
    ids: list[str]
