# SETUP:
# 1. python -m venv venv
# 2. Windows: venv\Scripts\activate  |  Mac/Linux: source venv/bin/activate
# 3. pip install -r requirements.txt
# 4. Copie .env.example para .env e preencha GEMINI_API_KEY
# 5. python orquestrador.py

import json
import os
from datetime import datetime
from dotenv import load_dotenv
from modulos import llm_brain

load_dotenv()


def main():
    empresa = "Tecnosolve"
    publico_alvo = "CIOs e CTOs do varejo brasileiro"
    tema = "Integração de sistemas legados com plataformas modernas de e-commerce"

    print(f"[Orquestrador] Empresa: {empresa}")
    print(f"[Orquestrador] Tema: {tema}\n")

    conteudo = llm_brain.gerar_conteudo(tema, empresa=empresa, publico_alvo=publico_alvo)

    # Salva em outputs/
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"outputs/{empresa.lower()}_{timestamp}.json"
    with open(nome_arquivo, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    print(f"[Orquestrador] Conteúdo salvo em: {nome_arquivo}\n")

    # Preview no terminal
    print("=" * 60)
    print("CARROSSEL — 9 slides")
    print("=" * 60)
    for slide in conteudo.get("carrossel", []):
        print(f"\nSlide {slide['slide']}: {slide['titulo']}")
        print(f"  {slide['texto'][:120]}...")

    print("\n" + "=" * 60)
    print("ARTIGO LINKEDIN (primeiros 300 chars)")
    print("=" * 60)
    artigo = conteudo.get("artigo_linkedin", "")
    print(artigo[:300] + "...")

    print("\n" + "=" * 60)
    print("ROTEIRO DE VÍDEO (primeiros 300 chars)")
    print("=" * 60)
    roteiro = conteudo.get("roteiro_video", "")
    print(roteiro[:300] + "...")


if __name__ == "__main__":
    main()
