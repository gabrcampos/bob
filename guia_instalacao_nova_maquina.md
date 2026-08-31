# Guia de instalação do Bob em nova máquina

---

## 1. Pré-requisitos

- Python 3.12+
- Git
- Acesso ao repositório `gabrcampos/bob`

---

## 2. Clonar e instalar dependências

```bash
git clone https://github.com/gabrcampos/bob.git
cd bob
pip install -r requirements.txt
```

---

## 3. Arquivos de configuração (copiar do servidor original)

Esses arquivos **não estão no git** e precisam ser copiados manualmente do servidor de produção:

| Arquivo | Para que serve |
|---|---|
| `.env` | Todas as variáveis de ambiente (Gemini, MongoDB, Telegram, etc.) |
| `config/service_account.json` | Drive API + Google Cloud Storage |
| `config/facebook_doisbe.json` | Publicação no Facebook (DoisBê) |
| `config/linkedin_token.json` | Publicação no LinkedIn |
| `config/youtube_token.json` | Upload no YouTube |
| `cookies.txt` | Scraping do Instagram (DoisBê) |

Caminho de cada um no servidor original:
```
/home/campos_1122/bob/.env
/home/campos_1122/bob/config/service_account.json
/home/campos_1122/bob/config/facebook_doisbe.json
/home/campos_1122/bob/config/linkedin_token.json
/home/campos_1122/bob/config/youtube_token.json
/home/campos_1122/bob/cookies.txt
```

---

## 4. Variáveis de ambiente (.env)

O `.env` precisa conter no mínimo:

```
GEMINI_API_KEY=...
MONGODB_URI=...
GCS_BUCKET_NAME=bob-videos-487590427215
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_ORG_ID=...
```

---

## 5. O que NÃO precisa configurar (já está na nuvem)

- **MongoDB Atlas** — banco já existe, basta o `MONGODB_URI`
- **Credenciais do Instagram** — token e ig_user_ids já estão no MongoDB por empresa
- **Drive folders** — links já salvos no MongoDB por conteúdo
- **GCS bucket** — já existe, o `service_account.json` dá acesso

---

## 6. Fontes (atenção)

As fontes em `config/fontes/` precisam ser os arquivos TTF **completos** do Google Fonts (com suporte a caracteres portugueses). Baixar manualmente:

- **Poppins Bold + Regular** — fonts.google.com/specimen/Poppins → Download family
- **Anton** — fonts.google.com/specimen/Anton
- **Space Mono Bold + Regular** — fonts.google.com/specimen/Space+Mono

Renomear para: `Poppins_bold.ttf`, `Poppins_regular.ttf`, `Anton_bold.ttf`, `Space_Mono_bold.ttf`, `Space_Mono_regular.ttf`

---

## 7. Token do Instagram (System User — nunca expira)

O token atual já está salvo no MongoDB. Se precisar regenerar:

1. business.facebook.com → Configurações → Usuários → Usuários do Sistema
2. Selecione o usuário do sistema existente
3. Gerar novo token → app `1147272694286950` → permissões: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
4. Atualizar no MongoDB:

```python
from modulos.db import col_empresas
token = '<novo_token>'
col_empresas().update_one({'id': 'tecnosolve'}, {'$set': {'instagram.access_token': token}})
col_empresas().update_one({'id': 'deliverydash'}, {'$set': {'instagram.access_token': token}})
```

---

## 8. Workflow completo para gerar e publicar os dois posts

### Gerar
```bash
python3 gerar_post.py tecnosolve carrossel "tema tecnosolve"
python3 gerar_post.py deliverydash carrossel_misto_dd "tema deliverydash"
```

Anotar o `conteudo_id` e `stem` de cada um na saída.

### Revisão visual

Ler cada PNG gerado e verificar:

**Tecnosolve (carrossel):** slides 3, 5 e 7 têm imagem IA — verificar logo no canto, imagem com contexto de varejo/tech. Sem garrafa térmica, escritório genérico ou smartphone isolado.

**DeliveryDash (misto):** slides 1, 2, 3, 4, 6, 7 e 8 têm imagem IA — toda imagem deve ter contexto de restaurante, dark kitchen, motoboy ou comida. Slide 6: fundo vermelho + título DeliveryDash + bullets com ✓.

**Sempre verificar no DB após geração** se o campo `texto` do slide 8 do DD contém "apagar incêndio" — o revisor automático detecta mas nem sempre remove.

