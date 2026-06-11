import os
import time
from pathlib import Path

from google import genai
from google.genai import types

OUTPUTS_DIR = Path("outputs")

# Durações suportadas pelo Veo 3.1 Lite (em segundos)
_DURACOES_VALIDAS = [5, 6, 8]


def _duracao_clip(segundos: float) -> int:
    """Escolhe a menor duração válida do Veo que cobre o trecho da frase."""
    for d in _DURACOES_VALIDAS:
        if d >= segundos:
            return d
    return _DURACOES_VALIDAS[-1]


def gerar_clip_broll(
    prompt: str,
    output_path: Path,
    duracao_segundos: float = 5.0,
) -> Path:
    """
    Gera um único clip de b-roll via Veo 3.1 Lite e salva em output_path.
    A geração é assíncrona — a função faz polling até concluir (~1-3 min por clip).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no ambiente.")

    client = genai.Client(api_key=api_key)
    duracao = _duracao_clip(duracao_segundos)

    print(f"[BRoll] Gerando clip {duracao}s | {prompt[:80]}...")

    operation = client.models.generate_videos(
        model="veo-3.1-lite-generate-preview",
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspectRatio="9:16",
            durationSeconds=duracao,
        ),
    )

    while not operation.done:
        time.sleep(20)
        operation = client.operations.get(operation)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    video = operation.response.generated_videos[0].video
    video.save(str(output_path))

    print(f"[BRoll] Clip salvo: {output_path}")
    return output_path


def gerar_videos_broll(
    prompts: list[dict],
    empresa_id: str,
    stem: str,
) -> list[dict]:
    """
    Recebe lista de {frase, prompt_video, start, end} e gera um clip por frase.
    Clips já existentes são reutilizados (idempotente).

    Retorna lista de {src (Path), start (float), end (float)}.
    """
    pasta = OUTPUTS_DIR / empresa_id / "broll"
    pasta.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, item in enumerate(prompts):
        output_path = pasta / f"{stem}_broll_{i:02d}.mp4"

        if output_path.exists():
            print(f"[BRoll] Clip {i:02d} já existe, reutilizando.")
        else:
            duracao = item["end"] - item["start"]
            gerar_clip_broll(item["prompt_video"], output_path, duracao)

        clips.append({
            "src": output_path,
            "start": item["start"],
            "end": item["end"],
        })

    return clips
