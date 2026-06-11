import re
import subprocess
from pathlib import Path
from PIL import Image

from modulos import gerador_imagens

# ffmpeg empacotado pelo Remotion (fallback quando não está no PATH)
_FFMPEG_REMOTION = Path("remotion_project/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe")


def _ffmpeg_bin() -> str:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    if _FFMPEG_REMOTION.exists():
        return str(_FFMPEG_REMOTION)
    raise RuntimeError("ffmpeg não encontrado. Instale ffmpeg ou verifique o projeto Remotion.")


def extrair_audio_instagram(url: str, output_path: Path) -> Path:
    """
    Baixa um vídeo do Instagram via yt-dlp e extrai o áudio como MP3.
    Retorna o caminho do arquivo MP3 gerado.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg_bin()

    # Baixa apenas o áudio direto, sem precisar de passo intermediário
    temp_video = output_path.with_suffix(".tmp_video")

    print(f"[Mídia] Baixando vídeo do Instagram: {url}")
    subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "-o", str(temp_video),
            url,
        ],
        check=True,
    )

    # Descobre a extensão real baixada (yt-dlp pode adicionar extensão ao nome)
    candidatos = list(temp_video.parent.glob(temp_video.stem + "*"))
    if not candidatos:
        raise FileNotFoundError(f"yt-dlp não gerou arquivo em {temp_video.parent}")
    arquivo_baixado = candidatos[0]

    print(f"[Mídia] Extraindo áudio para: {output_path}")
    subprocess.run(
        [ffmpeg, "-y", "-i", str(arquivo_baixado), "-vn",
         "-acodec", "libmp3lame", "-q:a", "2", str(output_path)],
        check=True,
    )

    arquivo_baixado.unlink(missing_ok=True)

    print(f"[Mídia] Áudio extraído com sucesso: {output_path}")
    return output_path
# Aqui você importaria o seu llm_brain para gerar os prompts
# from modulos import llm_brain

def _dividir_roteiro_em_cenas(roteiro: str, frases_por_cena: int = 4) -> list[str]:
    """Divide o texto a cada N frases para gerar os clipes no tempo certo."""
    frases = re.split(r'(?<=[.!?]) +', roteiro)
    cenas = []
    for i in range(0, len(frases), frases_por_cena):
        cenas.append(" ".join(frases[i:i + frases_por_cena]))
    return cenas


def gerar_clipes_ia(roteiro: str, identidade_visual: dict, empresa_id: str, stem: str) -> list[Path]:
    """
    Passo 1: Pega o roteiro e divide a cada 4 frases.
    Passo 2: Chama o LLM para criar um prompt descritivo de cena sem texto.
    Passo 3: Chama a API de Vídeo (ex: RunwayML, Luma) para gerar o .mp4.
    """
    print(f"[Mídia] Iniciando geração de clipes de vídeo IA para {empresa_id}")
    cenas = _dividir_roteiro_em_cenas(roteiro)
    
    caminhos_videos = []
    for idx, cena_texto in enumerate(cenas):
        print(f"  -> Gerando prompt visual para a cena {idx+1}: {cena_texto[:30]}...")
        
        # prompt_visual = llm_brain.gerar_prompt_de_video(cena_texto, identidade_visual)
        # url_video_ia = runway_api.generate(prompt_visual)
        # video_path = baixar_video(url_video_ia)
        
        # Mock do resultado
        mock_path = Path(f"outputs/{empresa_id}/videos/{stem}_cena_{idx}.mp4")
        caminhos_videos.append(mock_path)
        
    return caminhos_videos

def gerar_background_animacao_texto(identidade_visual: dict, empresa_id: str, stem: str) -> Path:
    """
    Reutiliza a lógica do gerador_imagens para criar um fundo limpo para o Remotion.
    Retorna um arquivo PNG (1080x1920) com as cores da empresa.
    """
    print(f"[Mídia] Gerando background vertical para animação de {empresa_id}...")
    pasta = Path("outputs") / empresa_id / "videos"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_bg = pasta / f"{stem}_bg.png"
    
    cores = identidade_visual.get("primarias", [])
    cor_primaria = gerador_imagens._primeira_cor(cores)
    
    # Cria canvas vertical (Reels/Tiktok) com a cor primária
    canvas = Image.new("RGB", (1080, 1920), cor_primaria)
    
    # Adiciona gradiente para dar um toque mais premium (usando a função existente)
    gradiente = gerador_imagens._gradiente_preto(1080, 1920, alpha_topo=0, alpha_base=180, inicio_rel=0.3)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), gradiente).convert("RGB")
    
    canvas.save(caminho_bg, "PNG")
    return caminho_bg
