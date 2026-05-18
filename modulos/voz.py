import os
import asyncio
from pathlib import Path
import edge_tts

OUTPUTS_DIR = Path("outputs")

class WordTiming:
    """Classe auxiliar para manter a compatibilidade com a estrutura esperada pelo teste_video.py"""
    def __init__(self, word: str, start: float, end: float):
        self.word = word
        self.start = start
        self.end = end

async def _gerar_edge_tts(roteiro: str, caminho_audio: Path) -> list[WordTiming]:
    # pt-BR-AntonioNeural (Masculina) ou pt-BR-FranciscaNeural (Feminina)
    communicate = edge_tts.Communicate(roteiro, "pt-BR-AntonioNeural")
    words_timings = []
    
    with open(caminho_audio, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # O edge-tts retorna o tempo em unidades de 100-nanosegundos. 
                # Dividimos por 10.000.000 para converter para segundos.
                start_sec = chunk["offset"] / 10000000.0
                end_sec = (chunk["offset"] + chunk["duration"]) / 10000000.0
                words_timings.append(WordTiming(chunk["text"], start_sec, end_sec))
                
    # Fallback caso a API da Microsoft não retorne os timestamps (WordBoundary)
    if not words_timings:
        print("[Voz] Aviso: Timestamps não retornados. Usando estimativa de tempo (fallback).")
        palavras = roteiro.split()
        tempo_atual = 0.0
        for p in palavras:
            words_timings.append(WordTiming(p, tempo_atual, tempo_atual + 0.40))
            tempo_atual += 0.45
            
    return words_timings

def gerar_audio_e_timings(roteiro: str, empresa_id: str, stem: str) -> tuple[Path, list[WordTiming]]:
    """
    Gera áudio e timestamps 100% gratuitos usando o Edge TTS da Microsoft.
    """
    print(f"[Voz] Gerando áudio e timestamps gratuitos para: {empresa_id}...")
    pasta = OUTPUTS_DIR / empresa_id / "audio"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_audio = pasta / f"{stem}.mp3"
    
    # Como o edge-tts é assíncrono, rodamos no loop de eventos
    timings = asyncio.run(_gerar_edge_tts(roteiro, caminho_audio))
    
    return caminho_audio, timings
