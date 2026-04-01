import io
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from modulos import llm_brain, gerador_imagens, drive

load_dotenv()

CONFIG_PATH = Path("config/empresas.json")
OUTPUTS_DIR = Path("outputs")
ARQUIVOS_DIR = Path("config/arquivos")

# Opções de estilo por slide (para slides com variante)
_OPCOES_ESTILO_SLIDE = {
    2: [
        ("Gradiente lateral", "A"),
        ("Blade diagonal",    "A1"),
        ("Frame",             "A2"),
        ("Accent bar",        "A3"),
        ("Padrão",            None),
    ],
    5: [
        ("Overlay colorido",  "B"),
        ("Duotone",           "B1"),
        ("Tag + linha",       "B2"),
        ("Número grande",     "B3"),
        ("Padrão",            None),
    ],
    7: [
        ("Split reto",        "C"),
        ("Diagonal",          "C1"),
        ("Overlap",           "C2"),
        ("Canto",             "C3"),
        ("Padrão",            None),
    ],
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def carregar_empresas() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def salvar_empresas(empresas: list[dict]):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(empresas, f, ensure_ascii=False, indent=2)


def pasta_arquivos(empresa_id: str) -> Path:
    p = ARQUIVOS_DIR / empresa_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def listar_arquivos(empresa_id: str) -> list[Path]:
    p = ARQUIVOS_DIR / empresa_id
    if not p.exists():
        return []
    return sorted(f for f in p.iterdir() if f.suffix.lower() in (".pdf", ".docx", ".doc"))


def slugify(texto: str) -> str:
    import re
    texto = texto.lower().strip()
    texto = re.sub(r"[àáâãä]", "a", texto)
    texto = re.sub(r"[èéêë]", "e", texto)
    texto = re.sub(r"[ìíîï]", "i", texto)
    texto = re.sub(r"[òóôõö]", "o", texto)
    texto = re.sub(r"[ùúûü]", "u", texto)
    texto = re.sub(r"[ç]", "c", texto)
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto[:60].strip("_")


def salvar_conteudo(conteudo: dict, empresa_id: str, tema: str) -> dict[str, Path]:
    """Salva carrossel, linkedin e roteiro em pastas separadas. Retorna dict com os paths."""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(tema)
    base = OUTPUTS_DIR / empresa_id
    paths = {}

    # Carrossel → JSON
    pasta = base / "carrossel"
    pasta.mkdir(parents=True, exist_ok=True)
    path_c = pasta / f"{slug}_{ts}.json"
    with open(path_c, "w", encoding="utf-8") as f:
        json.dump({
            "tema": conteudo["tema"],
            "empresa": conteudo["empresa"],
            "publico_alvo": conteudo["publico_alvo"],
            "slides": conteudo["carrossel"],
        }, f, ensure_ascii=False, indent=2)
    paths["carrossel"] = path_c

    # Post LinkedIn → MD
    pasta = base / "linkedin"
    pasta.mkdir(parents=True, exist_ok=True)
    path_l = pasta / f"{slug}_{ts}.md"
    path_l.write_text(
        f"# {conteudo['tema']}\n\n{conteudo.get('post_linkedin') or conteudo.get('artigo_linkedin', '')}",
        encoding="utf-8",
    )
    paths["linkedin"] = path_l

    # Narração → MD
    pasta = base / "video"
    pasta.mkdir(parents=True, exist_ok=True)
    path_v = pasta / f"{slug}_{ts}.md"
    path_v.write_text(
        f"# {conteudo['tema']}\n\n{conteudo.get('narracao_video') or conteudo.get('roteiro_video', '')}",
        encoding="utf-8",
    )
    paths["video"] = path_v

    return paths


def salvar_carrossel_tweet(slides: list[dict], empresa_id: str, tema: str) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(tema)
    pasta = OUTPUTS_DIR / empresa_id / "carrossel_tweet"
    pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / f"{slug}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tema": tema, "slides": slides}, f, ensure_ascii=False, indent=2)
    return path


def salvar_carrossel_misto_dd(slides: list[dict], empresa_id: str, tema: str) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(tema)
    pasta = OUTPUTS_DIR / empresa_id / "carrossel_misto_dd"
    pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / f"{slug}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tema": tema, "slides": slides}, f, ensure_ascii=False, indent=2)
    return path


def salvar_blog(texto: str, empresa_id: str, tema: str) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(tema)
    pasta = OUTPUTS_DIR / empresa_id / "blog"
    pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / f"{slug}_{ts}.md"
    path.write_text(texto, encoding="utf-8")
    return path


def listar_conteudos(empresa_id: str, tipo: str) -> list[Path]:
    pasta = OUTPUTS_DIR / empresa_id / tipo
    if not pasta.exists():
        return []
    return sorted(pasta.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)


def excluir_conteudo(empresa_id: str, stem: str):
    """Remove todos os arquivos com o mesmo stem em todas as pastas de tipo."""
    for tipo in TIPOS:
        for path in (OUTPUTS_DIR / empresa_id / tipo).glob(f"{stem}.*"):
            path.unlink(missing_ok=True)


def hex_para_rgb(hex_color: str) -> str | None:
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}"
    except ValueError:
        return None


def _campos_cores(prefixo: str, label: str, n: int, salvas: list[dict]) -> list[str]:
    """Renderiza n campos de texto hex para cores. Retorna lista de valores digitados."""
    st.caption(label)
    cols = st.columns(n)
    valores = []
    for j in range(n):
        hex_salvo = salvas[j]["hex"] if j < len(salvas) else ""
        v = cols[j].text_input(
            f"{j+1}",
            value=hex_salvo,
            placeholder="#rrggbb",
            key=f"{prefixo}_{j}",
            label_visibility="visible",
        )
        # Mostra preview inline se hex válido
        h = v.strip().lstrip("#")
        if len(h) == 6:
            cols[j].markdown(
                f'<div style="width:100%;height:16px;background:#{h};border-radius:4px;margin-top:-8px"></div>',
                unsafe_allow_html=True,
            )
        valores.append(v.strip())
    return valores


def _construir_cores(valores: list[str]) -> list[dict]:
    resultado = []
    for v in valores:
        rgb = hex_para_rgb(v)
        if rgb:
            resultado.append({"hex": v if v.startswith("#") else f"#{v}", "rgb": rgb})
    return resultado


