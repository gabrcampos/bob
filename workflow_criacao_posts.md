# Workflow de Criação de Posts — Referência Completa

Cobre o ciclo completo: geração → revisão visual → correções → Drive → Telegram → publicação Instagram.

---

## 1. Geração de conteúdo + imagens

```bash
python3 gerar_post.py <empresa_id> <tipo> "<tema>"
```

**Exemplos dos últimos posts (2026-08-27):**

```bash
# Tecnosolve — carrossel padrão
python3 gerar_post.py tecnosolve carrossel \
  "Relatórios de varejo desatualizados: como dados atrasados travam decisões"

# DeliveryDash — carrossel misto
python3 gerar_post.py deliverydash carrossel_misto_dd \
  "Tempo de preparo na cozinha: como monitorar e reduzir atrasos antes que o cliente reclame"
```

**Saída esperada:**
```
✓ conteudo_id: <id>
✓ Drive: https://drive.google.com/drive/folders/<folder_id>
```

**Tipos disponíveis:**
| Empresa | Tipo | Quando usar |
|---|---|---|
| tecnosolve | `carrossel` | post padrão (default) |
| tecnosolve | `carrossel_tweet` | só quando pedido explicitamente "estilo twitter/tweet" |
| deliverydash | `carrossel_misto_dd` | sempre para DD |

---

## 2. Localizar as imagens geradas

```python
from modulos.gerador_imagens import listar_imagens, listar_imagens_misto_dd

# Tecnosolve carrossel padrão
imagens = listar_imagens('tecnosolve', stem)

# DeliveryDash misto
imagens = listar_imagens_misto_dd('deliverydash', stem)
```

Caminho físico dos PNGs:
- TS carrossel: `outputs/tecnosolve/imagens/<stem>/slide_NN.png`
- DD misto: `outputs/deliverydash/imagens_misto_dd/<stem>/slide_NN.png`

---

## 3. Revisão visual obrigatória (antes de qualquer outra etapa)

Ler cada PNG com o tool `Read` e verificar:

### Tecnosolve — carrossel
- Slides com imagem IA: **3, 5 e 7**
- Logo escura visível no canto (`logo_index=2`)
- Imagem coerente com o título do slide (contexto de varejo/tech/dados)
- Sem garrafa térmica, smartphone isolado, escritório genérico

### DeliveryDash — carrossel_misto_dd
- Slides com imagem IA: **1, 2, 3, 4, 6, 7, 8**
- Toda imagem deve ter contexto de restaurante, dark kitchen, motoboy ou comida
- Slide 1: motoboy ou cozinha de restaurante — nunca pessoa genérica com celular
- Slide 6: fundo vermelho, título "DeliveryDash", bullets com ✓
- Slide 8: prato profissional de restaurante

**Clichês proibidos em texto de qualquer slide:**
- "apagar incêndio(s)" / "modo crise" / "no mundo de hoje"
- "descubra como" / "você sabia que"
- "transformação digital" (genérico) / "inovação disruptiva"

---

## 4. Corrigir slides com problema

### 4a. Corrigir texto de um slide (ex: clichê)

```python
from modulos.db import buscar_conteudo, atualizar_conteudo
import copy

doc = buscar_conteudo('<conteudo_id>')
slides = copy.deepcopy(doc['slides'])

# índice 0-based: slide 8 = índice 7
slides[7]['texto'] = 'Novo texto sem clichê.'

atualizar_conteudo('<conteudo_id>', {'slides': slides})
```

### 4b. Corrigir prompt de imagem de um slide

```python
slides[1]['prompt_imagem'] = 'Customer anxiously checking smartphone for food delivery status, delivery bag visible nearby, warm ambient light, no text.'
atualizar_conteudo('<conteudo_id>', {'slides': slides})
```

### 4c. Regenerar slide individualmente

```python
from modulos.db import buscar_conteudo, buscar_empresa
from modulos.gerador_imagens import gerar_imagem_slide_misto_dd
# ou: gerar_imagem_slide (para carrossel TS padrão)

empresa = buscar_empresa('<empresa_id>')
iv = empresa.get('identidade_visual', {})       # SEMPRE buscar via buscar_empresa(), nunca do doc
empresa_nome = empresa.get('nome', '')

doc = buscar_conteudo('<conteudo_id>')
slide = doc['slides'][idx]                      # 0-based

# DD misto
gerar_imagem_slide_misto_dd(slide, 'deliverydash', empresa_nome, stem, iv, logo_index=1)

# TS carrossel padrão
# gerar_imagem_slide(slide, 'tecnosolve', empresa_nome, stem, iv, logo_index=2)
```

---

## 5. Reconstruir PDF e atualizar Drive após correções

### 5a. Reconstruir PDF local

```python
from modulos.gerador_imagens import listar_imagens_misto_dd, imagens_para_pdf

imagens = listar_imagens_misto_dd('deliverydash', stem)
pdf_bytes = imagens_para_pdf(imagens)
with open(f'outputs/deliverydash/{stem}.pdf', 'wb') as f:
    f.write(pdf_bytes)
```

