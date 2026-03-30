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
LOGOS_DIR    = Path("config/logos")
SLIDE_W      = 1080
SLIDE_H      = 1350
AREA_TEXTO_H = int(SLIDE_H * 0.65)  # 65% da altura — texto + elementos fixos do bottom


# ─────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────

def logo_empresa(empresa_id: str, index: int = 1) -> Path | None:
    """Retorna o path da logo da empresa. index=1 para logo principal, index=2 para alternativa."""
    sufixo = "" if index == 1 else f"_{index}"
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"{empresa_id}{sufixo}.{ext}"
        if p.exists():
            return p
    return None


def _hex_para_rgb_tuple(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _primeira_cor(cores: list[dict]) -> tuple[int, int, int]:
    for c in cores:
        try:
            return _hex_para_rgb_tuple(c.get("hex", ""))
        except Exception:
            pass
    return (255, 255, 255)


def _segunda_cor(cores: list[dict]) -> tuple[int, int, int]:
    """Retorna a primeira cor disponível na lista ou branco como fallback."""
    for c in cores:
        try:
            return _hex_para_rgb_tuple(c.get("hex", ""))
        except Exception:
            pass
    return (255, 255, 255)


def _limpar_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")


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


# Slides que usam bullet points (afeta compor_slide e compor_slide_tweet)
_SLIDES_COM_BULLETS_CHECK = frozenset({2})   # ✓ checkmarks
_SLIDES_COM_BULLETS_FAIL  = frozenset({4})   # ✗ xmarks
_SLIDES_COM_BULLETS       = _SLIDES_COM_BULLETS_CHECK | _SLIDES_COM_BULLETS_FAIL


def _linhas_bullet(
    texto: str,
    fonte: ImageFont.FreeTypeFont,
    max_w: int,
    draw: ImageDraw.ImageDraw,
) -> list[tuple[str, str]]:
    """Retorna lista de (prefixo, linha) para texto com bullets ✓/✗ separados por \\n.
    O prefixo é '✓', '✗' ou '' para linhas de continuação."""
    result: list[tuple[str, str]] = []
    items = [l.strip() for l in texto.split("\n") if l.strip()]
    for item in items:
        if item.startswith("✓") or item.startswith("✗"):
            prefix = item[0]
            rest   = item[1:].lstrip()
            prefix_txt = prefix + " "
            prefix_w   = int(draw.textlength(prefix_txt, font=fonte)) + 8
            sublins    = _quebrar_texto(rest, fonte, max_w - prefix_w, draw)
            for j, sl in enumerate(sublins):
                result.append((prefix if j == 0 else "", sl))
        else:
            for sl in _quebrar_texto(item, fonte, max_w, draw):
                result.append(("", sl))
    return result or [("", "")]


# ─────────────────────────────────────────────
# Fontes
# ─────────────────────────────────────────────

def _limpar_nome_fonte(nome: str, remover_peso: bool = False) -> str:
    """Remove sufixos de tamanho e opcionalmente de peso do nome da fonte."""
    nome = re.sub(r'\s+\d+\s*(pt|px|rem|em)\b', '', nome, flags=re.IGNORECASE)
    if remover_peso:
        nome = re.sub(r'\s+(Bold|Regular|Italic|Light|Thin|Medium|Black|ExtraBold|SemiBold)\b', '', nome, flags=re.IGNORECASE)
    return nome.strip()


_USER_AGENTS = [
    "Mozilla/4.0 (compatible; MSIE 5.0; Windows 98)",
    "Wget/1.9.1",
    "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)",
]


def _extrair_url_por_peso(css: str, peso: int) -> str | None:
    """Percorre blocos @font-face e retorna a URL TTF/OTF do peso solicitado."""
    blocks = re.findall(r'@font-face\s*\{([^}]+)\}', css, re.DOTALL)
    for block in blocks:
        m_peso = re.search(r'font-weight:\s*(\d+)', block)
        if not m_peso or int(m_peso.group(1)) != peso:
            continue
        for ext in ("ttf", "otf"):
            m_url = re.search(rf'url\((https://[^)]+\.{ext})\)', block)
            if m_url:
                return m_url.group(1)
    return None


def _tentar_baixar_fonte(nome: str, peso: int = 400) -> Path | None:
    """Baixa TTF/OTF do Google Fonts para o peso especificado (400=regular, 700=bold)."""
    FONTES_DIR.mkdir(parents=True, exist_ok=True)

    sufixo = "bold" if peso >= 600 else "regular"
    for ext in ("ttf", "otf"):
        p = FONTES_DIR / f"{nome.replace(' ', '_')}_{sufixo}.{ext}"
        if p.exists():
            return p

    familia = nome.replace(' ', '+')
    # Pede ambos os pesos de uma vez — a resposta CSS terá dois blocos @font-face
    endpoints = [
        f"https://fonts.googleapis.com/css2?family={familia}:wght@400;700&display=swap",
        f"https://fonts.googleapis.com/css2?family={familia}:wght@{peso}&display=swap",
        f"https://fonts.googleapis.com/css?family={familia}",
    ]

    for ua in _USER_AGENTS:
        headers = {"User-Agent": ua}
        for url in endpoints:
            try:
                css = requests.get(url, timeout=10, headers=headers).text
                # Tenta URL exata para o peso pedido
                font_url = _extrair_url_por_peso(css, peso)
                # Fallback: qualquer TTF/OTF presente no CSS
                if not font_url:
                    for ext in ("ttf", "otf"):
                        matches = re.findall(rf"url\((https://[^)]+\.{ext})\)", css)
                        if matches:
                            font_url = matches[0]
                            break
                if font_url:
                    ext = "otf" if font_url.endswith(".otf") else "ttf"
                    data = requests.get(font_url, timeout=15).content
                    out = FONTES_DIR / f"{nome.replace(' ', '_')}_{sufixo}.{ext}"
                    out.write_bytes(data)
                    print(f"[Imagens] Fonte '{nome}' peso={peso} baixada ({ext}).")
                    return out
            except Exception:
                continue
    return None


def _fonte_cache_parcial(nome: str, peso: int = 400) -> Path | None:
    """Procura no cache o arquivo com sufixo correto (regular/bold)."""
    if not FONTES_DIR.exists():
        return None
    sufixo   = "bold" if peso >= 600 else "regular"
    nome_norm = nome.lower().replace(' ', '_')
    for f in FONTES_DIR.glob("*.ttf"):
        if nome_norm in f.stem.lower() and sufixo in f.stem.lower():
            print(f"[Imagens] Cache: '{f.name}'")
            return f
    return None


def baixar_fonte(nome: str, peso: int = 400) -> Path | None:
    """Baixa TTF do Google Fonts com múltiplos fallbacks."""
    candidato = _limpar_nome_fonte(nome, remover_peso=False)
    path = _fonte_cache_parcial(candidato, peso) or _tentar_baixar_fonte(candidato, peso)
    if path:
        return path
    candidato2 = _limpar_nome_fonte(nome, remover_peso=True)
    if candidato2 != candidato:
        path = _fonte_cache_parcial(candidato2, peso) or _tentar_baixar_fonte(candidato2, peso)
        if path:
            return path
    print(f"[Imagens] TTF não encontrado para '{nome}' peso={peso}")
    return None


_FONTES_SISTEMA = [
    "arial.ttf", "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]


def _carregar_fonte(nome: str | None, tamanho: int, negrito: bool = False) -> ImageFont.FreeTypeFont:
    if nome:
        peso = 700 if negrito else 400
        path = baixar_fonte(nome, peso=peso)
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
        f"Pure visual scene, absolutely NO text NO letters NO words NO numbers NO labels anywhere. "
        f"{prompt_imagem} "
        f"{estilo_imagem} "
        f"Brand color palette: {hexes or 'dark navy blue and white'}. "
        f"High resolution, suitable for a LinkedIn carousel slide background. "
        f"Do not include any typography, signage, screens with text, or written content of any kind."
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
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                    ),
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

def _gradiente_lateral(largura: int, altura: int, cor: tuple[int, int, int],
                       alpha_esq: int = 200, ponto_fade: float = 0.55) -> Image.Image:
    """Gradiente horizontal: esquerda (cor primária opaco) → direita (transparente)."""
    fade_start = int(largura * ponto_fade)
    fade_width = max(largura - fade_start, 1)
    grad_linha = Image.new("L", (largura, 1))
    for x in range(largura):
        if x <= fade_start:
            a = alpha_esq
        else:
            t = (x - fade_start) / fade_width
            a = int(alpha_esq * (1 - t))
        grad_linha.putpixel((x, 0), a)
    alpha_layer = grad_linha.resize((largura, altura), Image.BILINEAR)
    camada = Image.new("RGBA", (largura, altura), (*cor, 0))
    camada.putalpha(alpha_layer)
    return camada


def _gradiente_preto(largura: int, altura: int, alpha_topo: int = 60, alpha_base: int = 255,
                     inicio_rel: float = 0.0) -> Image.Image:
    """Cria uma camada RGBA preta com gradiente vertical (curva exponencial).
    inicio_rel define a partir de qual fração da imagem o gradiente começa (0.0 = topo, 1.0 = base)."""
    inicio_px = int(altura * inicio_rel)
    zona_h    = altura - inicio_px
    gradiente = Image.new("L", (1, altura))
    for y in range(altura):
        if y < inicio_px:
            a = 0
        else:
            t = (y - inicio_px) / max(zona_h - 1, 1)
            a = int(alpha_topo + (alpha_base - alpha_topo) * (t ** 0.55))
        gradiente.putpixel((0, y), min(255, a))
    gradiente = gradiente.resize((largura, altura), Image.BILINEAR)
    camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    camada.putalpha(gradiente)
    return camada


def _crop_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Escala e recorta centralmente para cobrir as dimensões alvo sem barras."""
    src_w, src_h = img.size
    escala = max(target_w / src_w, target_h / src_h)
    new_w = round(src_w * escala)
    new_h = round(src_h * escala)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _lh(draw: ImageDraw.ImageDraw, texto: str, font) -> int:
    """Altura real do glifo: bottom - top do bounding box."""
    bb = draw.textbbox((0, 0), texto, font=font)
    return bb[3] - bb[1]


_CAPA_BLK_PAD_V = 14   # padding vertical em cada bloco do título da capa
_CAPA_BLK_GAP   = 12   # espaçamento entre blocos do título da capa


def _textura_ruidosa(largura: int, altura: int, cor: tuple[int, int, int], sigma: int = 18) -> Image.Image:
    """Retorna imagem RGB com a cor base mesclada com granulação sutil (noise)."""
    base = Image.new("RGB", (largura, altura), cor)
    if largura < 1 or altura < 1:
        return base
    ruido = Image.effect_noise((largura, altura), sigma).convert("RGB")
    return Image.blend(base, ruido, 0.20)


def _aplicar_texto_texturizado(canvas: Image.Image, linha: str,
                                font: ImageFont.FreeTypeFont,
                                x: int, y: int,
                                cor: tuple[int, int, int]) -> Image.Image:
    """Aplica texto com preenchimento texturizado (cor + ruído granulado) sobre canvas."""
    textura = _textura_ruidosa(SLIDE_W, SLIDE_H, cor)
    mascara = Image.new("L", (SLIDE_W, SLIDE_H), 0)
    ImageDraw.Draw(mascara).text((x, y), linha, font=font, fill=255)
    textura_rgba = textura.convert("RGBA")
    textura_rgba.putalpha(mascara)
    base_rgba = canvas.convert("RGBA")
    base_rgba.alpha_composite(textura_rgba)
    return base_rgba.convert("RGB")


def _renderizar_blocos_capa(
    canvas: Image.Image,
    linhas_titulo: list[str],
    linhas_corpo: list[str],
    f_titulo: ImageFont.FreeTypeFont,
    f_corpo: ImageFont.FreeTypeFont,
    cor_primaria: tuple[int, int, int],
    cor_secundaria: tuple[int, int, int],
    y_inicio: int,
    sep_h: int = 24,
) -> Image.Image:
    """Capa: blocos de cor primária com texto texturizado cor-secundária + descrição bold centralizada."""
    shadow_dx, shadow_dy = 5, 6
    shadow_alpha = 102  # ~40% de 255
    shadow_cor = tuple(max(0, int(c * 0.35)) for c in cor_primaria)

    draw_tmp = ImageDraw.Draw(canvas)
    y = y_inicio

    # Cada bloco tem largura proporcional ao seu próprio texto (15% padding lateral)
    larguras_texto = [int(draw_tmp.textlength(l, font=f_titulo)) for l in linhas_titulo]

    for i, linha in enumerate(linhas_titulo):
        tw_linha = larguras_texto[i]
        pad_lat  = int(tw_linha * 0.15)
        bw       = tw_linha + pad_lat * 2
        bx       = (SLIDE_W - bw) // 2
        bh       = _lh(draw_tmp, linha, f_titulo) + _CAPA_BLK_PAD_V * 2

        # Sombra projetada (levemente para baixo e direita, 40% opacidade)
        sombra = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rounded_rectangle(
            [bx + shadow_dx, y + shadow_dy,
             bx + bw + shadow_dx, y + bh + shadow_dy],
            radius=6, fill=(*shadow_cor, shadow_alpha),
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), sombra).convert("RGB")

        # Bloco de fundo com cor primária
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([bx, y, bx + bw, y + bh], radius=6, fill=cor_primaria)

        # Texto centralizado dentro do bloco com preenchimento texturizado
        text_x = bx + pad_lat
        canvas = _aplicar_texto_texturizado(
            canvas, linha, f_titulo, text_x, y + _CAPA_BLK_PAD_V, cor_secundaria,
        )
        draw_tmp = ImageDraw.Draw(canvas)

        y += bh + (_CAPA_BLK_GAP if i < len(linhas_titulo) - 1 else 0)

    y += sep_h

    # Descrição: centralizada e em negrito
    draw = ImageDraw.Draw(canvas)
    for linha in linhas_corpo:
        lw = int(draw.textlength(linha, font=f_corpo))
        draw.text(((SLIDE_W - lw) // 2, y), linha, font=f_corpo, fill=(255, 255, 255))
        y += _lh(draw, linha, f_corpo) + 7

    return canvas


# Variantes de design por número de slide (1-based)
_VARIANTES_SLIDES = {2: "A", 5: "B", 7: "C"}


def compor_slide(titulo: str, texto: str, fundo_bytes: bytes,
                 nome_fonte: str | None, *,
                 logo_path: Path | None = None,
                 url_site: str = "",
                 cor_primaria: tuple[int, int, int] = (255, 255, 255),
                 cor_secundaria: tuple[int, int, int] = (255, 255, 255),
                 is_ultimo: bool = False,
                 variante: str | None = None,
                 slide_num: int = 0,
                 texto_passe: str = "Passe para o lado") -> Image.Image:
    fundo  = Image.open(BytesIO(fundo_bytes)).convert("RGBA")
    fundo  = _crop_cover(fundo, SLIDE_W, SLIDE_H)

    pad    = 64
    SEP_H  = 24
    _pill_h_bottom = int(SLIDE_W * 0.07)
    _bottom_pad    = 60
    _gap_lettering = 32
    _y_rodape      = SLIDE_H - _bottom_pad - _pill_h_bottom - 16 - _gap_lettering

    # flags de decoração renderizadas no momento do texto
    _accent_bar = False   # A3: barra cor primária acima do título
    _tag_acima  = False   # B2: pílula decorativa acima do título
    _linha_sep  = False   # B2: linha accent entre título e corpo

    # ─── Canvas e parâmetros de layout por variante ──────────────────────────
    _is_capa = (slide_num == 1 and variante is None)

    if variante == "C":
        canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H))
        canvas.paste(Image.new("RGBA", (SLIDE_W // 2, SLIDE_H), (*cor_primaria, 255)), (0, 0))
        canvas.paste(fundo.crop((SLIDE_W // 4, 0, SLIDE_W * 3 // 4, SLIDE_H)), (SLIDE_W // 2, 0))
        canvas = canvas.convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W // 2 - pad - 32, False, "centro"

    elif variante == "C1":
        # Diagonal split com borda branca na diagonal
        tilt    = 160
        x_split = int(SLIDE_W * 0.52)
        canvas  = Image.new("RGBA", (SLIDE_W, SLIDE_H))
        lmask   = Image.new("L", (SLIDE_W, SLIDE_H), 0)
        rmask   = Image.new("L", (SLIDE_W, SLIDE_H), 0)
        ImageDraw.Draw(lmask).polygon([(0,0),(x_split,0),(x_split-tilt,SLIDE_H),(0,SLIDE_H)], fill=255)
        ImageDraw.Draw(rmask).polygon([(x_split,0),(SLIDE_W,0),(SLIDE_W,SLIDE_H),(x_split-tilt,SLIDE_H)], fill=255)
        canvas.paste(Image.new("RGBA",(SLIDE_W,SLIDE_H),(*cor_primaria,255)), mask=lmask)
        canvas.paste(fundo, mask=rmask)
        canvas = canvas.convert("RGB")
        ImageDraw.Draw(canvas).line([(x_split,0),(x_split-tilt,SLIDE_H)], fill=(255,255,255), width=3)
        max_w, centrar_h, posicao = x_split - tilt - pad * 2, False, "centro"

    elif variante == "C2":
        # Overlap: bloco de cor 65% esquerda, imagem 35% direita
        split_x = int(SLIDE_W * 0.65)
        canvas  = Image.new("RGBA", (SLIDE_W, SLIDE_H))
        canvas.paste(Image.new("RGBA", (split_x, SLIDE_H), (*cor_primaria, 255)), (0, 0))
        canvas.paste(fundo.crop((split_x, 0, SLIDE_W, SLIDE_H)), (split_x, 0))
        canvas = canvas.convert("RGB")
        max_w, centrar_h, posicao = split_x - pad * 2, False, "centro"

    elif variante == "C3":
        # Canto: imagem + overlay + triângulo da cor primária no canto inferior esquerdo
        dark   = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=50, alpha_base=170, inicio_rel=0.0)
        canvas = Image.alpha_composite(fundo, dark)
        tri    = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
        tri_w  = int(SLIDE_W * 0.72)
        tri_h  = int(SLIDE_H * 0.52)
        ImageDraw.Draw(tri).polygon(
            [(0, SLIDE_H - tri_h), (tri_w, SLIDE_H), (0, SLIDE_H)],
            fill=(*cor_primaria, 230),
        )
        canvas = Image.alpha_composite(canvas, tri).convert("RGB")
        max_w, centrar_h, posicao = int(tri_w * 0.50) - pad, False, "base"

    elif variante == "B":
        overlay = Image.new("RGBA", (SLIDE_W, SLIDE_H), (*cor_primaria, 178))
        canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, True, "centro"

    elif variante == "B1":
        # Duotone: escala de cinza + tint da cor primária
        gray   = fundo.convert("L").convert("RGBA")
        tint   = Image.new("RGBA", (SLIDE_W, SLIDE_H), (*cor_primaria, 150))
        canvas = Image.alpha_composite(gray, tint)
        dark   = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=150, inicio_rel=0.30)
        canvas = Image.alpha_composite(canvas, dark).convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, True, "centro"

    elif variante == "B2":
        # Tag + linha: overlay escuro + pílula accent + linha entre título e corpo
        overlay = Image.new("RGBA", (SLIDE_W, SLIDE_H), (8, 12, 22, 210))
        canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, True, "centro"
        _tag_acima = True
        _linha_sep = True

    elif variante == "B3":
        # Número grande decorativo em background
        overlay = Image.new("RGBA", (SLIDE_W, SLIDE_H), (8, 12, 22, 215))
        canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
        f_num   = _carregar_fonte(nome_fonte, 400, negrito=True)
        num_txt = str(slide_num).zfill(2) if slide_num > 0 else "0"
        num_layer = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
        nd = ImageDraw.Draw(num_layer)
        num_w  = int(nd.textlength(num_txt, font=f_num))
        num_bb = nd.textbbox((0, 0), num_txt, font=f_num)
        num_h  = num_bb[3] - num_bb[1]
        nd.text(((SLIDE_W - num_w) // 2, (SLIDE_H - num_h) // 2 - 40),
                num_txt, font=f_num, fill=(*cor_primaria, 30))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), num_layer).convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, True, "centro"

    elif variante == "A":
        dark    = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=30, alpha_base=100, inicio_rel=0.0)
        canvas  = Image.alpha_composite(fundo, dark)
        lateral = _gradiente_lateral(SLIDE_W, SLIDE_H, cor_primaria)
        canvas  = Image.alpha_composite(canvas, lateral).convert("RGB")
        max_w, centrar_h, posicao = int(SLIDE_W * 0.55) - pad, False, "centro"

    elif variante == "A1":
        # Blade diagonal: polígono inclinado da cor primária cobre lado esquerdo
        dark   = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 20, 140))
        canvas = Image.alpha_composite(fundo, dark)
        blade  = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
        tilt   = 220
        x_split = int(SLIDE_W * 0.60)
        ImageDraw.Draw(blade).polygon(
            [(0, 0), (x_split, 0), (x_split - tilt, SLIDE_H), (0, SLIDE_H)],
            fill=(*cor_primaria, 210),
        )
        canvas = Image.alpha_composite(canvas, blade).convert("RGB")
        max_w, centrar_h, posicao = int((x_split - tilt - pad * 2) * 1.10), False, "centro"

    elif variante == "A2":
        # Frame: gradiente escuro + borda interna arredondada da cor primária
        overlay = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=230, inicio_rel=0.20)
        canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
        inset   = 30
        ImageDraw.Draw(canvas).rounded_rectangle(
            [inset, inset, SLIDE_W - inset, SLIDE_H - inset],
            radius=20, outline=cor_primaria, width=4,
        )
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, False, "base"

    elif variante == "A3":
        # Accent bar: gradiente + barra horizontal da cor primária acima do título
        overlay = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=230, inicio_rel=0.25)
        canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
        max_w, centrar_h, posicao = SLIDE_W - pad * 2, False, "base"
        _accent_bar = True

    else:
        if _is_capa:
            # Capa: preto sólido abaixo, fade nos primeiros 40% da altura
            fade_px = int(SLIDE_H * 0.8)
            _lyr = Image.new("L", (1, SLIDE_H))
            for _yi in range(SLIDE_H):
                _a = min(255, int(255 * _yi / fade_px)) if _yi < fade_px else 255
                _lyr.putpixel((0, _yi), _a)
            _lyr = _lyr.resize((SLIDE_W, SLIDE_H), Image.BILINEAR)
            _overlay = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
            _overlay.putalpha(_lyr)
            canvas  = Image.alpha_composite(fundo, _overlay).convert("RGB")
            max_w   = int(SLIDE_W * 0.60)
            centrar_h, posicao = True, "centro"
        else:
            overlay = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=255, inicio_rel=0.30)
            canvas  = Image.alpha_composite(fundo, overlay).convert("RGB")
            max_w, centrar_h, posicao = SLIDE_W - pad * 2, is_ultimo, "base"

    draw    = ImageDraw.Draw(canvas)
    cor_txt = (255, 255, 255)

    if posicao == "base":
        Y_SAFE_TOP    = SLIDE_H - int(SLIDE_H * 0.50)
        Y_SAFE_BOTTOM = _y_rodape
    else:
        Y_SAFE_TOP    = 240
        Y_SAFE_BOTTOM = _y_rodape

    # Espaço reservado por decorações acima do título
    _tag_h = 26 if _tag_acima else 0

    espaco = Y_SAFE_BOTTOM - Y_SAFE_TOP - _tag_h
    y_max  = Y_SAFE_BOTTOM

    # ─── Escolhe tamanho de fonte ─────────────────────────────────────────────
    _CANDIDATOS = [(62, 34), (54, 30), (46, 26), (38, 22), (32, 18), (26, 15), (22, 13)]
    f_titulo = f_corpo = None
    linhas_titulo = linhas_corpo = []
    h_titulo_total = h_corpo_total = 0
    _usar_bullets = slide_num in _SLIDES_COM_BULLETS
    linhas_bullet_corpo: list[tuple[str, str]] | None = None

    for tam_t, tam_c in _CANDIDATOS:
        f_t = _carregar_fonte(nome_fonte, tam_t, negrito=True)
        f_c = _carregar_fonte(nome_fonte, tam_c, negrito=_is_capa)
        lt  = _quebrar_texto(titulo, f_t, max_w, draw)
        if _usar_bullets:
            lb = _linhas_bullet(texto, f_c, max_w, draw)
            lc = [l for _, l in lb]
        else:
            lb = None
            lc  = _quebrar_texto(texto,  f_c, max_w, draw)
        if _is_capa:
            h_t = (sum(_lh(draw, l, f_t) + _CAPA_BLK_PAD_V * 2 for l in lt)
                   + _CAPA_BLK_GAP * max(len(lt) - 1, 0))
        else:
            h_t = sum(_lh(draw, l, f_t) + 10 for l in lt)
        h_c = sum(_lh(draw, l, f_c) + 7  for l in lc)
        if h_t + SEP_H + h_c <= espaco:
            f_titulo, f_corpo = f_t, f_c
            linhas_titulo, linhas_corpo = lt, lc
            linhas_bullet_corpo = lb
            h_titulo_total, h_corpo_total = h_t, h_c
            break

    if f_titulo is None:
        tam_t, tam_c = _CANDIDATOS[-1]
        f_titulo = _carregar_fonte(nome_fonte, tam_t, negrito=True)
        f_corpo  = _carregar_fonte(nome_fonte, tam_c, negrito=_is_capa)
        linhas_titulo = _quebrar_texto(titulo, f_titulo, max_w, draw)
        if _usar_bullets:
            linhas_bullet_corpo = _linhas_bullet(texto, f_corpo, max_w, draw)
            linhas_corpo = [l for _, l in linhas_bullet_corpo]
        else:
            linhas_corpo  = _quebrar_texto(texto,  f_corpo,  max_w, draw)
        if _is_capa:
            h_titulo_total = (sum(_lh(draw, l, f_titulo) + _CAPA_BLK_PAD_V * 2 for l in linhas_titulo)
                              + _CAPA_BLK_GAP * max(len(linhas_titulo) - 1, 0))
        else:
            h_titulo_total = sum(_lh(draw, l, f_titulo) + 10 for l in linhas_titulo)
        h_corpo_total  = sum(_lh(draw, l, f_corpo)  + 7  for l in linhas_corpo)
        print(f"[Imagens] Aviso: texto excede espaço disponível ({espaco}px) — usando fonte mínima.")

    # ─── Posicionamento vertical ──────────────────────────────────────────────
    bloco_h = h_titulo_total + SEP_H + h_corpo_total + _tag_h

    if posicao == "base":
        y = max(y_max - bloco_h, Y_SAFE_TOP)
    else:
        y = (Y_SAFE_TOP + Y_SAFE_BOTTOM - bloco_h) // 2
        y = max(y, Y_SAFE_TOP)

    # ─── Decorações acima do título ────────────────────────────────────────────
    if _tag_acima:
        pill_w, pill_h_dec = 64, 8
        pill_x = pad + (max_w - pill_w) // 2 if centrar_h else pad
        draw.rounded_rectangle([pill_x, y, pill_x + pill_w, y + pill_h_dec], radius=4, fill=cor_primaria)
        y += pill_h_dec + 18

    if _accent_bar:
        bar_y = max(y - 16, 0)
        draw.rectangle([0, bar_y, SLIDE_W, bar_y + 8], fill=cor_primaria)

    # ─── Renderização do texto ─────────────────────────────────────────────────
    if _is_capa:
        canvas = _renderizar_blocos_capa(
            canvas, linhas_titulo, linhas_corpo,
            f_titulo, f_corpo, cor_primaria, cor_secundaria, y, SEP_H,
        )
    else:
        for linha in linhas_titulo:
            x = pad + (max_w - int(draw.textlength(linha, font=f_titulo))) // 2 if centrar_h else pad
            draw.text((x, y), linha, font=f_titulo, fill=cor_txt)
            y += _lh(draw, linha, f_titulo) + 10

        if _linha_sep:
            sep_x0 = pad + (max_w - int(draw.textlength(linhas_titulo[0] if linhas_titulo else "", font=f_titulo))) // 2 if centrar_h else pad
            draw.rectangle([sep_x0, y + 4, sep_x0 + min(max_w, 200), y + 7], fill=cor_primaria)

        y += SEP_H

        if linhas_bullet_corpo is not None:
            for prefix, linha in linhas_bullet_corpo:
                x = pad
                if prefix in ("✓", "✗"):
                    cor_prefix = (50, 220, 80) if prefix == "✓" else (220, 60, 60)
                    prefix_txt = prefix + " "
                    draw.text((x, y), prefix_txt, font=f_corpo, fill=cor_prefix)
                    prefix_w = int(draw.textlength(prefix_txt, font=f_corpo)) + 8
                    draw.text((x + prefix_w, y), linha, font=f_corpo, fill=cor_txt)
                else:
                    draw.text((x, y), linha, font=f_corpo, fill=cor_txt)
                y += _lh(draw, linha, f_corpo) + 7
        else:
            for linha in linhas_corpo:
                x = pad + (max_w - int(draw.textlength(linha, font=f_corpo))) // 2 if centrar_h else pad
                draw.text((x, y), linha, font=f_corpo, fill=cor_txt)
                y += _lh(draw, linha, f_corpo) + 7

    canvas = _desenhar_elementos_fixos(
        canvas, logo_path, url_site, cor_primaria, nome_fonte, is_ultimo,
        logo_alinhamento="esquerda" if variante == "C" else "direita" if variante == "C1" else "centro",
        texto_passe=texto_passe,
    )
    return canvas


def _desenhar_elementos_fixos(
    canvas: Image.Image,
    logo_path: Path | None,
    url_site: str,
    cor_primaria: tuple[int, int, int],
    nome_fonte: str | None,
    is_ultimo: bool,
    logo_alinhamento: str = "centro",   # "centro" ou "esquerda"
    texto_passe: str = "Passe para o lado",
) -> Image.Image:
    """Adiciona logo no topo, pill de URL no bottom-left e (exceto no último slide)
    'Passe para o lado' + seta no bottom-right."""

    # ── Logo no topo (centralizada ou alinhada à esquerda) ───────────────
    if logo_path and logo_path.exists():
        logo       = Image.open(logo_path).convert("RGBA")
        max_logo_w = int(SLIDE_W * 0.35)   # máx 35% da largura (~378 px)
        max_logo_h = 110                    # máx altura fixa — limita logos quadradas/altas
        escala     = min(max_logo_w / logo.width, max_logo_h / logo.height)
        new_w      = max(1, int(logo.width  * escala))
        new_h      = max(1, int(logo.height * escala))
        logo   = logo.resize((new_w, new_h), Image.LANCZOS)
        base   = canvas.convert("RGBA")
        if logo_alinhamento == "esquerda":
            logo_x = 40
        elif logo_alinhamento == "direita":
            logo_x = SLIDE_W - new_w - 64
        else:
            logo_x = (SLIDE_W - new_w) // 2
        base.paste(logo, (logo_x, 60), logo)
        canvas = base.convert("RGB")

    draw = ImageDraw.Draw(canvas)

    pad        = 64
    bottom_pad = 60
    pill_h     = int(SLIDE_W * 0.07)   # ~76 px
    pill_r     = pill_h // 2
    pill_cy    = SLIDE_H - bottom_pad - pill_r
    f_bottom   = _carregar_fonte(nome_fonte, 22)

    if is_ultimo:
        # ── CTA centralizado no último slide ────────────────────────────
        cta_texto = "FALE COM UM ESPECIALISTA"
        cta_bg    = (255, 255, 255)        # branco
        cta_fg    = (37, 99, 235)          # azul
        f_cta     = _carregar_fonte(nome_fonte, 26)
        h_pad_cta = 36
        cta_w  = int(draw.textlength(cta_texto, font=f_cta)) + h_pad_cta * 2
        cta_x0 = (SLIDE_W - cta_w) // 2
        cta_x1 = cta_x0 + cta_w
        draw.rounded_rectangle(
            [cta_x0, pill_cy - pill_r, cta_x1, pill_cy + pill_r],
            radius=pill_r, fill=cta_bg,
        )
        draw.text(
            ((cta_x0 + cta_x1) / 2, pill_cy),
            cta_texto, font=f_cta, fill=cta_fg, anchor="mm",
        )
        return canvas

    # ── Pill "url" no bottom-left (bordas brancas, fundo transparente) ───
    url_texto = _limpar_url(url_site) if url_site else ""
    if url_texto:
        h_pad   = 24
        pill_x0 = pad
        pill_y0 = pill_cy - pill_r
        pill_y1 = pill_cy + pill_r
        pill_x1 = pill_x0 + draw.textlength(url_texto, font=f_bottom) + h_pad * 2
        draw.rounded_rectangle(
            [pill_x0, pill_y0, pill_x1, pill_y1],
            radius=pill_r, outline=(255, 255, 255), width=2,
        )
        draw.text(
            ((pill_x0 + pill_x1) / 2, pill_cy),
            url_texto, font=f_bottom, fill=(255, 255, 255), anchor="mm",
        )

    # ── "Passe para o lado" (pill preenchida) + seta (todos exceto o último) ──
    if not is_ultimo:
        circle_r  = pill_r
        gap       = 0

        # Círculo da seta (canto direito)
        circle_cx = SLIDE_W - pad - circle_r
        circle_cy = pill_cy
        draw.ellipse(
            [circle_cx - circle_r, circle_cy - circle_r,
             circle_cx + circle_r, circle_cy + circle_r],
            fill=cor_primaria,
        )
        # Seta "→": corpo horizontal + cabeça em chevron
        arm     = int(circle_r * 0.38)   # braço grande do chevron
        shaft_l = int(circle_r * 0.20)   # corpo
        lw      = 2
        # Centraliza a seta no círculo: tip_x = cx + metade da largura total
        tip_x    = circle_cx + (arm + shaft_l) // 2
        shaft_x0 = tip_x - arm - shaft_l
        # Corpo minúsculo
        draw.line([(shaft_x0, circle_cy), (tip_x, circle_cy)],
                  fill=(255, 255, 255), width=lw)
        # Cabeça em chevron grande
        draw.line([(tip_x - arm, circle_cy - arm), (tip_x, circle_cy)],
                  fill=(255, 255, 255), width=lw)
        draw.line([(tip_x, circle_cy), (tip_x - arm, circle_cy + arm)],
                  fill=(255, 255, 255), width=lw)

        # Pill "Passe para o lado" preenchida com cor primária
        h_pad_passe = 20
        passe_w     = draw.textlength(texto_passe, font=f_bottom) + h_pad_passe * 2
        passe_x1    = circle_cx - circle_r - gap
        passe_x0    = passe_x1 - passe_w
        draw.rounded_rectangle(
            [passe_x0, pill_cy - pill_r, passe_x1, pill_cy + pill_r],
            radius=pill_r, fill=cor_primaria,
        )
        draw.text(
            ((passe_x0 + passe_x1) / 2, pill_cy),
            texto_passe, font=f_bottom, fill=(255, 255, 255), anchor="mm",
        )

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
    logo_index: int = 1,
) -> list[Path]:
    """
    Gera uma imagem PNG por slide.
    callback(n_atual, total) chamado após cada slide.
    Retorna lista de paths salvos.
    """
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores      = identidade_visual.get("primarias", [])
    cores_sec  = identidade_visual.get("secundarias", [])
    fontes     = identidade_visual.get("fontes", [])
    fonte      = fontes[0] if fontes else None
    logo_p     = logo_empresa(empresa_id, logo_index)
    url_site   = identidade_visual.get("url_site", "")
    cor_prim   = _primeira_cor(cores)
    cor_sec    = _segunda_cor(cores_sec)

    paths  = []
    estilo = identidade_visual.get("estilo_imagem", "")
    total  = len(slides)
    for i, slide in enumerate(slides):
        n    = slide.get("slide", i + 1)
        dest = pasta / f"slide_{n:02d}.png"

        prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
        variante = _VARIANTES_SLIDES.get(n)
        print(f"[Imagens] Slide {n}/{total}: {slide['titulo']}" + (f" [variante {variante}]" if variante else ""))
        fundo  = _gerar_fundo(prompt_imagem, estilo, cores)
        imagem = compor_slide(
            slide["titulo"], slide["texto"], fundo, fonte,
            logo_path=logo_p, url_site=url_site,
            cor_primaria=cor_prim, cor_secundaria=cor_sec,
            is_ultimo=(i == total - 1),
            variante=variante,
            slide_num=n,
        )
        imagem.save(str(dest), "PNG")
        paths.append(dest)

        if callback:
            callback(i + 1, total)

    return paths


def gerar_imagem_slide(slide: dict, empresa_id: str, stem: str,
                       identidade_visual: dict, is_ultimo: bool = False,
                       variante_override: str | None = None,
                       logo_index: int = 1) -> Path:
    """Regenera a imagem de um único slide, sobrescrevendo o arquivo existente."""
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores    = identidade_visual.get("primarias", [])
    cores_sec = identidade_visual.get("secundarias", [])
    fontes   = identidade_visual.get("fontes", [])
    fonte    = fontes[0] if fontes else None
    estilo   = identidade_visual.get("estilo_imagem", "")
    logo_p   = logo_empresa(empresa_id, logo_index)
    url_site = identidade_visual.get("url_site", "")
    cor_prim = _primeira_cor(cores)
    cor_sec  = _segunda_cor(cores_sec)

    n        = slide.get("slide", 1)
    dest     = pasta / f"slide_{n:02d}.png"
    variante = variante_override if variante_override is not None else _VARIANTES_SLIDES.get(n)

    prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
    print(f"[Imagens] Regenerando slide {n}: {slide['titulo']}" + (f" [variante {variante}]" if variante else ""))
    fundo  = _gerar_fundo(prompt_imagem, estilo, cores)
    imagem = compor_slide(
        slide["titulo"], slide["texto"], fundo, fonte,
        logo_path=logo_p, url_site=url_site,
        cor_primaria=cor_prim, cor_secundaria=cor_sec,
        is_ultimo=is_ultimo,
        variante=variante,
        slide_num=n,
    )
    imagem.save(str(dest), "PNG")
    return dest


def listar_imagens(empresa_id: str, stem: str) -> list[Path]:
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    if not pasta.exists():
        return []
    return sorted(pasta.glob("slide_*.png"), key=lambda p: int(p.stem.split("_")[-1]))


# ─────────────────────────────────────────────
# Carrossel Tweet — slide limpo fundo branco
# ─────────────────────────────────────────────

_VERIFICADO_PATH         = LOGOS_DIR / "verificado.png"
_ARRASTE_ICONE_PATH      = LOGOS_DIR / "arraste_icone.png"
_SLIDES_COM_IMAGEM_TWEET = frozenset({3, 5, 7})  # slides que recebem imagem IA horizontal
_TWEET_IMG_H           = 360   # altura da faixa de imagem horizontal (px)
_TWEET_IMG_BORDER_R    = 5     # border-radius da imagem (px)


def _desenhar_badge_verificado(
    draw: ImageDraw.ImageDraw,
    cx: int, cy: int, raio: int,
    cor_badge: tuple[int, int, int],
) -> None:
    """Fallback: desenha círculo colorido com checkmark branco."""
    draw.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], fill=cor_badge)
    ck = int(raio * 0.50)
    p1 = (cx - ck, cy)
    p2 = (cx - ck // 3, cy + int(ck * 0.65))
    p3 = (cx + ck, cy - int(ck * 0.55))
    draw.line([p1, p2], fill=(255, 255, 255), width=max(2, raio // 6))
    draw.line([p2, p3], fill=(255, 255, 255), width=max(2, raio // 6))


def compor_slide_tweet(
    titulo: str,
    texto: str,
    empresa_nome: str,
    nome_fonte: str | None,
    *,
    logo_path: Path | None = None,
    cor_primaria: tuple[int, int, int] = (29, 155, 240),
    cor_circulo: tuple[int, int, int] = (29, 155, 240),
    imagem_bytes: bytes | None = None,
    slide_num: int = 0,
) -> Image.Image:
    """Slide no estilo Tweet: fundo branco, logo em círculo, nome+@handle+badge,
    título bold, descrição. Bloco inteiro centralizado verticalmente."""
    canvas = Image.new("RGB", (SLIDE_W, SLIDE_H), (255, 255, 255))
    draw   = ImageDraw.Draw(canvas)

    PAD           = 72
    COR_TITULO    = (15, 20, 30)
    COR_DESC      = (80, 90, 100)
    COR_HANDLE    = (120, 130, 140)
    LOGO_CIRCLE_R = 50
    HEADER_GAP    = 36     # gap entre o header e o título
    LINHA_GAP     = 10
    TOP_MARGIN    = 60
    max_w         = SLIDE_W - PAD * 2
    _img_w        = max_w

    _usar_bullets = slide_num in _SLIDES_COM_BULLETS
    _is_capa_tw   = (slide_num == 1)

    # ── Fontes fixas do header ────────────────────────────────────────────────
    f_nome   = _carregar_fonte(nome_fonte, 36, negrito=True)
    f_handle = _carregar_fonte(nome_fonte, 28)

    nome_h    = _lh(draw, empresa_nome, f_nome)
    handle_h  = _lh(draw, "@" + empresa_nome, f_handle)
    handle_gap = 14
    # Nome + @handle formam um bloco; garante que caiba verticalmente no círculo
    nome_bloco_h = nome_h + handle_gap + handle_h
    header_area_h = max(LOGO_CIRCLE_R * 2, nome_bloco_h)

    # ── Espaço extra reservado para indicador "Arraste" na capa ──────────────
    ARRASTE_H = 110  # altura estimada do bloco "Arraste para o lado" (inclui gap acima)
    arraste_h = ARRASTE_H if _is_capa_tw else 0

    # ── Extra de imagem IA ────────────────────────────────────────────────────
    img_extra = (40 + _TWEET_IMG_H) if imagem_bytes else 0

    # ── Seleção do tamanho de fonte (cabe no espaço disponível) ──────────────
    # O espaço para o bloco de texto é o restante depois do header e extras
    espaco_texto = (SLIDE_H - 2 * TOP_MARGIN
                    - header_area_h - HEADER_GAP
                    - 20          # separador título→corpo
                    - img_extra
                    - arraste_h)

    f_titulo = f_corpo = None
    linhas_titulo = []
    linhas_corpo  = []
    linhas_bullet_corpo: list[tuple[str, str]] | None = None

    for tam in [44, 40, 36, 32, 28, 24]:
        f_t = _carregar_fonte(nome_fonte, tam, negrito=True)
        f_c = _carregar_fonte(nome_fonte, tam, negrito=False)
        lt  = _quebrar_texto(titulo, f_t, max_w, draw)
        if _usar_bullets:
            lb = _linhas_bullet(texto, f_c, max_w, draw)
            lc = [l for _, l in lb]
        else:
            lb = None
            lc = _quebrar_texto(texto, f_c, max_w, draw)
        h_t = sum(_lh(draw, l, f_t) + LINHA_GAP for l in lt)
        h_c = sum(_lh(draw, l, f_c) + LINHA_GAP for l in lc)
        if h_t + 20 + h_c <= espaco_texto:
            f_titulo, f_corpo = f_t, f_c
            linhas_titulo, linhas_corpo = lt, lc
            linhas_bullet_corpo = lb
            break

    if f_titulo is None:
        f_titulo = _carregar_fonte(nome_fonte, 24, negrito=True)
        f_corpo  = _carregar_fonte(nome_fonte, 24, negrito=False)
        linhas_titulo = _quebrar_texto(titulo, f_titulo, max_w, draw)
        if _usar_bullets:
            linhas_bullet_corpo = _linhas_bullet(texto, f_corpo, max_w, draw)
            linhas_corpo = [l for _, l in linhas_bullet_corpo]
        else:
            linhas_corpo = _quebrar_texto(texto, f_corpo, max_w, draw)

    # ── Calcula altura total do bloco para centralizar verticalmente ──────────
    h_titulo = sum(_lh(draw, l, f_titulo) + LINHA_GAP for l in linhas_titulo)
    h_corpo  = sum(_lh(draw, l, f_corpo)  + LINHA_GAP for l in linhas_corpo)

    total_h = (header_area_h
               + HEADER_GAP
               + h_titulo + 20 + h_corpo
               + img_extra
               + arraste_h)

    y_start = max(TOP_MARGIN, (SLIDE_H - total_h) // 2)

    # ── Seção 1: Círculo + Logo (com clip circular) + Nome + @handle + Badge ──
    circle_cy = y_start + LOGO_CIRCLE_R
    circle_cx = PAD + LOGO_CIRCLE_R

    draw.ellipse(
        [circle_cx - LOGO_CIRCLE_R, circle_cy - LOGO_CIRCLE_R,
         circle_cx + LOGO_CIRCLE_R, circle_cy + LOGO_CIRCLE_R],
        fill=cor_circulo,
    )

    if logo_path and logo_path.exists():
        logo    = Image.open(logo_path).convert("RGBA")
        max_dim = int(LOGO_CIRCLE_R * 2.24)
        escala  = min(max_dim / logo.width, max_dim / logo.height)
        new_w   = max(1, int(logo.width  * escala))
        new_h   = max(1, int(logo.height * escala))
        logo    = logo.resize((new_w, new_h), Image.LANCZOS)
        # Clip logo ao círculo
        circle_d    = LOGO_CIRCLE_R * 2
        cir_canvas  = Image.new("RGBA", (circle_d, circle_d), (*cor_circulo, 255))
        cir_mask    = Image.new("L",    (circle_d, circle_d), 0)
        ImageDraw.Draw(cir_mask).ellipse([0, 0, circle_d - 1, circle_d - 1], fill=255)
        cir_canvas.paste(logo, ((circle_d - new_w) // 2, (circle_d - new_h) // 2), logo)
        cir_canvas.putalpha(cir_mask)
        base = canvas.convert("RGBA")
        base.paste(cir_canvas, (circle_cx - LOGO_CIRCLE_R, circle_cy - LOGO_CIRCLE_R), cir_canvas)
        canvas = base.convert("RGB")
        draw   = ImageDraw.Draw(canvas)

    # Nome + @handle à direita do círculo, centralizados verticalmente
    nome_x   = circle_cx + LOGO_CIRCLE_R + 20
    bloco_y  = circle_cy - nome_bloco_h // 2
    nome_y   = bloco_y
    handle_y = bloco_y + nome_h + handle_gap

    draw.text((nome_x, nome_y), empresa_nome, font=f_nome, fill=(0, 0, 0))

    # @ handle
    draw.text((nome_x, handle_y), "@" + empresa_nome, font=f_handle, fill=COR_HANDLE)

    # Badge verificado ao lado do nome
    nome_w  = int(draw.textlength(empresa_nome, font=f_nome))
    badge_x = nome_x + nome_w + 10
    badge_y = nome_y
    if _VERIFICADO_PATH.exists():
        bimg  = Image.open(_VERIFICADO_PATH).convert("RGBA")
        b_esc = nome_h / bimg.height
        bimg  = bimg.resize((max(1, int(bimg.width * b_esc)), nome_h), Image.LANCZOS)
        base  = canvas.convert("RGBA")
        base.paste(bimg, (badge_x, badge_y), bimg)
        canvas = base.convert("RGB")
        draw   = ImageDraw.Draw(canvas)
    else:
        br = nome_h // 2
        _desenhar_badge_verificado(draw, badge_x + br, badge_y + br, br, cor_primaria)

    # ── Seção 2: Título (bold) ─────────────────────────────────────────────────
    y = y_start + header_area_h + HEADER_GAP

    for linha in linhas_titulo:
        draw.text((PAD, y), linha, font=f_titulo, fill=COR_TITULO)
        y += _lh(draw, linha, f_titulo) + LINHA_GAP

    y += 20   # separador título → descrição

    # ── Seção 3: Descrição (regular, com bullets se slides 2/4) ───────────────
    if linhas_bullet_corpo is not None:
        for prefix, linha in linhas_bullet_corpo:
            if prefix in ("✓", "✗"):
                cor_prefix = (50, 200, 80) if prefix == "✓" else (210, 55, 55)
                prefix_txt = prefix + " "
                draw.text((PAD, y), prefix_txt, font=f_corpo, fill=cor_prefix)
                prefix_w = int(draw.textlength(prefix_txt, font=f_corpo)) + 8
                draw.text((PAD + prefix_w, y), linha, font=f_corpo, fill=COR_DESC)
            else:
                draw.text((PAD, y), linha, font=f_corpo, fill=COR_DESC)
            y += _lh(draw, linha, f_corpo) + LINHA_GAP
    else:
        for linha in linhas_corpo:
            draw.text((PAD, y), linha, font=f_corpo, fill=COR_DESC)
            y += _lh(draw, linha, f_corpo) + LINHA_GAP

    # ── Seção 4 (slides 3,5,7): Imagem IA horizontal logo após a descrição ─────
    if imagem_bytes is not None:
        img_y    = y + 40
        img      = Image.open(BytesIO(imagem_bytes)).convert("RGB")
        img      = _crop_cover(img, _img_w, _TWEET_IMG_H)
        mask_img = Image.new("L", (_img_w, _TWEET_IMG_H), 0)
        ImageDraw.Draw(mask_img).rounded_rectangle(
            [0, 0, _img_w - 1, _TWEET_IMG_H - 1],
            radius=_TWEET_IMG_BORDER_R, fill=255,
        )
        img_rgba = img.convert("RGBA")
        img_rgba.putalpha(mask_img)
        base = canvas.convert("RGBA")
        base.paste(img_rgba, (PAD, img_y), img_rgba)
        canvas = base.convert("RGB")
        draw   = ImageDraw.Draw(canvas)
        y = img_y + _TWEET_IMG_H

    # ── Seção 5 (capa): "Arraste para o lado" + ícone ─────────────────────────
    if _is_capa_tw:
        f_arr   = _carregar_fonte(nome_fonte, 45)
        txt_arr = "Arraste para o lado"
        arr_h   = _lh(draw, txt_arr, f_arr)
        cy_arr  = y + (ARRASTE_H - arr_h) // 2 + arr_h // 2

        if _ARRASTE_ICONE_PATH.exists():
            icone  = Image.open(_ARRASTE_ICONE_PATH).convert("RGBA")
            ic_esc = arr_h / icone.height
            ic_w   = max(1, int(icone.width * ic_esc))
            icone  = icone.resize((ic_w, arr_h), Image.LANCZOS)
            txt_w  = int(draw.textlength(txt_arr, font=f_arr))
            total_w = txt_w + 12 + ic_w
            start_x = SLIDE_W - PAD - total_w   # alinhado à direita
            draw.text((start_x, cy_arr - arr_h // 2), txt_arr, font=f_arr, fill=COR_DESC)
            base = canvas.convert("RGBA")
            base.paste(icone, (start_x + txt_w + 12, cy_arr + 1), icone)
            canvas = base.convert("RGB")
        else:
            # Fallback: círculo desenhado com seta
            arr_r   = 28
            txt_w   = int(draw.textlength(txt_arr, font=f_arr))
            total_w = txt_w + 18 + arr_r * 2
            start_x = SLIDE_W - PAD - total_w   # alinhado à direita
            draw.text((start_x, cy_arr - arr_h // 2), txt_arr, font=f_arr, fill=COR_DESC)
            c_cx = start_x + txt_w + 18 + arr_r
            draw.ellipse([c_cx - arr_r, cy_arr - arr_r, c_cx + arr_r, cy_arr + arr_r], fill=cor_circulo)
            arm   = int(arr_r * 0.42)
            tip_x = c_cx + arm
            lw    = max(2, arr_r // 7)
            draw.line([(c_cx - arm, cy_arr), (tip_x, cy_arr)], fill=(255, 255, 255), width=lw)
            draw.line([(tip_x - arm // 2, cy_arr - arm // 2), (tip_x, cy_arr)], fill=(255, 255, 255), width=lw)
            draw.line([(tip_x, cy_arr), (tip_x - arm // 2, cy_arr + arm // 2)], fill=(255, 255, 255), width=lw)

    return canvas


def _gerar_fundo_tweet(slide: dict, identidade_visual: dict) -> bytes | None:
    """Gera imagem de fundo para slides com imagem no Carrossel Tweet. Retorna None se falhar."""
    prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
    estilo  = identidade_visual.get("estilo_imagem", "")
    cores   = identidade_visual.get("primarias", [])
    try:
        return _gerar_fundo(prompt_imagem, estilo, cores)
    except Exception as e:
        print(f"[Tweet] Erro ao gerar imagem para slide {slide.get('slide', '?')}: {e}")
        return None


_SLIDEFINAL_TWEET_PATH = Path("config/slidefinal-ts-tweet.png")


def gerar_imagens_carrossel_tweet(
    slides: list[dict],
    empresa_id: str,
    empresa_nome: str,
    stem: str,
    identidade_visual: dict,
    logo_index: int = 1,
    cor_circulo_hex: str = "#1d9bf0",
    callback: callable = None,
) -> list[Path]:
    """Gera slides do Carrossel Tweet (fundo branco, estilo Twitter).
    Slide 1 (capa): mesmo design tweet com indicador 'Arraste para o lado'.
    Slides 3, 5 e 7: recebem imagem IA horizontal.
    Slide 10: sempre o PNG estático config/slidefinal-ts-tweet.png.
    """
    pasta = OUTPUTS_DIR / empresa_id / "imagens_tweet" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores    = identidade_visual.get("primarias", [])
    fontes   = identidade_visual.get("fontes", [])
    fonte    = fontes[0] if fontes else None
    logo_p   = logo_empresa(empresa_id, logo_index)
    cor_prim = _primeira_cor(cores)
    cor_circ = _hex_para_rgb_tuple(cor_circulo_hex)

    paths = []
    total = len(slides) + 1   # +1 para o slide 10 estático
    for i, slide in enumerate(slides):
        n    = int(slide.get("slide", i + 1))   # garante int mesmo que o JSON retorne string
        dest = pasta / f"slide_{n:02d}.png"
        print(f"[Tweet] Gerando slide {n} → {dest.name}")

        fundo_bytes = None
        if n in _SLIDES_COM_IMAGEM_TWEET:
            print(f"[Tweet] Gerando imagem IA para slide {n}...")
            fundo_bytes = _gerar_fundo_tweet(slide, identidade_visual)

        imagem = compor_slide_tweet(
            slide["titulo"], slide.get("texto", ""), empresa_nome, fonte,
            logo_path=logo_p, cor_primaria=cor_prim, cor_circulo=cor_circ,
            imagem_bytes=fundo_bytes, slide_num=n,
        )

        imagem.save(str(dest), "PNG")
        paths.append(dest)
        if callback:
            callback(i + 1, total)

    # Slide 10: PNG estático
    dest_10 = pasta / "slide_10.png"
    if _SLIDEFINAL_TWEET_PATH.exists():
        img10 = Image.open(_SLIDEFINAL_TWEET_PATH).convert("RGB")
        img10 = _crop_cover(img10, SLIDE_W, SLIDE_H)
        img10.save(str(dest_10), "PNG")
    else:
        print(f"[Tweet] Aviso: {_SLIDEFINAL_TWEET_PATH} não encontrado — slide 10 omitido.")
    if dest_10.exists():
        paths.append(dest_10)
    if callback:
        callback(total, total)

    return paths


def gerar_imagem_slide_tweet(
    slide: dict,
    empresa_id: str,
    empresa_nome: str,
    stem: str,
    identidade_visual: dict,
    logo_index: int = 1,
    cor_circulo_hex: str = "#1d9bf0",
) -> Path:
    """Regenera a imagem de um único slide do Carrossel Tweet."""
    pasta = OUTPUTS_DIR / empresa_id / "imagens_tweet" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores    = identidade_visual.get("primarias", [])
    fontes   = identidade_visual.get("fontes", [])
    fonte    = fontes[0] if fontes else None
    logo_p   = logo_empresa(empresa_id, logo_index)
    cor_prim = _primeira_cor(cores)
    cor_circ = _hex_para_rgb_tuple(cor_circulo_hex)

    n    = int(slide.get("slide", 1))
    dest = pasta / f"slide_{n:02d}.png"
    print(f"[Tweet] Regenerando slide {n} → {dest.name}")

    fundo_bytes = None
    if n in _SLIDES_COM_IMAGEM_TWEET:
        print(f"[Tweet] Gerando imagem IA para slide {n}...")
        fundo_bytes = _gerar_fundo_tweet(slide, identidade_visual)

    imagem = compor_slide_tweet(
        slide["titulo"], slide.get("texto", ""), empresa_nome, fonte,
        logo_path=logo_p, cor_primaria=cor_prim, cor_circulo=cor_circ,
        imagem_bytes=fundo_bytes, slide_num=n,
    )

    imagem.save(str(dest), "PNG")
    return dest


def listar_imagens_tweet(empresa_id: str, stem: str) -> list[Path]:
    pasta = OUTPUTS_DIR / empresa_id / "imagens_tweet" / stem
    if not pasta.exists():
        return []
    return sorted(pasta.glob("slide_*.png"), key=lambda p: int(p.stem.split("_")[-1]))
