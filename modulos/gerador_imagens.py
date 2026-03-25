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

def logo_empresa(empresa_id: str) -> Path | None:
    """Retorna o path da logo da empresa se existir, None caso contrário."""
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"{empresa_id}.{ext}"
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


def compor_slide(titulo: str, texto: str, fundo_bytes: bytes,
                 nome_fonte: str | None, *,
                 logo_path: Path | None = None,
                 url_site: str = "",
                 cor_primaria: tuple[int, int, int] = (255, 255, 255),
                 is_ultimo: bool = False) -> Image.Image:
    # Fundo: cover-crop para preencher 1080×1350 sem barras nem distorção
    fundo = Image.open(BytesIO(fundo_bytes)).convert("RGBA")
    fundo  = _crop_cover(fundo, SLIDE_W, SLIDE_H)
    canvas = fundo.copy()

    # Gradiente preto: 0% opacidade no topo → 80% na base
    overlay = _gradiente_preto(SLIDE_W, SLIDE_H, alpha_topo=0, alpha_base=255, inicio_rel=0.30)
    canvas  = Image.alpha_composite(canvas, overlay).convert("RGB")

    draw    = ImageDraw.Draw(canvas)
    cor_txt = (255, 255, 255)
    pad     = 64
    max_w   = SLIDE_W - pad * 2
    _pill_h_bottom = int(SLIDE_W * 0.07)       # altura dos elementos do bottom (~76 px)
    _bottom_pad    = 60
    _gap_lettering = 32                            # gap fixo entre texto e elementos do rodapé
    y_max        = SLIDE_H - _bottom_pad - _pill_h_bottom - 16 - _gap_lettering
    _max_texto_h = int(SLIDE_H * 0.50)         # 675 px — bloco nunca sobe acima de 50% da imagem
    espaco       = _max_texto_h
    SEP_H        = 24                          # espaçamento entre título e corpo

    # Escolhe o maior tamanho de fonte em que título + sep + corpo cabem em 675 px
    f_titulo = f_corpo = None
    linhas_titulo = linhas_corpo = []
    h_titulo_total = h_corpo_total = 0
    for tam_t, tam_c in [(62, 34), (54, 30), (46, 26), (38, 22)]:
        f_t = _carregar_fonte(nome_fonte, tam_t, negrito=True)
        f_c = _carregar_fonte(nome_fonte, tam_c)
        lt  = _quebrar_texto(titulo, f_t, max_w, draw)[:3]
        lc  = _quebrar_texto(texto,  f_c, max_w, draw)[:7]
        h_t = sum(_lh(draw, l, f_t) + 10 for l in lt)
        h_c = sum(_lh(draw, l, f_c) + 7  for l in lc)
        if h_t + SEP_H + h_c <= espaco:
            f_titulo, f_corpo = f_t, f_c
            linhas_titulo, linhas_corpo = lt, lc
            h_titulo_total, h_corpo_total = h_t, h_c
            break

    # Fallback: usa menor tamanho mesmo que não caiba tudo
    if f_titulo is None:
        f_titulo = _carregar_fonte(nome_fonte, 38, negrito=True)
        f_corpo  = _carregar_fonte(nome_fonte, 22)
        linhas_titulo = _quebrar_texto(titulo, f_titulo, max_w, draw)[:3]
        linhas_corpo  = _quebrar_texto(texto,  f_corpo,  max_w, draw)[:7]
        h_titulo_total = sum(_lh(draw, l, f_titulo) + 10 for l in linhas_titulo)
        h_corpo_total  = sum(_lh(draw, l, f_corpo)  + 7  for l in linhas_corpo)

    # Posição bottom-anchored: texto flutua logo acima dos elementos fixos
    bloco_h    = h_titulo_total + SEP_H + h_corpo_total
    y_topo_min = SLIDE_H - _max_texto_h        # nunca acima de 50% da imagem
    y = max(y_max - bloco_h, y_topo_min)

    # Renderiza com hard-clip: para antes de ultrapassar y_max
    for linha in linhas_titulo:
        h = _lh(draw, linha, f_titulo)
        if y + h > y_max:
            break
        draw.text((pad, y), linha, font=f_titulo, fill=cor_txt)
        y += h + 10

    y += SEP_H  # espaçamento entre título e corpo (sem linha separadora)

    for linha in linhas_corpo:
        h = _lh(draw, linha, f_corpo)
        if y + h > y_max:
            break
        draw.text((pad, y), linha, font=f_corpo, fill=cor_txt)
        y += h + 7

    canvas = _desenhar_elementos_fixos(
        canvas, logo_path, url_site, cor_primaria, nome_fonte, is_ultimo
    )
    return canvas


