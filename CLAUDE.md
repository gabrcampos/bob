# Bob — Regras de Geração de Posts

## Revisão visual obrigatória

Após gerar imagens de qualquer carrossel, ANTES de montar o PDF e enviar ao Telegram:

1. Ler cada PNG gerado com o tool `Read`
2. Verificar por empresa/tipo (ver regras abaixo)
3. Corrigir e regenerar slides com problema antes de continuar

Não enviar PDF ao Telegram sem ter feito a revisão visual.

---

## Regras por empresa

### Tecnosolve — carrossel_tweet
- **Logo**: sempre `logo_index=2` (logo escura, fundo branco)
- **Slides com imagem IA**: 3, 5 e 7
- **Revisar nas imagens**: logo visível e correta no canto, imagem de fundo coerente com o título do slide
- **Prompts proibidos**: palavras que gerem garrafa térmica (`thermal`), smartphone isolado, escritório genérico sem contexto

### DeliveryDash — carrossel_misto_dd
- **Logo**: `logo_index=1`
- **Slides com imagem IA**: 1, 2, 3, 4, 6, 7, 8
- **Slide 6**: título fixo "DeliveryDash", bullets com ✓, fundo de cozinha ou restaurante
- **Revisar nas imagens**: toda imagem deve ter contexto de restaurante, dark kitchen, motoboy ou comida. Jamais: varejo de supermercado, delivery de e-commerce (caixa marrom estilo Amazon), imagem sem referência a food service
- **Slide 1**: motoboy ou cozinha — nunca pessoa genérica com smartphone
- **Slide 8**: prato de restaurante profissional (já é fixo no código)

---

## Regras de legenda (todas as empresas)

- Sem travessão (`—`) — usar ponto ou dois-pontos
- Mínimo 2 quebras de linha dupla (`\n\n`) no corpo
- Exatamente 3 hashtags
- CTA fixo no final (antes das hashtags):
  - **DeliveryDash**: `Teste gratuitamente o DeliveryDash por 7 dias - link na bio.`
  - **Tecnosolve**: `Fale com um especialista - link na bio.`

---

## Clichês proibidos (em qualquer slide ou legenda)

- "apagar incêndio(s)"
- "modo crise"
- "no mundo de hoje"
- "descubra como"
- "você sabia que"
- "transformação digital" (genérico)
- "inovação disruptiva"

---

## Fluxo de geração

1. Gerar conteúdo (LLM) — revisão de texto automática via `_revisar_conteudo()`
2. Gerar imagens
3. **Revisão visual**: ler cada PNG e verificar regras acima
4. Corrigir slides com problema
5. Montar PDF
6. Enviar ao Telegram para aprovação final
7. Só agendar/publicar quando o usuário aprovar
