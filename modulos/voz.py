import asyncio
import subprocess
from pathlib import Path

import edge_tts

OUTPUTS_DIR = Path("outputs")

# ffmpeg empacotado pelo Remotion (fallback quando não está no PATH)
_FFMPEG_REMOTION = Path("remotion_project/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe")


class WordTiming:
    """Timing de uma palavra individual."""
    def __init__(self, word: str, start: float, end: float):
        self.word  = word
        self.start = start  # segundos
        self.end   = end    # segundos


# ─────────────────────────────────────────────
# TTS (Edge TTS)
# ─────────────────────────────────────────────

def _palavras_de_sentencas(sentencas: list[tuple[float, float, str]]) -> list[WordTiming]:
    """
    Distribui palavras dentro de cada frase proporcionalmente ao número de caracteres.
    Usa os tempos reais de início/fim de cada frase do SentenceBoundary.
    """
    result = []
    for start_sec, end_sec, texto in sentencas:
        palavras = texto.split()
        if not palavras:
            continue
        total_chars = sum(len(p) for p in palavras)
        if total_chars == 0:
            continue
        duracao = end_sec - start_sec
        t = start_sec
        for palavra in palavras:
            dur_palavra = duracao * (len(palavra) / total_chars)
            result.append(WordTiming(palavra, t, t + dur_palavra))
            t += dur_palavra
    return result


