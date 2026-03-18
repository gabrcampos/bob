import os
import re
import base64
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

FONTES_DIR   = Path("config/fontes")
OUTPUTS_DIR  = Path("outputs")
SLIDE_W      = 1080
SLIDE_H      = 1350
AREA_TEXTO_H = 540   # metade inferior fixa (imagem ocupa os 810px superiores)


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no ambiente.")
    return genai.Client(api_key=api_key)



def _quebrar_texto(texto: str, fonte: ImageFont.FreeTypeFont,
                   largura: int, draw: ImageDraw.ImageDraw) -> list[str]:
    linhas, linha = [], ""
    for palavra in texto.split():
        candidato = f"{linha} {palavra}".strip()
        if draw.textbbox((0, 0), candidato, font=fonte)[2] <= largura:
            linha = candidato
        else:
            if linha:
                linhas.append(linha)
            linha = palavra
    if linha:
        linhas.append(linha)
    return linhas


# ─────────────────────────────────────────────
# Fontes
# ─────────────────────────────────────────────

def _limpar_nome_fonte(nome: str, remover_peso: bool = False) -> str:
    """Remove sufixos de tamanho e opcionalmente de peso do nome da fonte."""
    nome = re.sub(r'\s+\d+\s*(pt|px|rem|em)\b', '', nome, flags=re.IGNORECASE)
    if remover_peso:
        nome = re.sub(r'\s+(Bold|Regular|Italic|Light|Thin|Medium|Black|ExtraBold|SemiBold)\b', '', nome, flags=re.IGNORECASE)
    return nome.strip()


def _tentar_baixar_fonte(nome: str) -> Path | None:
    """Tenta baixar TTF do Google Fonts pelo nome exato via múltiplos endpoints."""
    FONTES_DIR.mkdir(parents=True, exist_ok=True)
    path = FONTES_DIR / f"{nome.replace(' ', '_')}.ttf"
    if path.exists():
        return path

    familia = nome.replace(' ', '+')
    # Tenta CSS v2, CSS v1 e URL com especificação de peso
    endpoints = [
        f"https://fonts.googleapis.com/css2?family={familia}&display=swap",
        f"https://fonts.googleapis.com/css?family={familia}",
        f"https://fonts.googleapis.com/css2?family={familia}:wght@400;700;900&display=swap",
    ]
    headers = {"User-Agent": "Mozilla/4.0 (compatible; MSIE 5.0; Windows 98)"}
    for url in endpoints:
        try:
            css = requests.get(url, timeout=10, headers=headers).text
            urls = re.findall(r"url\((https://[^)]+\.ttf)\)", css)
            if urls:
                data = requests.get(urls[0], timeout=15).content
                path.write_bytes(data)
                print(f"[Imagens] Fonte '{nome}' baixada.")
                return path
        except Exception:
            continue
    return None


def _fonte_cache_parcial(nome: str) -> Path | None:
    """Procura no cache uma fonte cujo nome de arquivo contenha o nome buscado."""
    if not FONTES_DIR.exists():
        return None
    nome_norm = nome.lower().replace(' ', '_')
    for f in FONTES_DIR.glob("*.ttf"):
        if nome_norm in f.stem.lower():
            print(f"[Imagens] Fonte '{nome}' encontrada no cache como '{f.name}'.")
            return f
    return None


def baixar_fonte(nome: str) -> Path | None:
    """Baixa TTF do Google Fonts com múltiplos fallbacks."""
    # 1ª: com peso preservado (ex: "Archivo Black")
    candidato = _limpar_nome_fonte(nome, remover_peso=False)
    path = _fonte_cache_parcial(candidato) or _tentar_baixar_fonte(candidato)
    if path:
        return path
    # 2ª: sem peso (ex: "Archivo")
    candidato2 = _limpar_nome_fonte(nome, remover_peso=True)
    if candidato2 != candidato:
        path = _fonte_cache_parcial(candidato2) or _tentar_baixar_fonte(candidato2)
        if path:
            return path
    print(f"[Imagens] TTF não encontrado para '{nome}'")
    return None


