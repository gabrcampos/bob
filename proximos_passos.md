# Próximos Passos — Módulo de B-Roll com IA

## Contexto
O módulo de vídeo (`TextoAnimado`) já está funcional com legenda animada, fonte Poppins,
sentence case correto e remoção de silêncios no áudio.

O próximo bloco é gerar **b-rolls curtos e realistas** via IA para servir de background
dinâmico, sincronizados com as frases da narração.

---

## Decisões tomadas
- **Granularidade:** um vídeo por frase completa (não por chunk de legenda)
- **Estilo:** cenas do cotidiano — nunca abstrações (holograma, rede neural, onda...)
- **API:** avaliar melhor custo/benefício para a fase de testes (ver seção abaixo)

---

## API recomendada para testes

| API | Custo aprox. | Qualidade | Facilidade |
|---|---|---|---|
| **Kling 1.6** (via fal.ai) | ~$0,035/s | Excelente para cenas reais | SDK Python simples |
| **Luma Dream Machine** | ~$0,10/clip 5s | Boa, muito rápido | REST direto |
| **Minimax / Hailuo** | ~$0,01-0,02/s | Boa, melhor custo | Menos documentado |

**Recomendação para testes:** Kling via [fal.ai](https://fal.ai) — boa qualidade de cenas
realistas, SDK Python disponível, créditos de teste generosos.

---

## Arquitetura planejada

```
roteiro (texto)
    │
    ▼
llm_brain.gerar_prompts_broll(roteiro)
    │   LLM recebe o script completo e retorna uma lista de:
    │   { frase: str, prompt_video: str, start: float, end: float }
    │
    ▼
broll.gerar_videos_broll(prompts)
    │   Para cada prompt: chama a API de vídeo, baixa o clip
    │   Retorna lista de paths dos clips gerados
    │
    ▼
editor.renderizar_video_remotion(...)
    │   assetsVisuais agora é lista de clips de vídeo com timing
    │
    ▼
TextoAnimado.tsx
    Troca o clip de background conforme o frame atual
```

---

## Tarefas

### 1. `modulos/broll.py` (novo arquivo)
- [ ] `gerar_videos_broll(prompts, empresa_id, stem)` — chama a API, salva clips em `outputs/{empresa_id}/broll/`
- [ ] Cada clip gerado com duração proporcional ao tempo da frase + pequena margem

### 2. `modulos/llm_brain.py`
- [ ] `gerar_prompts_broll(roteiro, word_timings)` — LLM divide o roteiro em frases,
      gera um prompt visual concreto e cotidiano para cada uma, retorna lista com timing

**System prompt da LLM:**
```
Você é um diretor de vídeo criativo. Para cada trecho de fala,
crie um prompt curto (em inglês) para uma cena de vídeo realista e cotidiana.
NUNCA use: holograma, rede neural, animação, abstração, neon, sci-fi.
USE: pessoas reais, objetos físicos, ambientes do dia a dia.
Retorne APENAS JSON: [{"frase": "...", "prompt": "..."}, ...]
```

### 3. `remotion_project/src/TextoAnimado.tsx`
- [ ] Alterar `assetsVisuais` para aceitar lista de `{ src: string, startFrame: number, endFrame: number }`
- [ ] Renderizar o clip correto como background baseado no `frame` atual (`<Video>` do Remotion)
- [ ] Transição suave entre clips (crossfade simples com `opacity`)

### 4. `modulos/editor.py`
- [ ] Atualizar `renderizar_video_remotion` para receber e passar os clips com timing

### 5. `teste_video.py`
- [ ] Adicionar chamada ao `gerar_prompts_broll` + `gerar_videos_broll`
- [ ] Testar pipeline completo end-to-end

---

## Ordem de execução sugerida

1. Escolher e configurar a API de vídeo (obter chave, instalar SDK)
2. Criar `broll.py` com geração de um clip de teste manual
3. Criar `gerar_prompts_broll` na LLM e validar os prompts gerados
4. Atualizar `TextoAnimado.tsx` para consumir vídeos com timing
5. Rodar `teste_video.py` completo e ajustar sincronização
