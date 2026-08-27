---
description: Gera, revisa, corrige e sobe um post de blog para a Tecnosolve no Webflow
argument-hint: [tema opcional]
allowed-tools: [Bash, Read]
---

# /blog-tecnosolve

Cria um artigo de blog completo para a Tecnosolve e sobe ao Webflow como rascunho.

**Argumento opcional:** tema específico. Sem argumento, o tema é escolhido automaticamente entre conteúdos ainda não publicados.

## Instruções

### 1. Executar o pipeline

```bash
cd /home/campos_1122/bob && source venv/bin/activate && python3 gerar_blog_tecnosolve.py $ARGUMENTS
```

O script imprime progresso em 6 etapas:
- `[1/6]` Tema escolhido
- `[2/6]` Artigo gerado
- `[3/6]` Revisão Gemini (nota /10 + observações)
- `[4/6]` Correção automática (se nota < 8)
- `[5/6]` Imagem de capa gerada
- `[6/6]` Upload Webflow

O script termina com um bloco `BLOG CRIADO COM SUCESSO` contendo Tema, Título, Nota final, caminho da Capa, Webflow ID e DB ID.

### 2. Verificar imagem de capa

Após o script concluir, leia a imagem de capa com o tool Read:
- O caminho aparece na linha `Capa: ...` do output
- Verifique se a imagem é profissional, sem texto visível e adequada ao tema corporativo de TI
- Se a imagem for inadequada (muito genérica, com texto, ou completamente fora do contexto), informe o usuário

### 3. Reportar ao usuário

Reporte em português:
- **Tema** e **Título** do artigo
- **Nota final** da revisão Gemini (e se houve correção automática)
- **Webflow Item ID** — para o usuário localizar o rascunho no painel Webflow da Tecnosolve
- Se a imagem de capa foi verificada e aprovada ou se há ressalvas

### Tratamento de erros

- Se o script falhar em qualquer etapa, leia o erro, diagnostique e corrija antes de reportar ao usuário
- Erros comuns: GEMINI_API_KEY ausente, WEBFLOW_API_TOKEN ausente, MongoDB indisponível
