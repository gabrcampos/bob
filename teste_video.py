import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

from modulos import voz, midia, editor

# Carrega a OPENAI_API_KEY
load_dotenv()

def testar_pipeline_video():
    empresa_id = "tecnosolve"
    stem = "teste_remotion"
    roteiro = "A falta de tecnologia gera ruptura na gôndola. Sem dados precisos, você perde vendas."
    
    print("1. Gerando Áudio e Timestamps na OpenAI...")
    caminho_audio, words_timings = voz.gerar_audio_e_timings(roteiro, empresa_id, stem)
    
    # Formata as palavras exatamente como o React espera
    legendas = []
    for w in words_timings:
        legendas.append({
            "word": w.word,
            "start": w.start,
            "end": w.end
        })
        
    print("2. Gerando Background de Texto...")
    identidade_visual = {
        "primarias": [{"hex": "#131b71", "rgb": "19, 27, 113"}],
        "fontes": ["Poppins", "Poppins"]
    }
    caminho_bg = midia.gerar_background_animacao_texto(identidade_visual, empresa_id, stem)
    
    print("3. Movendo Assets para a pasta Public do Remotion...")
    pasta_public = Path("remotion_project/public")
    pasta_public.mkdir(exist_ok=True)
    
    shutil.copy(caminho_audio, pasta_public / f"{stem}.mp3")
    shutil.copy(caminho_bg, pasta_public / f"{stem}_bg.png")
    
    print("4. Chamando o Editor (Remotion Render)...")
    editor.renderizar_video_remotion(
        tipo_video="TextoAnimado",
        audio_path=f"{stem}.mp3",  # Remotion vai achar direto na pasta public
        frases_timings=legendas,
        assets_path=[f"{stem}_bg.png"],
        output_path=f"outputs/{empresa_id}/videos/{stem}_final.mp4",
        opcoes_visuais={
            "fontePrincipal": identidade_visual["fontes"][0],
            "corFundoTexto": identidade_visual["primarias"][0]["hex"]
        }
    )
    
if __name__ == "__main__":
    testar_pipeline_video()