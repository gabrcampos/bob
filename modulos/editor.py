import json
import subprocess
from pathlib import Path


def renderizar_video_remotion(
    tipo_video: str, 
    audio_path: str, 
    frases_timings: list[dict], 
    assets_path: list[str], 
    output_path: str,
    opcoes_visuais: dict = None
):
    """
    O Python prepara um JSON (props) e aciona o Remotion via CLI.
    tipo_video pode ser 'VideoComIA' ou 'TextoAnimado'.
    """
    print(f"[Editor] Preparando dados para renderização no Remotion...")
    
    # 1. Monta as Props (Dados que o React vai consumir para desenhar o vídeo)
    props = {
        "audioSrc": audio_path,
        "tipo": tipo_video,          # Diz pro Remotion qual composição usar
        "legendas": frases_timings,  # Ex: [{"texto": "A falta de TI...", "startFrame": 0, "endFrame": 120}]
        "assetsVisuais": assets_path, # Pode ser lista de vídeos IA ou a imagem de fundo do PIL
        "opcoesVisuais": opcoes_visuais or {}
    }
    
    props_file_rel = Path("public/current_props.json")
    props_file_abs = Path("remotion_project") / props_file_rel
    props_file_abs.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    
    # 2. Comando para o Remotion (precisa ter um projeto Remotion na pasta remotion_project)
    comando = [
        "npx", "remotion", "render", 
        "src/index.ts",         # Entrypoint do Remotion
        "ComposicaoPrincipal",  # Nome do comp no Remotion
        f"../{output_path}",    # Arquivo de saída (.mp4) voltando 1 nível para a pasta principal
        f"--props={str(props_file_rel)}"
    ]
    
    print("[Editor] Iniciando renderização...")
    subprocess.run(comando, cwd="remotion_project", shell=True, check=True)
    print(f"[Editor] Vídeo renderizado com sucesso em {output_path}")
