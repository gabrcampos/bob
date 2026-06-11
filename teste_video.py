import shutil
from pathlib import Path
from dotenv import load_dotenv

from modulos import voz, midia, editor
from modulos import llm_brain, broll as broll_mod

load_dotenv()


def testar_pipeline_video():
    empresa_id = "tecnosolve"
    stem       = "teste_remotion"
    roteiro    = "A falta de tecnologia gera ruptura na gôndola. Sem dados precisos, você perde vendas."

    # 1. Áudio + word timings
    print("1. Gerando áudio e timestamps...")
    caminho_audio, words_timings = voz.gerar_audio_e_timings(roteiro, empresa_id, stem)
    legendas = [{"word": w.word, "start": w.start, "end": w.end} for w in words_timings]

    # 2. Prompts de b-roll via LLM
    print("2. Gerando prompts de b-roll...")
    prompts_broll = llm_brain.gerar_prompts_broll(roteiro, words_timings)
    for p in prompts_broll:
        print(f"   [{p['start']:.1f}s-{p['end']:.1f}s] {p['frase']}")
        print(f"   -> {p['prompt_video']}")

    # 3. Clips de vídeo via Veo 3.1 Lite (~1-3 min por clip)
    print("3. Gerando clips de b-roll com Veo 3.1 Lite...")
    clips = broll_mod.gerar_videos_broll(prompts_broll, empresa_id, stem)

    # 4. Background estático (fallback entre clips / frame inicial)
    print("4. Gerando background estático...")
    identidade_visual = {
        "primarias": [{"hex": "#131b71", "rgb": "19, 27, 113"}],
        "fontes": ["Poppins", "Poppins"],
    }
    caminho_bg = midia.gerar_background_animacao_texto(identidade_visual, empresa_id, stem)

    # 5. Copia assets de áudio e background para public/
    print("5. Copiando assets para o Remotion...")
    pasta_public = Path("remotion_project/public")
    pasta_public.mkdir(exist_ok=True)
    shutil.copy(caminho_audio, pasta_public / f"{stem}.mp3")
    shutil.copy(caminho_bg,    pasta_public / f"{stem}_bg.png")

    # 6. Render (editor copia os clips de b-roll para public/broll/)
    print("6. Renderizando vídeo com Remotion...")
    editor.renderizar_video_remotion(
        tipo_video     = "TextoAnimado",
        audio_path     = f"{stem}.mp3",
        frases_timings = legendas,
        assets_path    = [f"{stem}_bg.png"],
        output_path    = f"outputs/{empresa_id}/videos/{stem}_final.mp4",
        opcoes_visuais = {
            "fontePrincipal": identidade_visual["fontes"][0],
            "corFundoTexto":  identidade_visual["primarias"][0]["hex"],
        },
        broll_clips = clips,
    )


if __name__ == "__main__":
    testar_pipeline_video()
