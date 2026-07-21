from contextlib import asynccontextmanager
import asyncio
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI

from api.routers import agenda, publicar
from api.routers.publicar import _executar_publicacao


async def _publicar_em_background(agenda_id: str):
    try:
        await asyncio.to_thread(_executar_publicacao, agenda_id)
    except Exception as e:
        print(f"[Scheduler] Exceção não capturada em {agenda_id}: {e}", flush=True)
        traceback.print_exc()


async def _loop_scheduler():
    """Verifica a cada 60s se há posts agendados prontos para publicar."""
    from modulos.db import col_agenda
    while True:
        try:
            agora = datetime.now(timezone.utc).replace(tzinfo=None)
            pendentes = list(col_agenda().find({
                "status": "pendente",
                "data_hora": {"$lte": agora},
            }))
            for doc in pendentes:
                agenda_id = str(doc["_id"])
                print(f"[Scheduler] Disparando: {agenda_id} ({doc.get('plataforma')} / {doc.get('empresa_id')})", flush=True)
                asyncio.create_task(_publicar_em_background(agenda_id))
        except Exception as e:
            print(f"[Scheduler] Erro no loop: {e}", flush=True)
            traceback.print_exc()
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_loop_scheduler())
    yield
    task.cancel()


app = FastAPI(
    title="BOB Scheduling API",
    description="API para agendamento e publicação automática de posts",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(agenda.router)
app.include_router(publicar.router)


@app.get("/health")
def health():
    return {"status": "ok"}