_FONTES_SISTEMA = [
    "arial.ttf", "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]


def _carregar_fonte(nome: str | None, tamanho: int) -> ImageFont.FreeTypeFont:
    if nome:
        path = baixar_fonte(nome)
        if path:
            try:
                return ImageFont.truetype(str(path), tamanho)
            except Exception:
                pass
    for candidato in _FONTES_SISTEMA:
        try:
            return ImageFont.truetype(candidato, tamanho)
        except Exception:
            pass
    return ImageFont.load_default()


# ─────────────────────────────────────────────
# Geração de fundo via Gemini
# ─────────────────────────────────────────────

_MODELOS_IMAGEM = [
    "imagen-4.0-fast-generate-001",
    "gemini-2.5-flash-image",
]

def _gerar_fundo(prompt_imagem: str, estilo_imagem: str, cores: list[dict]) -> bytes:
    """Gera imagem de fundo via Gemini/Imagen. Lança exceção se falhar."""
    hexes = ", ".join(c["hex"] for c in cores if c.get("hex"))
    prompt = (
        f"{prompt_imagem} "
        f"{estilo_imagem} "
        f"Brand color palette: {hexes or 'dark navy blue and white'}. "
        f"IMPORTANT: absolutely NO text, NO letters, NO numbers, NO words anywhere in the image. "
        f"High resolution, suitable for a LinkedIn carousel slide."
    )
    client = _get_client()
    ultimo_erro = None

    for modelo in _MODELOS_IMAGEM:
        try:
            # Imagen usa generate_images(); modelos Gemini usam generate_content()
            if "imagen" in modelo.lower():
                response = client.models.generate_images(
                    model=modelo,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(number_of_images=1),
                )
                data = response.generated_images[0].image.image_bytes
                if isinstance(data, str):
                    data = base64.b64decode(data)
                print(f"[Imagens] Fundo gerado com {modelo}")
                return data
            else:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"]
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        data = part.inline_data.data
                        if isinstance(data, str):
                            data = base64.b64decode(data)
                        print(f"[Imagens] Fundo gerado com {modelo}")
                        return data
                ultimo_erro = f"{modelo}: não retornou imagem"
                print(f"[Imagens] {ultimo_erro}")
        except Exception as e:
            ultimo_erro = f"{modelo}: {e}"
            print(f"[Imagens] Erro com {modelo}: {e}")

    raise RuntimeError(
        f"Nenhum modelo funcionou. Último erro: {ultimo_erro}"
    )


# ─────────────────────────────────────────────
# Composição do slide
# ─────────────────────────────────────────────

def _gradiente_preto(largura: int, altura: int, alpha_topo: int = 0, alpha_base: int = 204) -> Image.Image:
    """Cria uma camada RGBA preta com gradiente vertical de transparência."""
    gradiente = Image.new("L", (1, altura))
    for y in range(altura):
        a = int(alpha_topo + (alpha_base - alpha_topo) * (y / (altura - 1)))
        gradiente.putpixel((0, y), a)
    gradiente = gradiente.resize((largura, altura), Image.BILINEAR)
    camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    camada.putalpha(gradiente)
    return camada


def compor_slide(titulo: str, texto: str, fundo_bytes: bytes,
                 nome_fonte: str | None) -> Image.Image:
    # Fundo IA em tamanho total
    fundo = Image.open(BytesIO(fundo_bytes)).convert("RGBA")
    fundo = fundo.resize((SLIDE_W, SLIDE_H))
    canvas = fundo.copy()

    # Gradiente preto: 0% opacidade no topo → 80% na base
    overlay = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=204)
    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    draw    = ImageDraw.Draw(canvas)
    cor_txt = (255, 255, 255)   # texto sempre branco sobre o gradiente escuro
    pad     = 64
    y       = SLIDE_H - AREA_TEXTO_H + pad
    max_w   = SLIDE_W - pad * 2

    # Título
    f_titulo = _carregar_fonte(nome_fonte, 62)
    for linha in _quebrar_texto(titulo, f_titulo, max_w, draw)[:3]:
        draw.text((pad, y), linha, font=f_titulo, fill=cor_txt)
        y += draw.textbbox((0, 0), linha, font=f_titulo)[3] + 10

    # Separador
    y += 14
    draw.line([(pad, y), (SLIDE_W - pad, y)], fill=cor_txt, width=2)
    y += 22

    # Texto do slide
    f_corpo = _carregar_fonte(nome_fonte, 34)
    for linha in _quebrar_texto(texto, f_corpo, max_w, draw)[:7]:
        draw.text((pad, y), linha, font=f_corpo, fill=cor_txt)
        y += draw.textbbox((0, 0), linha, font=f_corpo)[3] + 7

    return canvas


# ─────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────

def gerar_imagens_carrossel(
    slides: list[dict],
    empresa_id: str,
    stem: str,
    identidade_visual: dict,
    callback: callable = None,
) -> list[Path]:
    """
    Gera uma imagem PNG por slide.
    callback(n_atual, total) chamado após cada slide.
    Retorna lista de paths salvos.
    """
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores  = identidade_visual.get("primarias", [])
    fontes = identidade_visual.get("fontes", [])
    fonte  = fontes[0] if fontes else None

    paths = []
    estilo = identidade_visual.get("estilo_imagem", "")
    total  = len(slides)
    for i, slide in enumerate(slides):
        n    = slide.get("slide", i + 1)
        dest = pasta / f"slide_{n:02d}.png"

        prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
        print(f"[Imagens] Slide {n}/{total}: {slide['titulo']}")
        fundo  = _gerar_fundo(prompt_imagem, estilo, cores)
        imagem = compor_slide(slide["titulo"], slide["texto"], fundo, fonte)
        imagem.save(str(dest), "PNG")
        paths.append(dest)

        if callback:
            callback(i + 1, total)

    return paths


def listar_imagens(empresa_id: str, stem: str) -> list[Path]:
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    if not pasta.exists():
        return []
    return sorted(pasta.glob("slide_*.png"))