### Corrigir slide com problema

```python
from modulos.db import buscar_conteudo, atualizar_conteudo, buscar_empresa
from modulos.gerador_imagens import gerar_imagem_slide_misto_dd
import copy

# 1. Editar no DB
doc = buscar_conteudo('<conteudo_id>')
slides = copy.deepcopy(doc['slides'])
slides[7]['texto'] = 'Novo texto sem clichê.'          # slide 8 = índice 7
slides[1]['prompt_imagem'] = 'Novo prompt com contexto de restaurante.'
atualizar_conteudo('<conteudo_id>', {'slides': slides})

# 2. Regenerar slide
empresa = buscar_empresa('deliverydash')
iv = empresa.get('identidade_visual', {})
doc = buscar_conteudo('<conteudo_id>')
gerar_imagem_slide_misto_dd(doc['slides'][1], 'deliverydash', empresa['nome'], stem, iv, logo_index=1)
```

### Reconstruir PDF e atualizar Drive

```python
from modulos.gerador_imagens import listar_imagens_misto_dd, imagens_para_pdf
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Reconstruir PDF
imagens = listar_imagens_misto_dd('deliverydash', stem)
pdf = imagens_para_pdf(imagens)
with open(f'outputs/deliverydash/{stem}.pdf', 'wb') as f:
    f.write(pdf)

# Atualizar no Drive
creds = service_account.Credentials.from_service_account_file(
    'config/service_account.json', scopes=['https://www.googleapis.com/auth/drive'])
service = build('drive', 'v3', credentials=creds, cache_discovery=False)

folder_id = '<id_da_pasta_drive>'  # buscar no doc do MongoDB
files = {f['name']: f['id'] for f in service.files().list(
    q=f"'{folder_id}' in parents and trashed=false",
    fields='files(id,name)', supportsAllDrives=True, includeItemsFromAllDrives=True
).execute()['files']}

for local, nome, mime in [
    (f'outputs/deliverydash/{stem}.pdf', f'{stem}.pdf', 'application/pdf'),
    (f'outputs/deliverydash/imagens_misto_dd/{stem}/slide_02.png', 'slide_02.png', 'image/png'),
]:
    service.files().update(
        fileId=files[nome],
        media_body=MediaFileUpload(local, mimetype=mime, resumable=True),
        supportsAllDrives=True
    ).execute()
```

### Enviar ao Telegram

```python
from modulos.telegram_bot import enviar_mensagem
enviar_mensagem(
    "Boa tarde! Dois posts para aprovação:\n\nTS - <título>\n<link>\n\nDD - <título>\n<link>",
    parse_mode=''
)
```

### Publicar no Instagram (TS primeiro, depois DD)

```python
from modulos.db import buscar_conteudo, buscar_credencial_instagram, atualizar_conteudo
from modulos.gerador_imagens import listar_imagens, listar_imagens_misto_dd
from modulos.instagram_publisher import publicar_carrossel_instagram

# Tecnosolve
doc = buscar_conteudo('<ts_conteudo_id>')
cred = buscar_credencial_instagram('tecnosolve')
imagens = listar_imagens('tecnosolve', ts_stem)
media_id = publicar_carrossel_instagram(imagens, doc['legenda'], cred['access_token'], 'tecnosolve', ts_stem)
atualizar_conteudo('<ts_conteudo_id>', {'status': 'publicado', 'media_id': media_id})

# DeliveryDash
doc = buscar_conteudo('<dd_conteudo_id>')
cred = buscar_credencial_instagram('deliverydash')
imagens = listar_imagens_misto_dd('deliverydash', dd_stem)
media_id = publicar_carrossel_instagram(imagens, doc['legenda'], cred['access_token'], 'deliverydash', dd_stem)
atualizar_conteudo('<dd_conteudo_id>', {'status': 'publicado', 'media_id': media_id})
```

---

## Armadilhas que já aconteceram

- **Fontes sem acento** — baixar TTF completo do Google Fonts, não via CDN/web
- **`identidade_visual=None`** ao regenerar slide — sempre usar `buscar_empresa()`, nunca o doc de conteúdo
- **Token Instagram expirado** — usar System User do Business Suite (nunca expira)
- **Instagram 400 ao publicar** — publicar TS antes do DD
- **Clichê "apagar incêndio" no slide 8 do DD** — checar campo `texto` no DB após geração mesmo que o revisor automático tenha detectado
