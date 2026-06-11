# Plano de Deploy do Bob — Google Cloud

## Visão Geral

Transformar o Bob de ferramenta local (3 instâncias Streamlit no computador) em uma aplicação web hospedada, sempre disponível, com imagens persistentes na nuvem.

**Stack alvo:** Cloud Run (app) + Cloud Storage (imagens) + Secret Manager (chaves) + MongoDB Atlas (banco — já existente ou a migrar)

---

## O que preciso de você (pré-requisitos)

### Obrigatório antes de começar

| Item | Detalhe | Status |
|---|---|---|
| **Google Cloud Project ID** | O ID do projeto criado na tela da imagem | Confirmar |
| **MongoDB** | O banco está no Atlas (nuvem) ou local? | Confirmar |
| **GitHub** | O repositório do bob está no GitHub? | Confirmar |
| **Decisão de autenticação** | Quem pode acessar o app? (ver opções abaixo) | Decidir |

### Opcional mas recomendado

| Item | Detalhe |
|---|---|
| **Domínio personalizado** | Ex: `bob.nomos.pro` ou `bob.tecnosolve.com`. Se não tiver, fica `*.run.app` (feio mas funciona) |
| **Repositório privado** | Se o código não está no GitHub ainda, precisamos subir |

### Opções de autenticação

O app hoje não tem senha — qualquer pessoa com a URL acessa. Precisamos decidir:

- **Google IAP (Identity-Aware Proxy)** — login com conta Google, gratuito no free tier. Recomendado se você e sua equipe usam Google Workspace
- **Senha simples no Streamlit** — mais rápido de implementar, menos seguro
- **URL secreta** — sem login, mas a URL é difícil de adivinhar. Serve para uso interno imediato

---

## Fases de Execução

### Fase 1 — Cloud Storage para imagens (2–3h de dev)

**O que muda:** imagens geradas deixam de ficar em `outputs/` local e passam a ser salvas em um bucket do GCS com URL pública.

**Impacto imediato:**
- Imagens persistem entre deploys e reinstalações
- Links diretos para compartilhar com clientes sem precisar do Drive
- Gratuito até 5GB/mês

**O que faço:**
1. Criar bucket no GCS (`bob-outputs`)
2. Modificar `gerador_imagens.py` para salvar no bucket após gerar localmente
3. Atualizar `app.py` para servir URLs do GCS em vez de caminhos locais
4. Configurar credenciais via Service Account

**Você precisa me dar:**
- Confirmação do Project ID do Google Cloud

---

### Fase 2 — Containerização com Docker (1–2h de dev)

**O que muda:** o bob é empacotado em um container que roda igual em qualquer lugar.

**O que faço:**
1. Criar `Dockerfile` otimizado para Streamlit + Pillow
2. Criar `.dockerignore` (excluir `venv/`, `outputs/`, `.env`)
3. Criar `docker-compose.yml` para testar local antes de subir
4. Testar build local

**Você não precisa fazer nada nessa fase.**

---

### Fase 3 — Deploy no Cloud Run (1–2h de dev)

**O que muda:** o bob fica disponível em uma URL pública, sem precisar abrir o computador.

**O que faço:**
1. Criar serviço no Cloud Run via `gcloud` CLI
2. Configurar variáveis de ambiente via **Secret Manager** (GEMINI_API_KEY, MONGODB_URI)
3. Definir limites de memória/CPU (Streamlit + Pillow precisam de ~1GB RAM)
4. Primeiro deploy manual, depois automatizado

**Você precisa:**
- Ter o `gcloud` CLI instalado (posso guiar a instalação em 5 minutos)
- Executar `gcloud auth login` uma vez no terminal

**Custo estimado:** dentro do free tier para uso da equipe interna (até ~1000 requisições/dia)

---

### Fase 4 — Domínio e autenticação (1h de dev)

**O que muda:** o app fica acessível por uma URL amigável com login.

**O que faço:**
1. Mapear domínio personalizado no Cloud Run (se você tiver um)
2. Configurar SSL automático (gratuito via Google)
3. Implementar a autenticação escolhida

**Você precisa:**
- Acesso ao painel DNS do domínio (ex: Registro.br, Cloudflare) para adicionar um registro CNAME
- Decisão sobre qual método de autenticação usar

---

### Fase 5 — CI/CD com Cloud Build (1h de dev)

**O que muda:** a cada `git push` na branch `main`, o bob é atualizado automaticamente em produção.

**O que faço:**
1. Criar `cloudbuild.yaml`
2. Conectar repositório GitHub ao Cloud Build
3. Configurar trigger de deploy automático

**Você precisa:**
- Repositório no GitHub (público ou privado)
- Autorizar o Cloud Build a ler o repositório

---

## Sequência recomendada

```
Fase 1 (Storage) → Fase 2 (Docker) → Fase 3 (Cloud Run) → Fase 4 (Domínio) → Fase 5 (CI/CD)
```

As fases 1 e 2 podem ser feitas sem nenhuma decisão sua — posso começar agora.
A Fase 3 precisa do Project ID e de um `gcloud auth login` seu.
A Fase 4 precisa da decisão de domínio e autenticação.

---

## O que NÃO muda

- A interface do Streamlit continua igual
- As empresas (Nomos, Tecnosolve, DeliveryDash) continuam no banco
- O fluxo de geração de conteúdo não muda
- A integração com Google Drive continua funcionando

---

## Resumo do que preciso de você agora

1. **Project ID do Google Cloud** — visível no console em `console.cloud.google.com`
2. **MongoDB está no Atlas ou local?** — se local, precisamos migrar para Atlas (gratuito até 512MB)
3. **Tem GitHub?** — URL do repositório ou confirmar que não tem ainda
4. **Domínio?** — tem um domínio comprado ou usar a URL padrão `*.run.app` por enquanto?
5. **Autenticação** — Google IAP, senha simples, ou URL secreta?