def _campos_identidade_visual(prefixo: str, iv: dict):
    """Renderiza seção completa de identidade visual. Retorna (primarias, secundarias, fontes)."""
    st.markdown("**Identidade visual**")

    primarias_salvas  = iv.get("primarias", [])
    secundarias_salvas = iv.get("secundarias", [])
    fontes_salvas     = iv.get("fontes", [])

    def _bloco_cores(label: str, n: int, salvas: list[dict], tipo: str):
        st.caption(label)
        cols = st.columns(n)
        resultado = []
        for j in range(n):
            salvo     = salvas[j] if j < len(salvas) else {}
            hex_salvo = salvo.get("hex", "")
            ativo     = bool(salvo)  # marcado se já tinha cor salva

            ativo_val = cols[j].checkbox("Usar", value=ativo, key=f"{prefixo}_{tipo}_ck_{j}", label_visibility="collapsed")
            v = cols[j].text_input(
                f"{j+1}", value=hex_salvo, placeholder="#rrggbb",
                key=f"{prefixo}_{tipo}_{j}",
                label_visibility="visible",
            )
            h = v.strip().lstrip("#")
            if len(h) == 6:
                cols[j].markdown(
                    f'<div style="width:100%;height:12px;background:#{h};border-radius:3px;margin-top:-6px"></div>',
                    unsafe_allow_html=True,
                )
            resultado.append(v.strip() if ativo_val else "")
        return resultado

    prim_vals = _bloco_cores("Cores primárias (até 3)", 3, primarias_salvas, "prim")
    sec_vals  = _bloco_cores("Cores secundárias (até 6)", 6, secundarias_salvas, "sec")

    st.caption("Fontes")
    col_f1, col_f2 = st.columns(2)
    fonte1 = col_f1.text_input("Principal",  value=fontes_salvas[0] if fontes_salvas else "",           key=f"{prefixo}_fonte1")
    fonte2 = col_f2.text_input("Secundária", value=fontes_salvas[1] if len(fontes_salvas) > 1 else "", key=f"{prefixo}_fonte2")

    return prim_vals, sec_vals, [fonte1.strip(), fonte2.strip()]


# ─────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────

st.set_page_config(page_title="Bob — Produção de Conteúdo", layout="wide")
st.title("Bob · Produção de Conteúdo")