async def _gerar_edge_tts(roteiro: str, caminho_audio: Path) -> list[WordTiming]:
    communicate = edge_tts.Communicate(roteiro, "pt-BR-AntonioNeural")
    word_timings: list[WordTiming] = []
    sentence_boundaries: list[tuple[float, float, str]] = []

    with open(caminho_audio, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Edge TTS < 7.x retorna word-level (100-nanosegundos → segundos)
                start = chunk["offset"] / 10_000_000.0
                end   = (chunk["offset"] + chunk["duration"]) / 10_000_000.0
                word_timings.append(WordTiming(chunk["text"], start, end))
            elif chunk["type"] == "SentenceBoundary":
                # Edge TTS 7.x retorna sentence-level
                start = chunk["offset"] / 10_000_000.0
                end   = (chunk["offset"] + chunk["duration"]) / 10_000_000.0
                sentence_boundaries.append((start, end, chunk["text"]))

    # Prioridade: WordBoundary > SentenceBoundary > fallback uniforme
    if word_timings:
        return word_timings

    if sentence_boundaries:
        timings = _palavras_de_sentencas(sentence_boundaries)
        if timings:
            print(f"[Voz] Usando SentenceBoundary ({len(sentence_boundaries)} frases, {len(timings)} palavras).")
            return timings

    print("[Voz] Aviso: sem timing events. Usando estimativa uniforme (fallback).")
    t = 0.0
    result = []
    for p in roteiro.split():
        result.append(WordTiming(p, t, t + 0.40))
        t += 0.45
    return result


# ─────────────────────────────────────────────
# Remoção de silêncios via ffmpeg
# ─────────────────────────────────────────────

def _ffmpeg_bin() -> str | None:
    """Retorna o caminho do ffmpeg disponível, ou None se não encontrado."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    if _FFMPEG_REMOTION.exists():
        return str(_FFMPEG_REMOTION)
    return None


def _detectar_silencias(
    ffmpeg: str,
    caminho_audio: Path,
    silence_thresh_db: int = -35,
    min_silence_ms: int = 300,
) -> list[tuple[float, float]]:
    """
    Usa ffmpeg silencedetect para encontrar silêncios reais no arquivo de áudio.
    Retorna lista de (start_s, end_s) de cada região silenciosa detectada.

    silence_thresh_db : nível abaixo do qual considera silêncio (padrão -35dB)
    min_silence_ms    : duração mínima para ser considerado silêncio
    """
    cmd = [
        ffmpeg, "-i", str(caminho_audio),
        "-af", f"silencedetect=noise={silence_thresh_db}dB:d={min_silence_ms / 1000:.3f}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")

    silences: list[tuple[float, float]] = []
    pending_start: float | None = None

    for line in result.stderr.splitlines():
        if "silence_start:" in line:
            try:
                pending_start = float(line.split("silence_start:")[-1].strip())
            except ValueError:
                pass
        elif "silence_end:" in line and pending_start is not None:
            try:
                end_str = line.split("silence_end:")[-1].split("|")[0].strip()
                silences.append((pending_start, float(end_str)))
                pending_start = None
            except ValueError:
                pass

    return silences


def _remover_silencias(
    caminho_audio: Path,
    timings: list[WordTiming],
    max_silence_ms: int = 350,
    silence_thresh_db: int = -35,
) -> tuple[Path, list[WordTiming]]:
    """
    Detecta silêncios reais no arquivo de áudio via ffmpeg silencedetect,
    remove o excesso (mantendo max_silence_ms de pausa natural) e ajusta
    todos os timestamps proporcionalmente.

    Por que silencedetect e não word timings:
    O SentenceBoundary do Edge TTS reporta quando o TTS processa a frase,
    não onde o silêncio físico está no áudio — o gap real só aparece no arquivo.
    """
    if not timings:
        return caminho_audio, timings

    ffmpeg = _ffmpeg_bin()
    if ffmpeg is None:
        print("[Voz] ffmpeg não encontrado — pulando remoção de silêncios.")
        return caminho_audio, timings

    # ── 1. Detecta onde os silêncios realmente estão no áudio ─────
    silences = _detectar_silencias(
        ffmpeg, caminho_audio,
        silence_thresh_db=silence_thresh_db,
        min_silence_ms=max_silence_ms,   # só detecta silêncios que vale cortar
    )

    if not silences:
        return caminho_audio, timings

    # ── 2. Calcula os cortes: mantém max_silence_ms, remove o resto ─
    max_s = max_silence_ms / 1000.0
    removals: list[tuple[float, float]] = []

    for sil_start, sil_end in silences:
        if sil_end - sil_start > max_s:
            removals.append((sil_start + max_s, sil_end))

    if not removals:
        return caminho_audio, timings

    # ── 3. Monta segmentos a MANTER e o comando ffmpeg ────────────
    keeps: list[tuple[float, float | None]] = []
    prev = 0.0
    for r_start, r_end in removals:
        keeps.append((prev, r_start))
        prev = r_end
    keeps.append((prev, None))

    n = len(keeps)
    parts: list[str] = []
    labels = ""
    for idx, (s, e) in enumerate(keeps):
        trim = f"atrim=start={s:.4f}" + (f":end={e:.4f}" if e is not None else "")
        parts.append(f"[0:a]{trim},asetpts=PTS-STARTPTS[a{idx}]")
        labels += f"[a{idx}]"

    filter_str = (
        parts[0].replace("[a0]", "[out]")
        if n == 1
        else ";".join(parts + [f"{labels}concat=n={n}:v=0:a=1[out]"])
    )

    tmp = caminho_audio.with_suffix(".tmp.mp3")
    cmd = [ffmpeg, "-y", "-i", str(caminho_audio),
           "-filter_complex", filter_str, "-map", "[out]", str(tmp)]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[Voz] ffmpeg falhou: {exc.stderr.decode(errors='replace')[:300]}")
        if tmp.exists():
            tmp.unlink()
        return caminho_audio, timings

    tmp.replace(caminho_audio)

    # ── 4. Ajusta os timestamps ────────────────────────────────────
    # Para cada palavra, subtrai o total removido antes do seu instante.
    def s_removidos_antes(t: float) -> float:
        total = 0.0
        for r_start, r_end in removals:
            if t >= r_end:
                total += r_end - r_start          # passou completamente pelo corte
            elif t > r_start:
                total += t - r_start              # dentro do corte → clamp ao início
        return total

    adjusted = [
        WordTiming(
            word  = wt.word,
            start = max(0.0, wt.start - s_removidos_antes(wt.start)),
            end   = max(0.0, wt.end   - s_removidos_antes(wt.end)),
        )
        for wt in timings
    ]

    removed_s = sum(e - s for s, e in removals)
    print(
        f"[Voz] Silêncios removidos: {removed_s * 1000:.0f}ms "
        f"({len(removals)} corte(s)) | "
        f"detectados: {[(f'{s:.2f}s-{e:.2f}s' ) for s, e in silences]}"
    )

    return caminho_audio, adjusted


# ─────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────

def gerar_audio_e_timings(
    roteiro: str,
    empresa_id: str,
    stem: str,
    remover_silencio: bool = True,
) -> tuple[Path, list[WordTiming]]:
    """
    Gera áudio MP3 + word-level timestamps via Edge TTS.
    Remove silêncios longos e ajusta os timestamps antes de retornar,
    garantindo que legendas e animações fiquem sincronizadas com o áudio final.
    """
    print(f"[Voz] Gerando áudio para: {empresa_id}...")
    pasta = OUTPUTS_DIR / empresa_id / "audio"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_audio = pasta / f"{stem}.mp3"

    timings = asyncio.run(_gerar_edge_tts(roteiro, caminho_audio))

    if remover_silencio:
        caminho_audio, timings = _remover_silencias(caminho_audio, timings)

    return caminho_audio, timings
