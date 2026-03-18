import json
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from modulos import llm_brain, gerador_imagens

load_dotenv()

CONFIG_PATH = Path("config/empresas.json")
OUTPUTS_DIR = Path("outputs")
ARQUIVOS_DIR = Path("config/arquivos")


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

        if st.button("Gerar conteúdo", type="primary", disabled=not tema.strip()):
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
    "carrossel": "Carrossel",
    "linkedin":  "Post LinkedIn",
    "video":     "Narração Vídeo",
    "blog":      "Blog",
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

                sub_carrossel, sub_linkedin, sub_video, sub_blog = st.tabs(
                    [TIPOS["carrossel"], TIPOS["linkedin"], TIPOS["video"], TIPOS["blog"]]
                )

                def _botao_excluir(emp_id: str, stem: str, tipo: str):
                    if st.button("Excluir", key=f"del_{tipo}_{emp_id}_{stem}", type="secondary"):
                        excluir_conteudo(emp_id, stem)
                        st.success("Conteúdo excluído.")
                        st.rerun()

                def _listar_md(tipo: str, altura: int, prefixo: str):
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
                            _botao_excluir(emp["id"], path.stem, tipo)
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
                            _botao_excluir(emp["id"], path.stem, "carrossel")

                            # ── Imagens ──────────────────────────────
                            imagens = gerador_imagens.listar_imagens(emp["id"], path.stem)

                            if imagens:
                                col_cap, col_regen = st.columns([4, 1])
                                col_cap.caption(f"{len(imagens)} imagem(ns) gerada(s)")
                                regenerar = col_regen.button("Regenerar", key=f"regen_img_{path.stem}")
                                cols = st.columns(3)
                                for idx, img_path in enumerate(imagens):
                                    with cols[idx % 3]:
                                        st.image(str(img_path), use_container_width=True)
                                        with open(img_path, "rb") as img_f:
                                            st.download_button(
                                                label=f"↓ Slide {idx+1}",
                                                data=img_f,
                                                file_name=img_path.name,
                                                mime="image/png",
                                                key=f"dl_{path.stem}_{idx}",
                                            )
                            else:
                                regenerar = False

                            if not imagens or regenerar:
                                iv = {
                                    **emp.get("identidade_visual", {}),
                                    "estilo_imagem": emp.get("estilo_imagem", ""),
                                }
                                if regenerar or st.button("Gerar Imagens", key=f"gen_img_{path.stem}", type="primary"):
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
                                st.divider()

                with sub_linkedin:
                    _listar_md("linkedin", 300, "li")

                with sub_video:
                    _listar_md("video", 200, "vid")

                with sub_blog:
                    _listar_md("blog", 500, "blog")