# ── Autenticação Google Drive (sidebar) ──────────────────────────────────────
with st.sidebar:
    st.subheader("Google Drive")
    if drive.esta_autenticado():
        st.success("Autenticado")
        if st.button("Revogar acesso", key="drive_revogar"):
            from pathlib import Path as _P
            _P("config/drive_token.json").unlink(missing_ok=True)
            st.rerun()
    else:
        st.warning("Não autenticado")
        if st.button("Autenticar com Google", key="drive_auth"):
            try:
                drive.autenticar()
                st.success("Autenticado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

aba_gerar, aba_empresas, aba_conteudos = st.tabs(
    ["Gerar Conteúdo", "Empresas", "Conteúdos"]
)

# ─────────────────────────────────────────────
# ABA: Gerar Conteúdo
# ─────────────────────────────────────────────

with aba_gerar:
    empresas = carregar_empresas()

    if not empresas:
        st.warning("Nenhuma empresa cadastrada. Vá para a aba **Empresas** e adicione uma.")
    else:
        nomes = [e["nome"] for e in empresas]
        nome_sel = st.selectbox("Empresa", nomes)
        empresa_sel = next(e for e in empresas if e["nome"] == nome_sel)

        col_info1, col_info2 = st.columns(2)
        col_info1.caption(f"Público-alvo: {empresa_sel['publico_alvo']}")
        url = empresa_sel.get("url_site", "")
        arquivos = listar_arquivos(empresa_sel["id"])
        col_info2.caption(f"Site: {url if url else '—'} · Arquivos: {len(arquivos)}")

        tema = st.text_input("Tema do conteúdo", placeholder="Ex: Integração de sistemas legados com e-commerce")

        ctx_existente = llm_brain.carregar_contexto_compilado(empresa_sel["id"])
        if not ctx_existente:
            st.warning("Contexto editorial não processado. Vá até a aba **Empresas** e clique em **Processar Contexto** antes de gerar.")

        col_btn1, col_btn2 = st.columns(2)

        if col_btn1.button("Gerar conteúdo", type="primary", disabled=not tema.strip(), use_container_width=True):
            with st.spinner("Gerando com Gemini..."):
                try:
                    conteudo = llm_brain.gerar_conteudo(
                        tema=tema.strip(),
                        empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"],
                        publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar conteúdo: {e}")
                    st.stop()

            paths = salvar_conteudo(conteudo, empresa_sel["id"], tema.strip())
            st.session_state.pop("blog_atual", None)
            st.success(f"Salvo em `outputs/{empresa_sel['id']}/` (carrossel, linkedin, vídeo)")
            st.session_state["conteudo_atual"] = conteudo

        if col_btn2.button("Gerar Carrossel Tweet", disabled=not tema.strip(), use_container_width=True):
            with st.spinner("Gerando Carrossel Tweet com Gemini..."):
                try:
                    slides_tweet = llm_brain.gerar_carrossel_tweet(
                        tema=tema.strip(),
                        empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"],
                        publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar Carrossel Tweet: {e}")
                    st.stop()
            path_tweet = salvar_carrossel_tweet(slides_tweet, empresa_sel["id"], tema.strip())
            st.success(f"Carrossel Tweet salvo em `{path_tweet}`")
            st.session_state["tweet_slides_atual"] = slides_tweet

        if st.button("Gerar Carrossel Misto DD", disabled=not tema.strip(), use_container_width=True):
            with st.spinner("Gerando Carrossel Misto DD com Gemini..."):
                try:
                    slides_mdd = llm_brain.gerar_carrossel_misto_dd(
                        tema=tema.strip(),
                        empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"],
                        publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar Carrossel Misto DD: {e}")
                    st.stop()
            path_mdd = salvar_carrossel_misto_dd(slides_mdd, empresa_sel["id"], tema.strip())
            st.success(f"Carrossel Misto DD salvo em `{path_mdd}`")
            st.session_state["misto_dd_slides_atual"] = slides_mdd

        conteudo = st.session_state.get("conteudo_atual")
        if conteudo:
            st.divider()

            sub_c, sub_li, sub_vid, sub_blog = st.tabs(
                ["Carrossel", "Post LinkedIn", "Narração Vídeo", "Blog"]
            )

            with sub_c:
                for slide in conteudo.get("carrossel", []):
                    with st.expander(f"Slide {slide['slide']} — {slide['titulo']}"):
                        st.write(slide["texto"])

            with sub_li:
                post = conteudo.get("post_linkedin") or conteudo.get("artigo_linkedin", "")
                st.caption(f"{len(post)} / 3.000 caracteres")
                st.text_area(" ", post, height=350, label_visibility="collapsed", key="prev_linkedin")

            with sub_vid:
                narracao = conteudo.get("narracao_video") or conteudo.get("roteiro_video", "")
                st.caption(f"{len(narracao.split())} palavras (~{len(narracao.split()) // 3}s de fala)")
                st.text_area(" ", narracao, height=200, label_visibility="collapsed", key="prev_video")

            with sub_blog:
                blog_gerado = st.session_state.get("blog_atual", "")
                if blog_gerado:
                    st.text_area(" ", blog_gerado, height=500, label_visibility="collapsed", key="prev_blog")
                else:
                    st.info("Blog ainda não gerado para este tema.")
                    if st.button("Gerar Blog", type="primary"):
                        with st.spinner("Gerando blog com Gemini..."):
                            try:
                                blog_texto = llm_brain.gerar_blog(
                                    tema=conteudo["tema"],
                                    empresa=empresa_sel["nome"],
                                    empresa_id=empresa_sel["id"],
                                    publico_alvo=empresa_sel["publico_alvo"],
                                    url_site=empresa_sel.get("url_site", ""),
                                )
                            except Exception as e:
                                st.error(f"Erro ao gerar blog: {e}")
                                st.stop()
                        path_blog = salvar_blog(blog_texto, empresa_sel["id"], conteudo["tema"])
                        st.session_state["blog_atual"] = blog_texto
                        st.success(f"Blog salvo em `{path_blog}`")
                        st.rerun()

        tweet_slides = st.session_state.get("tweet_slides_atual")
        if tweet_slides:
            st.divider()
            st.subheader("Carrossel Tweet")
            for slide in tweet_slides:
                with st.expander(f"Slide {slide['slide']} — {slide['titulo']}"):
                    st.write(slide["texto"])

        misto_dd_slides = st.session_state.get("misto_dd_slides_atual")
        if misto_dd_slides:
            st.divider()
            st.subheader("Carrossel Misto DD")
            for slide in misto_dd_slides:
                with st.expander(f"Slide {slide['slide']} — {slide['titulo']}"):
                    st.write(slide["texto"])

# ─────────────────────────────────────────────
# ABA: Empresas
# ─────────────────────────────────────────────

with aba_empresas:
    empresas = carregar_empresas()

    if empresas:
        st.subheader("Empresas cadastradas")
        for i, emp in enumerate(empresas):
            with st.expander(emp["nome"]):

                # ── Dados + identidade visual ─────────────────
                iv = emp.get("identidade_visual", {})

                with st.form(key=f"form_edit_{i}"):
                    st.markdown("**Dados da empresa**")
                    nome     = st.text_input("Nome", value=emp["nome"])
                    setor    = st.text_input("Setor", value=emp.get("setor", ""))
                    publico  = st.text_input("Público-alvo", value=emp.get("publico_alvo", ""))
                    url_site = st.text_input("URL do site", value=emp.get("url_site", ""), placeholder="https://...")
                    descricao = st.text_area("Descrição", value=emp.get("descricao", ""), height=80)
                    tom        = st.text_area("Tom de voz", value=emp.get("tom_de_voz", ""), height=80)
                    estilo_img = st.text_area("Estilo das imagens IA", value=emp.get("estilo_imagem", ""), height=100,
                                              placeholder="Ex: fotografias corporativas de alta qualidade em ambientes de tecnologia, paleta fria, sem pessoas sorrindo de banco de imagens...")
                    drive_folder_id = st.text_input(
                        "ID da pasta Google Drive",
                        value=emp.get("drive_folder_id", ""),
                        placeholder="Ex: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
                        help="Abra a pasta no Drive e copie o ID da URL: drive.google.com/drive/folders/[ID AQUI]",
                    )

                    st.divider()
                    prim_vals, sec_vals, fontes_vals = _campos_identidade_visual(f"edit_{i}", iv)

                    col_salvar, col_excluir = st.columns([1, 1])
                    salvar = col_salvar.form_submit_button("Salvar", type="primary")
                    excluir = col_excluir.form_submit_button("Excluir empresa", type="secondary")

                if salvar:
                    empresas[i] = {
                        "id": emp["id"],
                        "nome": nome,
                        "setor": setor,
                        "publico_alvo": publico,
                        "url_site": url_site.strip(),
                        "descricao": descricao,
                        "tom_de_voz": tom,
                        "estilo_imagem": estilo_img.strip(),
                        "drive_folder_id": drive_folder_id.strip(),
                        "identidade_visual": {
                            "primarias":   _construir_cores(prim_vals),
                            "secundarias": _construir_cores(sec_vals),
                            "fontes": [f for f in fontes_vals if f],
                        },
                    }
                    salvar_empresas(empresas)
                    st.success("Salvo.")
                    st.rerun()

                if excluir:
                    empresas.pop(i)
                    salvar_empresas(empresas)
                    st.success("Empresa removida.")
                    st.rerun()

                # ── Logos da empresa ──────────────────────────
                st.divider()
                col_logo1_hdr, col_logo2_hdr = st.columns(2)

                # Logo principal (1)
                with col_logo1_hdr:
                    st.markdown("**Logo principal**")
                    logo_path = gerador_imagens.logo_empresa(emp["id"], 1)
                    if logo_path:
                        col_logo, col_del_logo = st.columns([3, 1])
                        col_logo.image(str(logo_path), width=160)
                        if col_del_logo.button("Remover", key=f"del_logo_{emp['id']}"):
                            logo_path.unlink()
                            st.success("Logo removida.")
                            st.rerun()
                    logo_upload = st.file_uploader(
                        "Enviar logo principal (PNG, JPG ou WEBP)",
                        type=["png", "jpg", "jpeg", "webp"],
                        key=f"logo_upload_{emp['id']}",
                        label_visibility="collapsed",
                    )
                    if logo_upload:
                        from pathlib import Path as _Path
                        logos_dir = _Path("config/logos")
                        logos_dir.mkdir(parents=True, exist_ok=True)
                        for old in logos_dir.glob(f"{emp['id']}.*"):
                            if "_" not in old.stem.replace(emp["id"], ""):
                                old.unlink()
                        ext  = logo_upload.name.rsplit(".", 1)[-1].lower()
                        dest = logos_dir / f"{emp['id']}.{ext}"
                        dest.write_bytes(logo_upload.getvalue())
                        st.success("Logo principal salva!")
                        st.rerun()

                # Logo alternativa (2)
                with col_logo2_hdr:
                    st.markdown("**Logo alternativa (2ª opção)**")
                    logo2_path = gerador_imagens.logo_empresa(emp["id"], 2)
                    if logo2_path:
                        col_logo2, col_del_logo2 = st.columns([3, 1])
                        col_logo2.image(str(logo2_path), width=160)
                        if col_del_logo2.button("Remover", key=f"del_logo2_{emp['id']}"):
                            logo2_path.unlink()
                            st.success("Logo alternativa removida.")
                            st.rerun()
                    logo2_upload = st.file_uploader(
                        "Enviar logo alternativa (PNG, JPG ou WEBP)",
                        type=["png", "jpg", "jpeg", "webp"],
                        key=f"logo2_upload_{emp['id']}",
                        label_visibility="collapsed",
                    )
                    if logo2_upload:
                        from pathlib import Path as _Path
                        logos_dir = _Path("config/logos")
                        logos_dir.mkdir(parents=True, exist_ok=True)
                        for old in logos_dir.glob(f"{emp['id']}_2.*"):
                            old.unlink()
                        ext  = logo2_upload.name.rsplit(".", 1)[-1].lower()
                        dest = logos_dir / f"{emp['id']}_2.{ext}"
                        dest.write_bytes(logo2_upload.getvalue())
                        st.success("Logo alternativa salva!")
                        st.rerun()

                # ── Contexto editorial compilado ──────────────
                st.divider()
                st.markdown("**Contexto editorial compilado**")

                ctx_path  = llm_brain.caminho_contexto(emp["id"])
                ctx_texto = llm_brain.carregar_contexto_compilado(emp["id"])

                if ctx_texto:
                    ts_ctx = datetime.fromtimestamp(ctx_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    st.caption(f"Última atualização: {ts_ctx}")
                else:
                    st.caption("Nenhum contexto compilado ainda.")

                ctx_editado = st.text_area(
                    "Contexto",
                    value=ctx_texto,
                    height=250,
                    key=f"ctx_{emp['id']}",
                    placeholder="Clique em 'Processar Contexto' para gerar automaticamente, ou escreva manualmente.",
                    label_visibility="collapsed",
                )

                col_proc, col_salvar_ctx = st.columns([2, 1])

                if col_proc.button("Processar Contexto", key=f"proc_{emp['id']}"):
                    url = emp.get("url_site", "")
                    arqs = listar_arquivos(emp["id"])
                    if not url and not arqs:
                        st.error("Adicione o site ou arquivos antes de processar.")
                    else:
                        with st.spinner("Compilando contexto com Gemini..."):
                            try:
                                llm_brain.processar_contexto(
                                    empresa_id=emp["id"],
                                    empresa_nome=emp["nome"],
                                    url_site=url,
                                )
                                st.success("Contexto compilado e salvo.")
                                st.session_state.pop(f"ctx_{emp['id']}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")

                if col_salvar_ctx.button("Salvar edição", key=f"save_ctx_{emp['id']}"):
                    llm_brain.salvar_contexto_compilado(emp["id"], ctx_editado)
                    st.success("Contexto salvo.")
                    st.session_state.pop(f"ctx_{emp['id']}", None)
                    st.rerun()

                # ── Arquivos de contexto ──────────────────────
                st.divider()
                st.markdown("**Arquivos de contexto** (PDF, DOCX)")

                arqs = listar_arquivos(emp["id"])
                if arqs:
                    for arq in arqs:
                        col_nome, col_del = st.columns([5, 1])
                        col_nome.write(f"📄 {arq.name}")
                        if col_del.button("Remover", key=f"del_{emp['id']}_{arq.name}"):
                            arq.unlink()
                            st.success(f"'{arq.name}' removido.")
                            st.rerun()
                else:
                    st.caption("Nenhum arquivo enviado ainda.")

                uploaded = st.file_uploader(
                    "Adicionar arquivo",
                    type=["pdf", "docx", "doc"],
                    key=f"upload_{emp['id']}",
                    label_visibility="collapsed",
                )
                if uploaded:
                    dest = pasta_arquivos(emp["id"]) / uploaded.name
                    dest.write_bytes(uploaded.getvalue())
                    st.success(f"'{uploaded.name}' salvo.")
                    st.rerun()

    st.divider()
    st.subheader("Adicionar empresa")

    with st.form("form_nova"):
        nome      = st.text_input("Nome *")
        setor     = st.text_input("Setor")
        publico   = st.text_input("Público-alvo *")
        url_site  = st.text_input("URL do site", placeholder="https://...")
        descricao = st.text_area("Descrição", height=80)
        tom       = st.text_area("Tom de voz", height=80)
        estilo_img_nova = st.text_area(
            "Estilo das imagens IA", height=100, key="nova_estilo_img",
            placeholder="Ex: fotografias corporativas de alta qualidade em ambientes de tecnologia, paleta fria, sem pessoas sorrindo de banco de imagens...",
        )
        drive_folder_id_nova = st.text_input(
            "ID da pasta Google Drive", key="nova_drive_folder",
            placeholder="Ex: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
            help="Abra a pasta no Drive e copie o ID da URL: drive.google.com/drive/folders/[ID AQUI]",
        )

        st.divider()
        prim_vals, sec_vals, fontes_vals = _campos_identidade_visual("nova", {})

        adicionar = st.form_submit_button("Adicionar", type="primary")

    if adicionar:
        if not nome.strip() or not publico.strip():
            st.error("Nome e Público-alvo são obrigatórios.")
        else:
            nova = {
                "id": nome.strip().lower().replace(" ", "_"),
                "nome": nome.strip(),
                "setor": setor.strip(),
                "publico_alvo": publico.strip(),
                "url_site": url_site.strip(),
                "descricao": descricao.strip(),
                "tom_de_voz": tom.strip(),
                "estilo_imagem": estilo_img_nova.strip(),
                "drive_folder_id": drive_folder_id_nova.strip(),
                "identidade_visual": {
                    "primarias":   _construir_cores(prim_vals),
                    "secundarias": _construir_cores(sec_vals),
                    "fontes": [f for f in fontes_vals if f],
                },
            }
            empresas.append(nova)
            salvar_empresas(empresas)
            st.success(f"Empresa '{nome}' adicionada.")
            st.rerun()

# ─────────────────────────────────────────────
# ABA: Conteúdos
# ─────────────────────────────────────────────

TIPOS = {
    "carrossel":          "Carrossel",
    "carrossel_tweet":    "Carrossel Tweet",
    "carrossel_misto_dd": "Carrossel Misto DD",
    "linkedin":           "Post LinkedIn",
    "video":              "Narração Vídeo",
    "blog":               "Blog",
}

with aba_conteudos:
    empresas = carregar_empresas()

    if not empresas:
        st.info("Nenhuma empresa cadastrada.")
    else:
        for emp in empresas:
            # Verifica se há algum conteúdo para esta empresa
            tem_conteudo = any(
                listar_conteudos(emp["id"], tipo) for tipo in TIPOS
            )
            total = sum(len(listar_conteudos(emp["id"], t)) for t in TIPOS)
            label = f"{emp['nome']}  —  {total} conteúdo(s)" if total else emp["nome"]

            with st.expander(label, expanded=tem_conteudo and len(empresas) == 1):
                if not tem_conteudo:
                    st.caption("Nenhum conteúdo gerado ainda.")
                    continue

                sub_carrossel, sub_tweet, sub_misto_dd, sub_linkedin, sub_video, sub_blog = st.tabs(
                    [TIPOS["carrossel"], TIPOS["carrossel_tweet"], TIPOS["carrossel_misto_dd"],
                     TIPOS["linkedin"], TIPOS["video"], TIPOS["blog"]]
                )

                def _botao_excluir(emp_id: str, stem: str, tipo: str):
                    if st.button("Excluir", key=f"del_{tipo}_{emp_id}_{stem}", type="secondary"):
                        excluir_conteudo(emp_id, stem)
                        st.success("Conteúdo excluído.")
                        st.rerun()

                def _listar_md(tipo: str, altura: int, prefixo: str, fn_regenerar=None):
                    arquivos = listar_conteudos(emp["id"], tipo)
                    if not arquivos:
                        st.caption("Nenhum conteúdo gerado ainda.")
                        return
                    for path in arquivos:
                        data  = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                        texto = path.read_text(encoding="utf-8")
                        linhas = texto.splitlines()
                        tema_arq = linhas[0].lstrip("# ") if linhas else path.stem
                        corpo    = "\n".join(linhas[2:]) if len(linhas) > 2 else texto
                        with st.expander(f"{tema_arq}  ·  {data}"):
                            btn_cols = st.columns([1, 1, 5]) if fn_regenerar else st.columns([1, 6])
                            if btn_cols[0].button("Excluir", key=f"del_{tipo}_{emp['id']}_{path.stem}", type="secondary"):
                                excluir_conteudo(emp["id"], path.stem)
                                st.success("Conteúdo excluído.")
                                st.rerun()
                            if fn_regenerar and btn_cols[1].button("↺ Regenerar", key=f"regen_{tipo}_{path.stem}"):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novo = fn_regenerar(tema_arq)
                                        path.write_text(f"# {tema_arq}\n\n{novo}", encoding="utf-8")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
                            st.text_area(" ", corpo, height=altura, key=f"{prefixo}_{path.stem}", label_visibility="collapsed")

                with sub_carrossel:
                    arquivos = listar_conteudos(emp["id"], "carrossel")
                    if not arquivos:
                        st.caption("Nenhum carrossel gerado.")
                    for path in arquivos:
                        data = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                        with open(path, encoding="utf-8") as f:
                            dados = json.load(f)
                        tema_arq = dados.get("tema", path.stem)
                        with st.expander(f"{tema_arq}  ·  {data}"):
                            col_del, col_regen_texto, _esp = st.columns([1, 2, 3])
                            if col_del.button("Excluir", key=f"del_carrossel_{emp['id']}_{path.stem}", type="secondary"):
                                excluir_conteudo(emp["id"], path.stem)
                                st.success("Conteúdo excluído.")
                                st.rerun()
                            if col_regen_texto.button("↺ Regenerar texto", key=f"regen_slides_{path.stem}", use_container_width=True):
                                with st.spinner("Regenerando carrossel..."):
                                    try:
                                        novos_slides = llm_brain.gerar_slides_carrossel(
                                            tema=dados.get("tema", ""),
                                            empresa=dados.get("empresa", emp["nome"]),
                                            empresa_id=emp["id"],
                                            publico_alvo=dados.get("publico_alvo", emp["publico_alvo"]),
                                            url_site=emp.get("url_site", ""),
                                        )
                                        dados["slides"] = novos_slides
                                        with open(path, "w", encoding="utf-8") as _f:
                                            json.dump(dados, _f, ensure_ascii=False, indent=2)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            # ── Imagens ──────────────────────────────
                            imagens = gerador_imagens.listar_imagens(emp["id"], path.stem)
                            iv = {
                                **emp.get("identidade_visual", {}),
                                "estilo_imagem": emp.get("estilo_imagem", ""),
                                "url_site": emp.get("url_site", ""),
                            }

                            # Seletor de logo (mostra apenas se houver 2ª logo cadastrada)
                            _logo_idx = 1
                            if gerador_imagens.logo_empresa(emp["id"], 2):
                                _logos_opts = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                _logo_sel = st.radio(
                                    "Logo",
                                    _logos_opts,
                                    horizontal=True,
                                    key=f"logo_radio_{path.stem}",
                                    label_visibility="collapsed",
                                )
                                _logo_idx = 2 if _logo_sel == _logos_opts[1] else 1

                            if imagens:
                                col_cap, col_baixar, col_drive, col_regen = st.columns([2, 1, 1, 1])
                                col_cap.caption(f"{len(imagens)} imagem(ns) gerada(s)")
                                regenerar_tudo = col_regen.button("↺ Regenerar tudo", key=f"regen_img_{path.stem}", use_container_width=True)

                                folder_id = emp.get("drive_folder_id", "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                                if col_drive.button("📤 Drive", key=f"drive_{path.stem}", use_container_width=True, disabled=not folder_id):
                                    with st.spinner("Enviando para o Google Drive..."):
                                        try:
                                            resultados, nome_pasta = drive.enviar_carrossel_drive(imagens, folder_id)
                                            st.success(f"{len(resultados)} imagens enviadas para a pasta **{nome_pasta}** no Drive!")
                                        except Exception as e:
                                            st.error(f"Erro ao enviar para o Drive: {e}")
                                if not folder_id:
                                    col_drive.caption("Configure o ID da pasta na aba Empresas")

                                zip_buf = io.BytesIO()
                                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, img_path in enumerate(imagens):
                                        zf.write(img_path, arcname=f"{idx + 1}.png")
                                zip_buf.seek(0)
                                col_baixar.download_button(
                                    label="↓ Baixar tudo",
                                    data=zip_buf,
                                    file_name=f"{path.stem}.zip",
                                    mime="application/zip",
                                    key=f"dl_zip_{path.stem}",
                                    use_container_width=True,
                                )
                                cols = st.columns(3)
                                for idx, img_path in enumerate(imagens):
                                    slide_n = int(img_path.stem.split("_")[-1])
                                    with cols[idx % 3]:
                                        st.image(str(img_path), use_container_width=True)
                                        col_dl, col_rs = st.columns(2)
                                        with open(img_path, "rb") as img_f:
                                            col_dl.download_button(
                                                label="↓ Baixar",
                                                data=img_f.read(),
                                                file_name=img_path.name,
                                                mime="image/png",
                                                key=f"dl_{path.stem}_{idx}",
                                                use_container_width=True,
                                            )
                                        # Selectbox de estilo para slides com variante
                                        _variante_sel = None
                                        if slide_n in _OPCOES_ESTILO_SLIDE:
                                            _nomes = [o[0] for o in _OPCOES_ESTILO_SLIDE[slide_n]]
                                            _vals  = {o[0]: o[1] for o in _OPCOES_ESTILO_SLIDE[slide_n]}
                                            _sel   = st.selectbox(
                                                "Estilo",
                                                _nomes,
                                                key=f"est_{path.stem}_{slide_n}",
                                                label_visibility="collapsed",
                                            )
                                            _variante_sel = _vals[_sel]

                                        if col_rs.button("↺ Slide", key=f"regen_slide_{path.stem}_{idx}", use_container_width=True):
                                            slide_data = next(
                                                (s for s in dados.get("slides", []) if s.get("slide") == slide_n),
                                                None,
                                            )
                                            if slide_data:
                                                with st.spinner(f"Regenerando slide {slide_n}..."):
                                                    try:
                                                        total_slides = len(dados.get("slides", []))
                                                        gerador_imagens.gerar_imagem_slide(
                                                            slide=slide_data,
                                                            empresa_id=emp["id"],
                                                            stem=path.stem,
                                                            identidade_visual=iv,
                                                            is_ultimo=(slide_n == total_slides),
                                                            variante_override=_variante_sel,
                                                            logo_index=_logo_idx,
                                                        )
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regenerar_tudo = False

                            if not imagens or regenerar_tudo:
                                if regenerar_tudo or st.button("Gerar Imagens", key=f"gen_img_{path.stem}", type="primary"):
                                    slides = dados.get("slides", [])
                                    barra  = st.progress(0, text="Iniciando...")
                                    status = st.empty()

                                    def _progresso(n, total):
                                        barra.progress(n / total, text=f"Gerando slide {n} de {total}...")
                                        status.caption(f"Slide {n}/{total} concluído.")

                                    try:
                                        gerador_imagens.gerar_imagens_carrossel(
                                            slides=slides,
                                            empresa_id=emp["id"],
                                            stem=path.stem,
                                            identidade_visual=iv,
                                            callback=_progresso,
                                            logo_index=_logo_idx,
                                        )
                                        barra.empty()
                                        status.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            for slide in dados.get("slides", []):
                                st.markdown(f"**Slide {slide['slide']} — {slide['titulo']}**")
                                st.write(slide["texto"])
                                if slide.get("prompt_imagem"):
                                    st.caption(f"🖼️ Imagem: {slide['prompt_imagem']}")
                                st.divider()

                with sub_tweet:
                    arquivos_tw = listar_conteudos(emp["id"], "carrossel_tweet")
                    if not arquivos_tw:
                        st.caption("Nenhum Carrossel Tweet gerado.")
                    for path_tw in arquivos_tw:
                        data_tw = datetime.fromtimestamp(path_tw.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                        with open(path_tw, encoding="utf-8") as f_tw:
                            dados_tw = json.load(f_tw)
                        tema_tw = dados_tw.get("tema", path_tw.stem)
                        with st.expander(f"{tema_tw}  ·  {data_tw}"):
                            col_del_tw, col_regen_tw, _esp_tw = st.columns([1, 2, 3])
                            if col_del_tw.button("Excluir", key=f"del_tweet_{emp['id']}_{path_tw.stem}", type="secondary"):
                                excluir_conteudo(emp["id"], path_tw.stem)
                                st.success("Conteúdo excluído.")
                                st.rerun()
                            if col_regen_tw.button("↺ Regenerar texto", key=f"regen_tweet_{path_tw.stem}", use_container_width=True):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novos_tw = llm_brain.gerar_carrossel_tweet(
                                            tema=tema_tw,
                                            empresa=emp["nome"],
                                            empresa_id=emp["id"],
                                            publico_alvo=emp["publico_alvo"],
                                            url_site=emp.get("url_site", ""),
                                        )
                                        dados_tw["slides"] = novos_tw
                                        with open(path_tw, "w", encoding="utf-8") as _f:
                                            json.dump(dados_tw, _f, ensure_ascii=False, indent=2)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            # ── Imagens Tweet ─────────────────────────
                            imagens_tw = gerador_imagens.listar_imagens_tweet(emp["id"], path_tw.stem)
                            iv_tw = {
                                **emp.get("identidade_visual", {}),
                                "estilo_imagem": emp.get("estilo_imagem", ""),
                            }

                            # Seletor de logo + cor do círculo
                            _logo_idx_tw = 1
                            _cor_circ_tw = "#1d9bf0"
                            _tw_col1, _tw_col2 = st.columns([2, 1])
                            with _tw_col1:
                                if gerador_imagens.logo_empresa(emp["id"], 2):
                                    _logos_opts_tw = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                    _logo_sel_tw = st.radio(
                                        "Logo",
                                        _logos_opts_tw,
                                        horizontal=True,
                                        key=f"logo_radio_tw_{path_tw.stem}",
                                        label_visibility="collapsed",
                                    )
                                    _logo_idx_tw = 2 if _logo_sel_tw == _logos_opts_tw[1] else 1
                            with _tw_col2:
                                _cor_circ_tw = st.color_picker(
                                    "Cor do círculo",
                                    value="#1d9bf0",
                                    key=f"cor_circ_tw_{path_tw.stem}",
                                )

                            if imagens_tw:
                                col_cap_tw, col_baixar_tw, col_regen_img_tw = st.columns([3, 1, 1])
                                col_cap_tw.caption(f"{len(imagens_tw)} imagem(ns) gerada(s)")
                                regen_tw_tudo = col_regen_img_tw.button("↺ Regenerar tudo", key=f"regen_tw_img_{path_tw.stem}", use_container_width=True)

                                zip_buf_tw = io.BytesIO()
                                with zipfile.ZipFile(zip_buf_tw, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, ip in enumerate(imagens_tw):
                                        zf.write(ip, arcname=f"{idx + 1}.png")
                                zip_buf_tw.seek(0)
                                col_baixar_tw.download_button(
                                    label="↓ Baixar tudo",
                                    data=zip_buf_tw,
                                    file_name=f"{path_tw.stem}_tweet.zip",
                                    mime="application/zip",
                                    key=f"dl_zip_tw_{path_tw.stem}",
                                    use_container_width=True,
                                )
                                cols_tw = st.columns(3)
                                for idx, img_path_tw in enumerate(imagens_tw):
                                    slide_n_tw = int(img_path_tw.stem.split("_")[-1])
                                    with cols_tw[idx % 3]:
                                        st.image(str(img_path_tw), use_container_width=True)
                                        col_dl_tw, col_rs_tw = st.columns(2)
                                        with open(img_path_tw, "rb") as img_f_tw:
                                            col_dl_tw.download_button(
                                                label="↓ Baixar",
                                                data=img_f_tw.read(),
                                                file_name=img_path_tw.name,
                                                mime="image/png",
                                                key=f"dl_tw_{path_tw.stem}_{idx}",
                                                use_container_width=True,
                                            )
                                        if col_rs_tw.button("↺ Slide", key=f"regen_slide_tw_{path_tw.stem}_{idx}", use_container_width=True):
                                            slide_data_tw = next(
                                                (s for s in dados_tw.get("slides", []) if s.get("slide") == slide_n_tw),
                                                None,
                                            )
                                            if slide_data_tw:
                                                with st.spinner(f"Regenerando slide {slide_n_tw}..."):
                                                    try:
                                                        gerador_imagens.gerar_imagem_slide_tweet(
                                                            slide=slide_data_tw,
                                                            empresa_id=emp["id"],
                                                            empresa_nome=emp["nome"],
                                                            stem=path_tw.stem,
                                                            identidade_visual=iv_tw,
                                                            logo_index=_logo_idx_tw,
                                                            cor_circulo_hex=_cor_circ_tw,
                                                        )
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regen_tw_tudo = False

                            if not imagens_tw or regen_tw_tudo:
                                if regen_tw_tudo or st.button("Gerar Imagens", key=f"gen_img_tw_{path_tw.stem}", type="primary"):
                                    slides_tw = dados_tw.get("slides", [])
                                    barra_tw  = st.progress(0, text="Iniciando...")
                                    status_tw = st.empty()

                                    def _prog_tw(n, total):
                                        barra_tw.progress(n / total, text=f"Gerando slide {n} de {total}...")
                                        status_tw.caption(f"Slide {n}/{total} concluído.")

                                    try:
                                        gerador_imagens.gerar_imagens_carrossel_tweet(
                                            slides=slides_tw,
                                            empresa_id=emp["id"],
                                            empresa_nome=emp["nome"],
                                            stem=path_tw.stem,
                                            identidade_visual=iv_tw,
                                            logo_index=_logo_idx_tw,
                                            cor_circulo_hex=_cor_circ_tw,
                                            callback=_prog_tw,
                                        )
                                        barra_tw.empty()
                                        status_tw.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            for slide in dados_tw.get("slides", []):
                                st.markdown(f"**Slide {slide['slide']} — {slide['titulo']}**")
                                st.write(slide["texto"])
                                st.divider()

                with sub_misto_dd:
                    arquivos_mdd = listar_conteudos(emp["id"], "carrossel_misto_dd")
                    if not arquivos_mdd:
                        st.caption("Nenhum Carrossel Misto DD gerado.")
                    for path_mdd in arquivos_mdd:
                        data_mdd = datetime.fromtimestamp(path_mdd.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                        with open(path_mdd, encoding="utf-8") as f_mdd:
                            dados_mdd = json.load(f_mdd)
                        tema_mdd = dados_mdd.get("tema", path_mdd.stem)
                        with st.expander(f"{tema_mdd}  ·  {data_mdd}"):
                            col_del_mdd, col_regen_mdd, _esp_mdd = st.columns([1, 2, 3])
                            if col_del_mdd.button("Excluir", key=f"del_mdd_{emp['id']}_{path_mdd.stem}", type="secondary"):
                                excluir_conteudo(emp["id"], path_mdd.stem)
                                st.success("Conteúdo excluído.")
                                st.rerun()
                            if col_regen_mdd.button("↺ Regenerar texto", key=f"regen_mdd_{path_mdd.stem}", use_container_width=True):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novos_mdd = llm_brain.gerar_carrossel_misto_dd(
                                            tema=tema_mdd,
                                            empresa=emp["nome"],
                                            empresa_id=emp["id"],
                                            publico_alvo=emp["publico_alvo"],
                                            url_site=emp.get("url_site", ""),
                                        )
                                        dados_mdd["slides"] = novos_mdd
                                        with open(path_mdd, "w", encoding="utf-8") as _f:
                                            json.dump(dados_mdd, _f, ensure_ascii=False, indent=2)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            # ── Imagens Misto DD ───────────────────────────
                            imagens_mdd = gerador_imagens.listar_imagens_misto_dd(emp["id"], path_mdd.stem)
                            iv_mdd = {
                                **emp.get("identidade_visual", {}),
                                "estilo_imagem": emp.get("estilo_imagem", ""),
                                "url_site": emp.get("url_site", ""),
                            }

                            _logo_idx_mdd = 1
                            if gerador_imagens.logo_empresa(emp["id"], 2):
                                _logos_opts_mdd = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                _logo_sel_mdd = st.radio(
                                    "Logo",
                                    _logos_opts_mdd,
                                    horizontal=True,
                                    key=f"logo_radio_mdd_{path_mdd.stem}",
                                    label_visibility="collapsed",
                                )
                                _logo_idx_mdd = 2 if _logo_sel_mdd == _logos_opts_mdd[1] else 1

                            if imagens_mdd:
                                col_cap_mdd, col_baixar_mdd, col_drive_mdd, col_regen_mdd_img = st.columns([2, 1, 1, 1])
                                col_cap_mdd.caption(f"{len(imagens_mdd)} imagem(ns) gerada(s)")
                                regen_mdd_tudo = col_regen_mdd_img.button("↺ Regenerar tudo", key=f"regen_mdd_img_{path_mdd.stem}", use_container_width=True)

                                folder_id_mdd = emp.get("drive_folder_id", "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                                if col_drive_mdd.button("📤 Drive", key=f"drive_mdd_{path_mdd.stem}", use_container_width=True, disabled=not folder_id_mdd):
                                    with st.spinner("Enviando para o Google Drive..."):
                                        try:
                                            resultados, nome_pasta = drive.enviar_carrossel_drive(imagens_mdd, folder_id_mdd)
                                            st.success(f"{len(resultados)} imagens enviadas para **{nome_pasta}** no Drive!")
                                        except Exception as e:
                                            st.error(f"Erro ao enviar para o Drive: {e}")
                                if not folder_id_mdd:
                                    col_drive_mdd.caption("Configure o ID da pasta na aba Empresas")

                                zip_buf_mdd = io.BytesIO()
                                with zipfile.ZipFile(zip_buf_mdd, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, ip in enumerate(imagens_mdd):
                                        zf.write(ip, arcname=f"{idx + 1}.png")
                                zip_buf_mdd.seek(0)
                                col_baixar_mdd.download_button(
                                    label="↓ Baixar tudo",
                                    data=zip_buf_mdd,
                                    file_name=f"{path_mdd.stem}_misto_dd.zip",
                                    mime="application/zip",
                                    key=f"dl_zip_mdd_{path_mdd.stem}",
                                    use_container_width=True,
                                )

                                cols_mdd = st.columns(3)
                                for idx, img_path_mdd in enumerate(imagens_mdd):
                                    slide_n_mdd = int(img_path_mdd.stem.split("_")[-1])
                                    with cols_mdd[idx % 3]:
                                        st.image(str(img_path_mdd), use_container_width=True)
                                        fundo_key = f"fundo_ok_mdd_{path_mdd.stem}_{idx}"
                                        fundo_ok  = st.checkbox("Fundo ok", key=fundo_key)
                                        col_dl_mdd, col_rs_mdd = st.columns(2)
                                        with open(img_path_mdd, "rb") as img_f_mdd:
                                            col_dl_mdd.download_button(
                                                label="↓ Baixar",
                                                data=img_f_mdd.read(),
                                                file_name=img_path_mdd.name,
                                                mime="image/png",
                                                key=f"dl_mdd_{path_mdd.stem}_{idx}",
                                                use_container_width=True,
                                            )
                                        if col_rs_mdd.button("↺ Slide", key=f"regen_slide_mdd_{path_mdd.stem}_{idx}", use_container_width=True):
                                            slide_data_mdd = next(
                                                (s for s in dados_mdd.get("slides", []) if s.get("slide") == slide_n_mdd),
                                                None,
                                            )
                                            if slide_data_mdd:
                                                with st.spinner(f"Regenerando slide {slide_n_mdd}..."):
                                                    try:
                                                        gerador_imagens.gerar_imagem_slide_misto_dd(
                                                            slide=slide_data_mdd,
                                                            empresa_id=emp["id"],
                                                            empresa_nome=emp["nome"],
                                                            stem=path_mdd.stem,
                                                            identidade_visual=iv_mdd,
                                                            logo_index=_logo_idx_mdd,
                                                            fundo_fixo=fundo_ok,
                                                        )
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regen_mdd_tudo = False

                            if not imagens_mdd or regen_mdd_tudo:
                                if regen_mdd_tudo or st.button("Gerar Imagens", key=f"gen_img_mdd_{path_mdd.stem}", type="primary"):
                                    slides_mdd_gen = dados_mdd.get("slides", [])
                                    barra_mdd  = st.progress(0, text="Iniciando...")
                                    status_mdd = st.empty()

                                    def _prog_mdd(n, total):
                                        barra_mdd.progress(n / total, text=f"Gerando slide {n} de {total}...")
                                        status_mdd.caption(f"Slide {n}/{total} concluído.")

                                    try:
                                        gerador_imagens.gerar_imagens_carrossel_misto_dd(
                                            slides=slides_mdd_gen,
                                            empresa_id=emp["id"],
                                            empresa_nome=emp["nome"],
                                            stem=path_mdd.stem,
                                            identidade_visual=iv_mdd,
                                            logo_index=_logo_idx_mdd,
                                            callback=_prog_mdd,
                                        )
                                        barra_mdd.empty()
                                        status_mdd.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            for slide in dados_mdd.get("slides", []):
                                st.markdown(f"**Slide {slide['slide']} — {slide['titulo']}**")
                                st.write(slide["texto"])
                                if slide.get("prompt_imagem") is not None:
                                    _edit_key = f"edit_prompt_{path_mdd.stem}_{slide['slide']}"
                                    _col_p, _col_e = st.columns([6, 1])
                                    _col_p.caption(f"🖼️ {slide['prompt_imagem']}")
                                    if _col_e.button("✏️", key=f"btn_ep_{path_mdd.stem}_{slide['slide']}", help="Editar prompt de imagem"):
                                        st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)
                                    if st.session_state.get(_edit_key, False):
                                        _novo_prompt = st.text_area(
                                            "Prompt",
                                            value=slide["prompt_imagem"],
                                            key=f"ta_ep_{path_mdd.stem}_{slide['slide']}",
                                            label_visibility="collapsed",
                                        )
                                        _cs, _csr = st.columns(2)
                                        if _cs.button("💾 Salvar", key=f"sv_ep_{path_mdd.stem}_{slide['slide']}", use_container_width=True):
                                            slide["prompt_imagem"] = _novo_prompt
                                            with open(path_mdd, "w", encoding="utf-8") as _fp:
                                                json.dump(dados_mdd, _fp, ensure_ascii=False, indent=2)
                                            st.session_state[_edit_key] = False
                                            st.rerun()
                                        if _csr.button("💾 Salvar e Regenerar", key=f"svr_ep_{path_mdd.stem}_{slide['slide']}", use_container_width=True):
                                            slide["prompt_imagem"] = _novo_prompt
                                            with open(path_mdd, "w", encoding="utf-8") as _fp:
                                                json.dump(dados_mdd, _fp, ensure_ascii=False, indent=2)
                                            with st.spinner(f"Regenerando slide {slide['slide']}..."):
                                                try:
                                                    gerador_imagens.gerar_imagem_slide_misto_dd(
                                                        slide=slide,
                                                        empresa_id=emp["id"],
                                                        empresa_nome=emp["nome"],
                                                        stem=path_mdd.stem,
                                                        identidade_visual=iv_mdd,
                                                        logo_index=_logo_idx_mdd,
                                                    )
                                                    st.session_state[_edit_key] = False
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Erro: {e}")
                                st.divider()

                with sub_linkedin:
                    _listar_md("linkedin", 300, "li",
                        fn_regenerar=lambda tema: llm_brain.gerar_linkedin(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))

                with sub_video:
                    _listar_md("video", 200, "vid",
                        fn_regenerar=lambda tema: llm_brain.gerar_narracao(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))

                with sub_blog:
                    _listar_md("blog", 500, "blog",
                        fn_regenerar=lambda tema: llm_brain.gerar_blog(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))
