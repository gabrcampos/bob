import json
import shutil
import subprocess
from pathlib import Path

FPS = 30


def renderizar_video_remotion(
    tipo_video: str,
    audio_path: str,
    frases_timings: list[dict],
    assets_path: list[str],
    output_path: str,
    opcoes_visuais: dict = None,
    broll_clips: list[dict] = None,
):
    """
    Prepara props JSON e aciona o Remotion via CLI.

    broll_clips: lista de {src (Path|str), start (float s), end (float s)}
    Os clips são copiados para remotion_project/public/broll/ e referenciados
    como paths relativos na prop brollClips do componente React.
    """
    print("[Editor] Preparando dados para renderização no Remotion...")

    # Copia clips de b-roll para public/broll/ e converte para paths relativos
    broll_props = []
    if broll_clips:
        pasta_public_broll = Path("remotion_project/public/broll")
        pasta_public_broll.mkdir(parents=True, exist_ok=True)
        for clip in broll_clips:
            src = Path(clip["src"])
            dest = pasta_public_broll / src.name
            shutil.copy(src, dest)
            broll_props.append({
                "src":        f"broll/{src.name}",
                "startFrame": round(clip["start"] * FPS),
                "endFrame":   round(clip["end"]   * FPS),
            })

    props = {
        "audioSrc":      audio_path,
        "tipo":          tipo_video,
        "legendas":      frases_timings,
        "assetsVisuais": assets_path,
        "opcoesVisuais": opcoes_visuais or {},
        "brollClips":    broll_props,
    }

    props_file_rel = Path("public/current_props.json")
    props_file_abs = Path("remotion_project") / props_file_rel
    props_file_abs.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    comando = [
        "npx", "remotion", "render",
        "src/index.ts",
        "ComposicaoPrincipal",
        f"../{output_path}",
        f"--props={str(props_file_rel)}",
    ]

    print("[Editor] Iniciando renderização...")
    subprocess.run(comando, cwd="remotion_project", shell=True, check=True)
    print(f"[Editor] Vídeo renderizado com sucesso em {output_path}")
