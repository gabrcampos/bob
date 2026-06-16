from fastapi import FastAPI

from api.routers import agenda, publicar

app = FastAPI(
    title="BOB Scheduling API",
    description="API para agendamento de posts em lote no TikTok e YouTube Shorts",
    version="1.0.0",
)

app.include_router(agenda.router)
app.include_router(publicar.router)


@app.get("/health")
def health():
    return {"status": "ok"}