### 5b. Atualizar arquivos no Drive (sem criar duplicatas)

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(
    'config/service_account.json', scopes=SCOPES)
service = build('drive', 'v3', credentials=creds, cache_discovery=False)

# 1. Listar arquivos da pasta para pegar os file IDs
folder_id = '<id_da_pasta_drive>'
result = service.files().list(
    q=f"'{folder_id}' in parents and trashed=false",
    fields='files(id, name)',
    supportsAllDrives=True, includeItemsFromAllDrives=True
).execute()
file_map = {f['name']: f['id'] for f in result['files']}

# 2. Atualizar arquivo por arquivo
updates = [
    ('outputs/deliverydash/<stem>.pdf', '<stem>.pdf', 'application/pdf'),
    ('outputs/deliverydash/imagens_misto_dd/<stem>/slide_02.png', 'slide_02.png', 'image/png'),
    # adicionar outros slides corrigidos...
]
for local_path, fname, mime in updates:
    media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
    service.files().update(
        fileId=file_map[fname], media_body=media, supportsAllDrives=True
    ).execute()
    print(f'Atualizado: {fname}')
```

---

## 6. Enviar links ao Telegram

```python
from modulos.telegram_bot import enviar_mensagem

msg = """Boa tarde! Dois posts novos para aprovação:

TS - <título resumido>
<link_drive_ts>

DD - <título resumido>
<link_drive_dd>"""

enviar_mensagem(msg, parse_mode='')
```

**Regras da mensagem:**
- Saudação por horário: Bom dia / Boa tarde / Boa noite
- `parse_mode=''` (plain text, sem HTML/Markdown)
- Uma linha por empresa, link na linha seguinte

---

## 7. Publicar no Instagram

Sempre publicar TS primeiro, depois DD (evita erro 400 da API).

```python
from modulos.db import buscar_conteudo, buscar_credencial_instagram, atualizar_conteudo
from modulos.gerador_imagens import listar_imagens, listar_imagens_misto_dd
from modulos.instagram_publisher import publicar_carrossel_instagram

# --- Tecnosolve ---
doc_ts = buscar_conteudo('<ts_conteudo_id>')
cred_ts = buscar_credencial_instagram('tecnosolve')
imagens_ts = listar_imagens('tecnosolve', ts_stem)

media_id = publicar_carrossel_instagram(
    imagens_ts, doc_ts['legenda'], cred_ts['access_token'], 'tecnosolve', ts_stem)
atualizar_conteudo('<ts_conteudo_id>', {'status': 'publicado', 'media_id': media_id})
print(f'TS publicado: {media_id}')

# --- DeliveryDash ---
doc_dd = buscar_conteudo('<dd_conteudo_id>')
cred_dd = buscar_credencial_instagram('deliverydash')
imagens_dd = listar_imagens_misto_dd('deliverydash', dd_stem)

media_id = publicar_carrossel_instagram(
    imagens_dd, doc_dd['legenda'], cred_dd['access_token'], 'deliverydash', dd_stem)
atualizar_conteudo('<dd_conteudo_id>', {'status': 'publicado', 'media_id': media_id})
print(f'DD publicado: {media_id}')
```

---

## Referência dos últimos posts (2026-08-27)

| Campo | Tecnosolve | DeliveryDash |
|---|---|---|
| Tema | Relatórios de varejo desatualizados | Tempo de preparo na cozinha |
| Tipo | `carrossel` | `carrossel_misto_dd` |
| `conteudo_id` | `6a8f616ccfa7b7014102bbd0` | `6a8f6300a165e109927497e3` |
| `stem` | `relatorios_de_varejo_desatualizados_..._20260826_215804` | `tempo_de_preparo_na_cozinha_..._20260826_220448` |
| Drive | [pasta TS](https://drive.google.com/drive/folders/18_7bJCiwHap9Fw-SdU3f4B1pXMFK_E-5) | [pasta DD](https://drive.google.com/drive/folders/1IHGj1KX1AK2_WEzjBLItoCfRSO39dgqk) |
| `media_id` | `17871498513634023` | `18454431967142620` |

**Correções feitas nesta sessão (DD):**
- Slide 8: removido clichê "apagar incêndios" do campo `texto`
- Slide 2: prompt atualizado para incluir contexto de delivery (sacola visível)
- Slide 4: prompt atualizado para cozinha comercial com chef estressado

---

## Armadilhas conhecidas

| Problema | Causa | Fix |
|---|---|---|
| `identidade_visual=None` ao regenerar slide | Doc do conteúdo guarda `None` | Sempre usar `buscar_empresa(empresa_id).get('identidade_visual', {})` |
| Imagen 4.0 retorna 404 | Modelos descontinuados | Sistema cai automaticamente para `gemini-2.5-flash-image` (funcional) |
| Drive cria arquivo duplicado | Usar `create` em vez de `update` | Listar pasta, pegar `file_id`, usar `files().update()` |
| Instagram erro 400 | Publicar DD antes do TS | Sempre publicar TS primeiro, depois DD |
| Clichê detectado mas não removido pelo revisor | Bug no revisor automático | Checar campo `texto` de todos os slides no DB após geração |
