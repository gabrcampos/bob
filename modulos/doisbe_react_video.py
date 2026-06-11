"""
Orquestra a criação do vídeo "fake corte de React":
  - topo  (600 px): clipe de YouTube baixado via yt-dlp
  - base (1320 px): corte do broll-react.mp4 via ffmpeg
Renderiza com o projeto Remotion doisbe-react.
"""

import json
import subprocess
from pathlib import Path

REMOTION_PROJECT = Path(__file__).parent.parent / "doisbe-react"
PUBLIC_DIR = REMOTION_PROJECT / "public"
BROLL_REACT_SOURCE = Path(
    r"C:\Users\Gabriel Campos\Documents\ProjetosDev"
    r"\cta-machine-pattern\companies\doisbe\broll-react\broll-react-1.mp4"
)


# ─── YouTube ─────────────────────────────────────────────────────────────────

def baixar_youtube(url: str, output_path: Path) -> Path:
    """
    Baixa o melhor formato mp4 ≤ 1080p do URL e salva em output_path.
    Requer yt-dlp instalado: pip install yt-dlp
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--format", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]",
        "--merge-output-format", "mp4",
        "--output", str(output_path),
        "--no-playlist",
        url,
    ]

    print(f"[YouTube] Baixando: {url}")
    subprocess.run(cmd, check=True)
    print(f"[YouTube] Salvo em: {output_path}")
    return output_path


# ─── B-roll React ─────────────────────────────────────────────────────────────

def cortar_broll_react(
    start_sec: float,
    duration_sec: float,
    output_path: Path,
    source: Path = BROLL_REACT_SOURCE,
) -> Path:
    """
    Recorta um trecho do broll-react.mp4 usando ffmpeg (cópia de stream, sem re-encode).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", str(source),
        "-t", str(duration_sec),
        "-c", "copy",
        str(output_path),
    ]

    print(f"[BRoll] Cortando {duration_sec}s a partir de {start_sec}s...")
    subprocess.run(cmd, check=True)
    print(f"[BRoll] Clip salvo: {output_path}")
    return output_path


# ─── Preparação de assets ─────────────────────────────────────────────────────

def preparar_assets(
    *,
    youtube_url: str,
    youtube_start: float = 0.0,
    broll_start: float = 0.0,
    duracao_segundos: float,
    slug: str = "video",
    forcar_redownload: bool = False,
) -> dict:
    """
    1. Baixa o vídeo do YouTube (ou reutiliza se já existir).
    2. Copia broll-react.mp4 para public/ (Remotion precisa do arquivo em public/).
    3. Retorna o dict de props para o Remotion.
    """
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    # YouTube
    youtube_dest = PUBLIC_DIR / f"{slug}_youtube.mp4"
    if forcar_redownload or not youtube_dest.exists():
        baixar_youtube(youtube_url, youtube_dest)
    else:
        print(f"[YouTube] Reutilizando: {youtube_dest.name}")

    # B-roll React — copia para public/ para que o Remotion acesse via staticFile()
    broll_dest = PUBLIC_DIR / f"{slug}_broll_react.mp4"
    if not broll_dest.exists() or forcar_redownload:
        import shutil
        if BROLL_REACT_SOURCE.exists():
            shutil.copy2(BROLL_REACT_SOURCE, broll_dest)
            print(f"[BRoll] Copiado para public/: {broll_dest.name}")
        else:
            raise FileNotFoundError(
                f"broll-react.mp4 não encontrado em: {BROLL_REACT_SOURCE}\n"
                "Coloque o arquivo antes de rodar."
            )
    else:
        print(f"[BRoll] Reutilizando: {broll_dest.name}")

    fps = 30
    props = {
        "brollSrc": broll_dest.name,
        "youtubeSrc": youtube_dest.name,
        "youtubeStartFrom": youtube_start,
        "brollStartFrom": broll_start,
        "durationInFrames": round(duracao_segundos * fps),
    }

    props_path = REMOTION_PROJECT / "public" / "current_props.json"
    props_path.write_text(json.dumps(props, indent=2, ensure_ascii=False))
    print(f"[Props] Salvo: {props_path}")

    return props


# ─── Renderização ─────────────────────────────────────────────────────────────

def renderizar(output_path: Path, concurrency: int = 4) -> Path:
    """
    Chama o CLI do Remotion para renderizar o projeto doisbe-react.
    Requer: npm install já executado dentro de doisbe-react/.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "npx", "remotion", "render",
        "FakeCorteReact",
        str(output_path),
        "--concurrency", str(concurrency),
    ]

    print(f"[Remotion] Renderizando → {output_path}")
    subprocess.run(cmd, check=True, cwd=str(REMOTION_PROJECT))
    print(f"[Remotion] Vídeo gerado: {output_path}")
    return output_path


# ─── Ponto de entrada conveniente ────────────────────────────────────────────

def gerar_fake_corte_react(
    *,
    youtube_url: str,
    youtube_start: float = 0.0,
    broll_start: float = 0.0,
    duracao_segundos: float = 30.0,
    output_path: Path,
    slug: str = "video",
) -> Path:
    """
    Pipeline completo: prepara assets → atualiza props → renderiza.
    """
    preparar_assets(
        youtube_url=youtube_url,
        youtube_start=youtube_start,
        broll_start=broll_start,
        duracao_segundos=duracao_segundos,
        slug=slug,
    )
    return renderizar(output_path)
