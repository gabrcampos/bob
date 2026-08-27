import re
import unicodedata
from datetime import datetime
import requests
import markdown

def _slugify(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    texto = texto.lower().strip()
    texto = re.sub(r'[\s]+', '-', texto)
    texto = re.sub(r'[^a-z0-9\-_]', '', texto)
    slug_base = re.sub(r'-+', '-', texto).strip('-')
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{slug_base}-{timestamp}" if slug_base else f"artigo-{timestamp}"

def enviar_post(api_token: str, collection_id: str, titulo: str, corpo_markdown: str, imagem_path=None):
    url = f"https://api.webflow.com/v2/collections/{collection_id}/items"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "accept": "application/json"
    }
    
    # 1. Normalize newlines e limpe espaços fantasmas de copy/paste
    corpo_markdown = corpo_markdown.replace('\r\n', '\n').replace('\r', '\n')
    corpo_markdown = corpo_markdown.replace('\xa0', ' ') # --- NOVO: Remove non-breaking spaces
    
    # 2. Padroniza bullets protegendo o negrito
    corpo_markdown = re.sub(r'^(\s*)\\?[*•+]\s+', r'\1- ', corpo_markdown, flags=re.MULTILINE | re.UNICODE)
    
    # 3. Converte para HTML nativo
    corpo_html = markdown.markdown(corpo_markdown, extensions=['extra', 'sane_lists'])
    
    # --- NOVO: A GRANDE CORREÇÃO PARA O WEBFLOW ---
    # Minifica o HTML removendo todas as quebras de linha.
    # Isso impede que o parser do Webflow engasgue e delete as listas.
    corpo_html = corpo_html.replace('\n', '').replace('\r', '')
    # ----------------------------------------------
    
    # Rebaixa H1 para H2
    corpo_html = corpo_html.replace('<h1>', '<h2>').replace('</h1>', '</h2>')
    
    # Gera um Post Summary inteligente
    texto_espacado = re.sub(r'<(p|br|div|h[1-6]|li|ul|ol)[^>]*>', ' ', corpo_html)
    resumo_limpo = re.sub(r'<[^>]+>', '', texto_espacado)
    resumo_limpo = re.sub(r'\s+', ' ', resumo_limpo).strip()
    
    # 3. Corta antes de 240 caracteres, na última palavra completa
    if len(resumo_limpo) > 240:
        corte = resumo_limpo[:240]
        ultimo_espaco = corte.rfind(' ')
        
        if ultimo_espaco > 0:
            # Pega o texto até o último espaço e remove pontuações no final
            texto_cortado = corte[:ultimo_espaco].rstrip('.,;:- ')
            post_summary = f"{texto_cortado}..."
        else:
            post_summary = f"{corte.rstrip('.,;:- ')}..."
    else:
        post_summary = resumo_limpo
        
    field_data = {
        "name": titulo,
        "slug": _slugify(titulo),
        "post-body": corpo_html,
        "post-summary": post_summary,
    }

    # Upload de imagem de capa para o GCS e associa ao Webflow
    if imagem_path:
        try:
            from pathlib import Path as _Path
            from modulos.cloud_storage import upload_imagem_permanente
            caminho = _Path(imagem_path)
            blob_name = f"blog_capas/{caminho.name}"
            img_url = upload_imagem_permanente(caminho, blob_name)
            field_data["main-image"] = {"url": img_url, "alt": titulo}
            field_data["thumbnail-image"] = {"url": img_url, "alt": titulo}
            print(f"[Webflow] Imagem de capa associada: {img_url}")
        except Exception as e:
            print(f"[Webflow] Aviso: não foi possível fazer upload da imagem de capa: {e}")

    payload = {
        "isArchived": False,
        "isDraft": True,
        "fieldData": field_data,
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if not response.ok:
        print(f"[Webflow] Erro na API: {response.text}")
        response.raise_for_status()
        
    print(f"[Webflow] Post '{titulo}' enviado com sucesso para o Webflow (ID: {response.json().get('id')})")
    return response.json()


def publicar_item(api_token: str, collection_id: str, item_id: str) -> bool:
    """
    Publica um item que está como rascunho (isDraft: True) no Webflow.
    Chamado pelo cron de agendamento quando chega a data de publicação.
    Retorna True em caso de sucesso.
    """
    url = f"https://api.webflow.com/v2/collections/{collection_id}/items/publish"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    response = requests.post(url, json={"itemIds": [item_id]}, headers=headers, timeout=30)
    if not response.ok:
        print(f"[Webflow] Erro ao publicar item {item_id}: {response.text}")
        response.raise_for_status()
    print(f"[Webflow] Item {item_id} publicado com sucesso.")
    return True