def _desenhar_elementos_fixos(
    canvas: Image.Image,
    logo_path: Path | None,
    url_site: str,
    cor_primaria: tuple[int, int, int],
    nome_fonte: str | None,
    is_ultimo: bool,
) -> Image.Image:
    """Adiciona logo no topo, pill de URL no bottom-left e (exceto no último slide)
    'Passe para o lado' + seta no bottom-right."""

    # ── Logo centralizada no topo ────────────────────────────────────────
    if logo_path and logo_path.exists():
        logo   = Image.open(logo_path).convert("RGBA")
        max_w  = int(SLIDE_W * 0.40)               # 40% da largura (dobro do anterior)
        escala = min(max_w / logo.width, max_w / logo.height)
        new_w  = max(1, int(logo.width  * escala))
        new_h  = max(1, int(logo.height * escala))
        logo   = logo.resize((new_w, new_h), Image.LANCZOS)
        base   = canvas.convert("RGBA")
        base.paste(logo, ((SLIDE_W - new_w) // 2, 60), logo)
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
        cta_x0 = pad                       # alinhado à esquerda com o texto
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
        texto_passe = "Passe para o lado"
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
) -> list[Path]:
    """
    Gera uma imagem PNG por slide.
    callback(n_atual, total) chamado após cada slide.
    Retorna lista de paths salvos.
    """
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores      = identidade_visual.get("primarias", [])
    fontes     = identidade_visual.get("fontes", [])
    fonte      = fontes[0] if fontes else None
    logo_p     = logo_empresa(empresa_id)
    url_site   = identidade_visual.get("url_site", "")
    cor_prim   = _primeira_cor(cores)

    paths  = []
    estilo = identidade_visual.get("estilo_imagem", "")
    total  = len(slides)
    for i, slide in enumerate(slides):
        n    = slide.get("slide", i + 1)
        dest = pasta / f"slide_{n:02d}.png"

        prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
        print(f"[Imagens] Slide {n}/{total}: {slide['titulo']}")
        fundo  = _gerar_fundo(prompt_imagem, estilo, cores)
        imagem = compor_slide(
            slide["titulo"], slide["texto"], fundo, fonte,
            logo_path=logo_p, url_site=url_site,
            cor_primaria=cor_prim, is_ultimo=(i == total - 1),
        )
        imagem.save(str(dest), "PNG")
        paths.append(dest)

        if callback:
            callback(i + 1, total)

    return paths


def gerar_imagem_slide(slide: dict, empresa_id: str, stem: str,
                       identidade_visual: dict, is_ultimo: bool = False) -> Path:
    """Regenera a imagem de um único slide, sobrescrevendo o arquivo existente."""
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    pasta.mkdir(parents=True, exist_ok=True)

    cores    = identidade_visual.get("primarias", [])
    fontes   = identidade_visual.get("fontes", [])
    fonte    = fontes[0] if fontes else None
    estilo   = identidade_visual.get("estilo_imagem", "")
    logo_p   = logo_empresa(empresa_id)
    url_site = identidade_visual.get("url_site", "")
    cor_prim = _primeira_cor(cores)

    n    = slide.get("slide", 1)
    dest = pasta / f"slide_{n:02d}.png"

    prompt_imagem = slide.get("prompt_imagem") or slide.get("titulo", "")
    print(f"[Imagens] Regenerando slide {n}: {slide['titulo']}")
    fundo  = _gerar_fundo(prompt_imagem, estilo, cores)
    imagem = compor_slide(
        slide["titulo"], slide["texto"], fundo, fonte,
        logo_path=logo_p, url_site=url_site,
        cor_primaria=cor_prim, is_ultimo=is_ultimo,
    )
    imagem.save(str(dest), "PNG")
    return dest


def listar_imagens(empresa_id: str, stem: str) -> list[Path]:
    pasta = OUTPUTS_DIR / empresa_id / "imagens" / stem
    if not pasta.exists():
        return []
    return sorted(pasta.glob("slide_*.png"))
