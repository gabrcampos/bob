import io
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from modulos import llm_brain, gerador_imagens, drive, db, docs

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


def salvar_conteudo(
    conteudo: dict,
    empresa_id: str,
    tema: str,
    empresa_sel: dict,
    *,
    opt_linkedin: bool = True,
    opt_video: bool = True,
) -> str:
    """Salva conteúdo padrão no MongoDB. Retorna o _id do documento."""
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="carrossel",
        tema=tema,
        slides=conteudo.get("carrossel", []),
        legenda=conteudo.get("legenda", ""),
        post_linkedin=conteudo.get("post_linkedin", "") if opt_linkedin else "",
        narracao_video=conteudo.get("narracao_video", "") if opt_video else "",
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def salvar_carrossel_tweet(dados: dict, empresa_id: str, tema: str, empresa_sel: dict) -> str:
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="carrossel_tweet",
        tema=tema,
        slides=dados.get("slides", []),
        legenda=dados.get("legenda", ""),
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def salvar_carrossel_misto_dd(dados: dict, empresa_id: str, tema: str, empresa_sel: dict) -> str:
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="carrossel_misto_dd",
        tema=tema,
        slides=dados.get("slides", []),
        legenda=dados.get("legenda", ""),
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def salvar_linkedin(texto: str, empresa_id: str, tema: str, empresa_sel: dict) -> str:
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="linkedin",
        tema=tema,
        post_linkedin=texto,
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def salvar_video(texto: str, empresa_id: str, tema: str, empresa_sel: dict) -> str:
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="video",
        tema=tema,
        narracao_video=texto,
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def salvar_blog(texto: str, empresa_id: str, tema: str, empresa_sel: dict) -> str:
    return db.salvar_conteudo(
        empresa_id=empresa_id,
        tipo="blog",
        tema=tema,
        blog=texto,
        empresa_nome=empresa_sel.get("nome", ""),
        publico_alvo=empresa_sel.get("publico_alvo", ""),
    )


def listar_conteudos(empresa_id: str, tipo: str) -> list[dict]:
    return db.listar_conteudos(empresa_id, tipo)


def excluir_conteudo(conteudo_id: str):
    """Remove conteúdo e seus agendamentos do banco."""
    db.excluir_conteudo(conteudo_id)


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
# Checklist de status
# ─────────────────────────────────────────────

def _checklist_status(doc: dict):
    """Renderiza a barra de progresso de status de um conteúdo."""
    status = doc.get("status", {})
    cid    = doc["_id"]

    etapas = [
        ("slides_gerados",  "Slides",   "✅" if status.get("slides_gerados")  else "⬜"),
        ("imagens_geradas", "Imagens",  "✅" if status.get("imagens_geradas") else "⬜"),
        ("drive_enviado",   "Drive",    "✅" if status.get("drive_enviado")   else "⬜"),
        ("aprovado",        "Aprovado", "✅" if doc.get("aprovado")           else "⬜"),
        ("agendado",        "Agendado", "✅" if status.get("agendado")        else "⬜"),
        ("publicado",       "Publicado","✅" if status.get("publicado")       else "⬜"),
    ]

    concluidas = sum(1 for _, _, icone in etapas if icone == "✅")
    progresso  = concluidas / len(etapas)

    st.progress(progresso)

    cols = st.columns(len(etapas))
    for col, (campo, label, icone) in zip(cols, etapas):
        col.markdown(
            f"<div style='text-align:center;font-size:18px'>{icone}</div>"
            f"<div style='text-align:center;font-size:11px;color:gray'>{label}</div>",
            unsafe_allow_html=True,
        )

    # Botão de aprovação inline
    if not doc.get("aprovado"):
        if st.button("✔ Marcar como aprovado", key=f"aprovar_{cid}", type="secondary"):
            db.atualizar_conteudo(cid, {"aprovado": True})
            st.rerun()
    else:
        if st.button("↩ Remover aprovação", key=f"desaprovar_{cid}"):
            db.atualizar_conteudo(cid, {"aprovado": False})
            st.rerun()

    # Link do Drive se disponível
    drive_link = status.get("drive_link")
    if drive_link:
        st.caption(f"📁 [Abrir no Drive]({drive_link})")

    st.divider()


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

        ctx_existente = llm_brain.carregar_contexto_compilado(empresa_sel["id"])
        if not ctx_existente:
            st.warning("Contexto editorial não processado. Vá até a aba **Empresas** e clique em **Processar Contexto** antes de gerar.")

        # ── Sugestão de temas ─────────────────────────────────────────────────
        _key_sugestoes = f"sugestoes_{empresa_sel['id']}"

        _col_sug, _col_limpar = st.columns([3, 1])
        if _col_sug.button("💡 Sugerir 10 temas", key="btn_sugerir", width='stretch', disabled=not ctx_existente):
            with st.spinner("Buscando tendências e sugerindo temas..."):
                try:
                    sugestoes = llm_brain.sugerir_temas(
                        empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"],
                        publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                    st.session_state[_key_sugestoes] = sugestoes
                    st.session_state[f"sel_{_key_sugestoes}"] = []
                except Exception as e:
                    st.error(f"Erro ao sugerir temas: {e}")

        if _key_sugestoes in st.session_state and _col_limpar.button("✕ Limpar", key="btn_limpar_sug"):
            del st.session_state[_key_sugestoes]
            st.session_state.pop(f"sel_{_key_sugestoes}", None)

        temas_selecionados: list[str] = []
        if _key_sugestoes in st.session_state:
            st.caption("Selecione os temas que deseja gerar:")
            sugestoes_lista = st.session_state[_key_sugestoes]
            _sel_key = f"sel_{_key_sugestoes}"
            selecionados = st.session_state.get(_sel_key, [])
            for i, sugestao in enumerate(sugestoes_lista):
                checked = st.checkbox(sugestao, value=(sugestao in selecionados), key=f"ck_sug_{empresa_sel['id']}_{i}")
                if checked and sugestao not in selecionados:
                    selecionados.append(sugestao)
                elif not checked and sugestao in selecionados:
                    selecionados.remove(sugestao)
            st.session_state[_sel_key] = selecionados
            temas_selecionados = selecionados

        st.caption("Ou escreva um tema manualmente:")
        tema = st.text_input("Tema do conteúdo", placeholder="Ex: Integração de sistemas legados com e-commerce", label_visibility="collapsed")

        # Combina: temas selecionados + tema manual (se preenchido)
        _todos_temas = temas_selecionados + ([tema.strip()] if tema.strip() and tema.strip() not in temas_selecionados else [])

        st.caption("Conteúdos adicionais")
        ck1, ck2, ck3 = st.columns(3)
        opt_linkedin = ck1.checkbox("Post LinkedIn", value=True,  key="opt_linkedin")
        opt_video    = ck2.checkbox("Narração Vídeo", value=True, key="opt_video")
        opt_blog     = ck3.checkbox("Blog",           value=False, key="opt_blog")

        col_btn1, col_btn2 = st.columns(2)

        def _gerar_adicionais(tema_str: str, slides: list[dict]):
            """Gera e salva linkedin, vídeo e/ou blog conforme checkboxes."""
            if opt_linkedin:
                with st.spinner(f"Gerando Post LinkedIn — {tema_str[:40]}..."):
                    txt = llm_brain.gerar_linkedin(
                        tema=tema_str, empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"], publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""), slides=slides,
                    )
                    salvar_linkedin(txt, empresa_sel["id"], tema_str, empresa_sel)
            if opt_video:
                with st.spinner(f"Gerando Narração Vídeo — {tema_str[:40]}..."):
                    txt = llm_brain.gerar_narracao(
                        tema=tema_str, empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"], publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                    salvar_video(txt, empresa_sel["id"], tema_str, empresa_sel)
            if opt_blog:
                with st.spinner(f"Gerando Blog — {tema_str[:40]}..."):
                    txt = llm_brain.gerar_blog(
                        tema=tema_str, empresa=empresa_sel["nome"],
                        empresa_id=empresa_sel["id"], publico_alvo=empresa_sel["publico_alvo"],
                        url_site=empresa_sel.get("url_site", ""),
                    )
                    salvar_blog(txt, empresa_sel["id"], tema_str, empresa_sel)

        _sem_temas = not _todos_temas
        _label_btn1 = f"Gerar Conteúdo Padrão ({len(_todos_temas)})" if len(_todos_temas) > 1 else "Gerar Conteúdo Padrão"
        _label_btn2 = f"Gerar Carrossel Tweet ({len(_todos_temas)})" if len(_todos_temas) > 1 else "Gerar Carrossel Tweet"

        if col_btn1.button(_label_btn1, type="primary", disabled=_sem_temas, width='stretch'):
            ultimo_conteudo = None
            barra_lote = st.progress(0) if len(_todos_temas) > 1 else None
            for idx_t, tema_str in enumerate(_todos_temas):
                with st.spinner(f"Gerando Conteúdo Padrão — {tema_str[:50]}... ({idx_t+1}/{len(_todos_temas)})"):
                    try:
                        conteudo = llm_brain.gerar_conteudo(
                            tema=tema_str,
                            empresa=empresa_sel["nome"],
                            empresa_id=empresa_sel["id"],
                            publico_alvo=empresa_sel["publico_alvo"],
                            url_site=empresa_sel.get("url_site", ""),
                        )
                    except Exception as e:
                        st.error(f"Erro em '{tema_str[:40]}': {e}")
                        continue
                salvar_conteudo(
                    conteudo, empresa_sel["id"], tema_str, empresa_sel,
                    opt_linkedin=opt_linkedin, opt_video=opt_video,
                )
                if opt_blog:
                    try:
                        blog_txt = llm_brain.gerar_blog(
                            tema=tema_str, empresa=empresa_sel["nome"],
                            empresa_id=empresa_sel["id"], publico_alvo=empresa_sel["publico_alvo"],
                            url_site=empresa_sel.get("url_site", ""),
                        )
                        salvar_blog(blog_txt, empresa_sel["id"], tema_str, empresa_sel)
                    except Exception as e:
                        st.warning(f"Blog não gerado para '{tema_str[:40]}': {e}")
                ultimo_conteudo = conteudo
                if barra_lote:
                    barra_lote.progress((idx_t + 1) / len(_todos_temas))
            if barra_lote:
                barra_lote.empty()
            gerados_labels = ["carrossel"] + (["linkedin"] if opt_linkedin else []) + (["vídeo"] if opt_video else []) + (["blog"] if opt_blog else [])
            st.success(f"{len(_todos_temas)} tema(s) gerado(s): {', '.join(gerados_labels)}")
            st.session_state.pop("blog_atual", None)
            if ultimo_conteudo:
                st.session_state["conteudo_atual"] = ultimo_conteudo

        if col_btn2.button(_label_btn2, disabled=_sem_temas, width='stretch'):
            barra_lote_tw = st.progress(0) if len(_todos_temas) > 1 else None
            ultimo_tweet = None
            for idx_t, tema_str in enumerate(_todos_temas):
                with st.spinner(f"Gerando Carrossel Tweet — {tema_str[:50]}... ({idx_t+1}/{len(_todos_temas)})"):
                    try:
                        slides_tweet = llm_brain.gerar_carrossel_tweet(
                            tema=tema_str,
                            empresa=empresa_sel["nome"],
                            empresa_id=empresa_sel["id"],
                            publico_alvo=empresa_sel["publico_alvo"],
                            url_site=empresa_sel.get("url_site", ""),
                        )
                    except Exception as e:
                        st.error(f"Erro em '{tema_str[:40]}': {e}")
                        continue
                salvar_carrossel_tweet(slides_tweet, empresa_sel["id"], tema_str, empresa_sel)
                _gerar_adicionais(tema_str, slides_tweet.get("slides", []))
                if barra_lote_tw:
                    barra_lote_tw.progress((idx_t + 1) / len(_todos_temas))
                ultimo_tweet = slides_tweet
            if barra_lote_tw:
                barra_lote_tw.empty()
            st.success(f"{len(_todos_temas)} Carrossel(is) Tweet gerado(s).")
            if _todos_temas:
                st.session_state["tweet_slides_atual"] = ultimo_tweet

        _label_btn3 = f"Gerar Carrossel Misto DD ({len(_todos_temas)})" if len(_todos_temas) > 1 else "Gerar Carrossel Misto DD"
        if st.button(_label_btn3, disabled=_sem_temas, width='stretch'):
            barra_lote_mdd = st.progress(0) if len(_todos_temas) > 1 else None
            ultimo_mdd = None
            for idx_t, tema_str in enumerate(_todos_temas):
                with st.spinner(f"Gerando Carrossel Misto DD — {tema_str[:50]}... ({idx_t+1}/{len(_todos_temas)})"):
                    try:
                        slides_mdd = llm_brain.gerar_carrossel_misto_dd(
                            tema=tema_str,
                            empresa=empresa_sel["nome"],
                            empresa_id=empresa_sel["id"],
                            publico_alvo=empresa_sel["publico_alvo"],
                            url_site=empresa_sel.get("url_site", ""),
                        )
                    except Exception as e:
                        st.error(f"Erro em '{tema_str[:40]}': {e}")
                        continue
                salvar_carrossel_misto_dd(slides_mdd, empresa_sel["id"], tema_str, empresa_sel)
                _gerar_adicionais(tema_str, slides_mdd.get("slides", []))
                if barra_lote_mdd:
                    barra_lote_mdd.progress((idx_t + 1) / len(_todos_temas))
                ultimo_mdd = slides_mdd
            if barra_lote_mdd:
                barra_lote_mdd.empty()
            st.success(f"{len(_todos_temas)} Carrossel(is) Misto DD gerado(s).")
            if ultimo_mdd:
                st.session_state["misto_dd_slides_atual"] = ultimo_mdd

        conteudo = st.session_state.get("conteudo_atual")
        if conteudo:
            st.divider()

            sub_c, sub_li, sub_vid, sub_blog = st.tabs(
                ["Conteúdo Padrão", "Post LinkedIn", "Narração Vídeo", "Blog"]
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
                        salvar_blog(blog_texto, empresa_sel["id"], conteudo["tema"], empresa_sel)
                        st.session_state["blog_atual"] = blog_texto
                        st.success("Blog salvo.")
                        st.rerun()

        tweet_slides = st.session_state.get("tweet_slides_atual")
        if tweet_slides:
            st.divider()
            st.subheader("Carrossel Tweet")
            for slide in tweet_slides.get("slides", []):
                with st.expander(f"Slide {slide['slide']} — {slide['titulo']}"):
                    st.write(slide["texto"])

        misto_dd_slides = st.session_state.get("misto_dd_slides_atual")
        if misto_dd_slides:
            st.divider()
            st.subheader("Carrossel Misto DD")
            for slide in misto_dd_slides.get("slides", []):
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
    "carrossel":          "Conteúdo Padrão",
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
            contagens = db.contar_conteudos(emp["id"])
            total = sum(contagens.values())
            label = f"{emp['nome']}  —  {total} conteúdo(s)" if total else emp["nome"]

            with st.expander(label, expanded=bool(total) and len(empresas) == 1):
                if not total:
                    st.caption("Nenhum conteúdo gerado ainda.")
                    continue

                # ── Google Doc — Posts LinkedIn + Narração ────────────
                _gdoc_key = f"gdoc_url_{emp['id']}"
                _col_gdoc, _col_gdoc_link = st.columns([2, 3])
                if _col_gdoc.button("📄 Gerar Google Doc (LinkedIn + Vídeo)", key=f"gdoc_{emp['id']}", width='stretch'):
                    with st.spinner("Criando Google Doc..."):
                        try:
                            folder_id_gdoc = emp.get("drive_folder_id") or ""
                            _doc_id, _doc_url = docs.criar_doc_posts(
                                empresa_id=emp["id"],
                                empresa_nome=emp["nome"],
                                folder_id=folder_id_gdoc or None,
                            )
                            st.session_state[_gdoc_key] = _doc_url
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao criar doc: {e}")
                if st.session_state.get(_gdoc_key):
                    _col_gdoc_link.markdown(f"📝 [Abrir documento]({st.session_state[_gdoc_key]})")

                # ── Gerar conteúdos escritos de carrosseis existentes ─────────
                _key_esc_exp  = f"escritos_exp_{emp['id']}"
                _key_esc_sel  = f"escritos_sel_{emp['id']}"

                if st.button("✍️ Gerar conteúdos escritos", key=f"btn_escritos_{emp['id']}", width='stretch'):
                    st.session_state[_key_esc_exp] = not st.session_state.get(_key_esc_exp, False)
                    st.session_state[_key_esc_sel] = []

                if st.session_state.get(_key_esc_exp):
                    _docs_base = []
                    for _t in ["carrossel", "carrossel_tweet", "carrossel_misto_dd"]:
                        for _d in listar_conteudos(emp["id"], _t):
                            _docs_base.append(_d)

                    if not _docs_base:
                        st.caption("Nenhum carrossel disponível como base.")
                    else:
                        st.caption("Selecione os conteúdos que deseja usar como base:")
                        _sel_ids = st.session_state.get(_key_esc_sel, [])
                        for _doc in _docs_base:
                            _cid  = str(_doc["_id"])
                            _data = _doc["criado_em"].strftime("%d/%m/%Y") if _doc.get("criado_em") else "—"
                            _tlabel = TIPOS.get(_doc.get("tipo", ""), "")
                            _checked = st.checkbox(
                                f"{_doc['tema']}  ·  {_tlabel}  ·  {_data}",
                                value=_cid in _sel_ids,
                                key=f"ck_esc_{emp['id']}_{_cid}",
                            )
                            if _checked and _cid not in _sel_ids:
                                _sel_ids.append(_cid)
                            elif not _checked and _cid in _sel_ids:
                                _sel_ids.remove(_cid)
                        st.session_state[_key_esc_sel] = _sel_ids

                        _esc_c1, _esc_c2, _esc_c3 = st.columns([1, 1, 2])
                        _opt_esc_li  = _esc_c1.checkbox("Post LinkedIn",   value=True,  key=f"opt_esc_li_{emp['id']}")
                        _opt_esc_vid = _esc_c2.checkbox("Narração Vídeo",  value=True,  key=f"opt_esc_vid_{emp['id']}")

                        if st.button(
                            f"Gerar para {len(_sel_ids)} selecionado(s)",
                            key=f"btn_esc_gerar_{emp['id']}",
                            disabled=not _sel_ids or (not _opt_esc_li and not _opt_esc_vid),
                            width='stretch',
                        ):
                            _docs_map = {str(_d["_id"]): _d for _d in _docs_base}
                            for _cid in _sel_ids:
                                _doc = _docs_map.get(_cid)
                                if not _doc:
                                    continue
                                _tema_doc = _doc["tema"]
                                if _opt_esc_li:
                                    with st.spinner(f"Gerando LinkedIn — {_tema_doc[:40]}..."):
                                        try:
                                            _txt = llm_brain.gerar_linkedin(
                                                tema=_tema_doc,
                                                empresa=emp["nome"],
                                                empresa_id=emp["id"],
                                                publico_alvo=emp["publico_alvo"],
                                                url_site=emp.get("url_site", ""),
                                            )
                                            salvar_linkedin(_txt, emp["id"], _tema_doc, emp)
                                        except Exception as e:
                                            st.error(f"Erro LinkedIn '{_tema_doc[:30]}': {e}")
                                if _opt_esc_vid:
                                    with st.spinner(f"Gerando Narração — {_tema_doc[:40]}..."):
                                        try:
                                            _txt = llm_brain.gerar_narracao(
                                                tema=_tema_doc,
                                                empresa=emp["nome"],
                                                empresa_id=emp["id"],
                                                publico_alvo=emp["publico_alvo"],
                                                url_site=emp.get("url_site", ""),
                                            )
                                            salvar_video(_txt, emp["id"], _tema_doc, emp)
                                        except Exception as e:
                                            st.error(f"Erro Narração '{_tema_doc[:30]}': {e}")
                            st.success("Conteúdos gerados com sucesso!")
                            st.session_state[_key_esc_exp] = False
                            st.rerun()

                def _tab_label(tipo: str) -> str:
                    n = contagens.get(tipo, 0)
                    return f"{TIPOS[tipo]} ({n})" if n else TIPOS[tipo]

                sub_carrossel, sub_tweet, sub_misto_dd, sub_linkedin, sub_video, sub_blog = st.tabs([
                    _tab_label("carrossel"), _tab_label("carrossel_tweet"), _tab_label("carrossel_misto_dd"),
                    _tab_label("linkedin"),  _tab_label("video"),           _tab_label("blog"),
                ])

                def _listar_md(tipo: str, campo: str, altura: int, prefixo: str, fn_regenerar=None):
                    docs = listar_conteudos(emp["id"], tipo)
                    if not docs:
                        st.caption("Nenhum conteúdo gerado ainda.")
                        return
                    for doc in docs:
                        cid  = doc["_id"]
                        data = doc["criado_em"].strftime("%d/%m/%Y %H:%M") if doc.get("criado_em") else "—"
                        corpo = doc.get(campo, "")
                        with st.expander(f"{doc['tema']}  ·  {data}"):
                            btn_cols = st.columns([1, 1, 5]) if fn_regenerar else st.columns([1, 6])
                            if btn_cols[0].button("Excluir", key=f"del_{tipo}_{emp['id']}_{cid}", type="secondary"):
                                excluir_conteudo(cid)
                                st.success("Excluído.")
                                st.rerun()
                            if fn_regenerar and btn_cols[1].button("↺ Regenerar", key=f"regen_{tipo}_{cid}"):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novo = fn_regenerar(doc["tema"])
                                        db.atualizar_conteudo(cid, {campo: novo})
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
                            st.text_area(" ", corpo, height=altura, key=f"{prefixo}_{cid}", label_visibility="collapsed")

                with sub_carrossel:
                    docs_c = listar_conteudos(emp["id"], "carrossel")
                    if not docs_c:
                        st.caption("Nenhum carrossel gerado.")
                    for doc in docs_c:
                        cid  = doc["_id"]
                        stem = doc.get("stem", cid)
                        data = doc["criado_em"].strftime("%d/%m/%Y %H:%M") if doc.get("criado_em") else "—"
                        if doc.get("status", {}).get("drive_enviado"):
                            _mid = f"dm_{cid}"
                            st.markdown(
                                f'<div id="{_mid}"></div><style>div[data-testid="element-container"]:has(#{_mid}) + div[data-testid="element-container"] div[data-testid="stExpander"]{{background-color:rgba(34,197,94,0.07)!important;border-radius:8px;}}</style>',
                                unsafe_allow_html=True,
                            )
                        with st.expander(f"{doc['tema']}  ·  {data}"):
                            _checklist_status(doc)
                            col_del, col_regen_texto, _esp = st.columns([1, 2, 3])
                            if col_del.button("Excluir", key=f"del_c_{emp['id']}_{cid}", type="secondary"):
                                excluir_conteudo(cid)
                                st.success("Excluído.")
                                st.rerun()
                            if col_regen_texto.button("↺ Regenerar texto", key=f"regen_c_{cid}", width='stretch'):
                                with st.spinner("Regenerando carrossel..."):
                                    try:
                                        novos = llm_brain.gerar_slides_carrossel(
                                            tema=doc["tema"],
                                            empresa=doc.get("empresa_nome", emp["nome"]),
                                            empresa_id=emp["id"],
                                            publico_alvo=doc.get("publico_alvo", emp["publico_alvo"]),
                                            url_site=emp.get("url_site", ""),
                                        )
                                        db.atualizar_conteudo(cid, {"slides": novos})
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            imagens = gerador_imagens.listar_imagens(emp["id"], stem)
                            iv = {**emp.get("identidade_visual", {}), "estilo_imagem": emp.get("estilo_imagem", ""), "url_site": emp.get("url_site", "")}

                            _logo_idx = 1
                            if gerador_imagens.logo_empresa(emp["id"], 2):
                                _logos_opts = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                _logo_sel = st.radio("Logo", _logos_opts, horizontal=True, key=f"logo_c_{cid}", label_visibility="collapsed")
                                _logo_idx = 2 if _logo_sel == _logos_opts[1] else 1

                            _leg = doc.get("legenda", "")
                            _col_leg, _col_gerar_leg = st.columns([4, 1])
                            with _col_leg:
                                _nova_leg = st.text_area("Legenda", value=_leg, key=f"leg_c_{cid}", height=100, label_visibility="collapsed", placeholder="Legenda para o post...")
                            with _col_gerar_leg:
                                if st.button("✨ Gerar legenda", key=f"gerar_leg_c_{cid}", width='stretch'):
                                    with st.spinner("Gerando..."):
                                        try:
                                            _nova_leg = llm_brain.gerar_legenda(doc["tema"], doc.get("empresa_nome", emp["nome"]), emp["id"], doc.get("publico_alvo", emp["publico_alvo"]), doc.get("slides", []))
                                            db.atualizar_conteudo(cid, {"legenda": _nova_leg})
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if _nova_leg != _leg:
                                    if st.button("💾 Salvar legenda", key=f"sv_leg_c_{cid}", width='stretch'):
                                        db.atualizar_conteudo(cid, {"legenda": _nova_leg})
                                        st.success("Legenda salva.")

                            if imagens:
                                col_cap, col_baixar, col_drive, col_regen = st.columns([2, 1, 1, 1])
                                col_cap.caption(f"{len(imagens)} imagem(ns) gerada(s)")
                                regenerar_tudo = col_regen.button("↺ Regenerar tudo", key=f"regen_img_c_{cid}", width='stretch')
                                folder_id = emp.get("drive_folder_id", "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                                if col_drive.button("📤 Drive", key=f"drive_c_{cid}", width='stretch', disabled=not folder_id):
                                    with st.spinner("Enviando..."):
                                        try:
                                            resultados, nome_pasta, folder_link = drive.enviar_carrossel_drive(imagens, folder_id)
                                            db.marcar_drive_enviado(cid, folder_link)
                                            st.success(f"{len(resultados)} imagens enviadas para **{nome_pasta}**!")
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if not folder_id:
                                    col_drive.caption("Configure o ID da pasta na aba Empresas")
                                zip_buf = io.BytesIO()
                                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, ip in enumerate(imagens):
                                        zf.write(ip, arcname=f"{idx+1}.png")
                                zip_buf.seek(0)
                                col_baixar.download_button("↓ Baixar tudo", data=zip_buf, file_name=f"{stem}.zip", mime="application/zip", key=f"dl_zip_c_{cid}", width='stretch')
                                cols = st.columns(3)
                                for idx, img_path in enumerate(imagens):
                                    slide_n = int(img_path.stem.split("_")[-1])
                                    with cols[idx % 3]:
                                        st.image(str(img_path), width='stretch')
                                        col_dl, col_rs = st.columns(2)
                                        with open(img_path, "rb") as img_f:
                                            col_dl.download_button("↓ Baixar", data=img_f.read(), file_name=img_path.name, mime="image/png", key=f"dl_c_{cid}_{idx}", width='stretch')
                                        _variante_sel = None
                                        if slide_n in _OPCOES_ESTILO_SLIDE:
                                            _nomes = [o[0] for o in _OPCOES_ESTILO_SLIDE[slide_n]]
                                            _vals  = {o[0]: o[1] for o in _OPCOES_ESTILO_SLIDE[slide_n]}
                                            _variante_sel = _vals[st.selectbox("Estilo", _nomes, key=f"est_c_{cid}_{slide_n}", label_visibility="collapsed")]
                                        if col_rs.button("↺ Slide", key=f"rs_c_{cid}_{idx}", width='stretch'):
                                            slide_data = next((s for s in doc.get("slides", []) if s.get("slide") == slide_n), None)
                                            if slide_data:
                                                with st.spinner(f"Regenerando slide {slide_n}..."):
                                                    try:
                                                        gerador_imagens.gerar_imagem_slide(slide=slide_data, empresa_id=emp["id"], stem=stem, identidade_visual=iv, is_ultimo=(slide_n == len(doc.get("slides", []))), variante_override=_variante_sel, logo_index=_logo_idx)
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regenerar_tudo = False

                            if not imagens or regenerar_tudo:
                                if regenerar_tudo or st.button("Gerar Imagens", key=f"gen_img_c_{cid}", type="primary"):
                                    barra = st.progress(0, text="Iniciando...")
                                    status_el = st.empty()
                                    def _prog(n, total): barra.progress(n/total, text=f"Slide {n}/{total}..."); status_el.caption(f"Slide {n}/{total}")
                                    try:
                                        gerador_imagens.gerar_imagens_carrossel(slides=doc.get("slides", []), empresa_id=emp["id"], stem=stem, identidade_visual=iv, callback=_prog, logo_index=_logo_idx)
                                        db.marcar_imagens_geradas(cid)
                                        barra.empty(); status_el.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            slides_editados = list(doc.get("slides", []))
                            for i, slide in enumerate(slides_editados):
                                _sk = f"c_{cid}_{slide['slide']}"
                                st.caption(f"Slide {slide['slide']}")
                                slides_editados[i]["titulo"] = st.text_input("Título", value=slide["titulo"], key=f"tit_{_sk}", label_visibility="collapsed", placeholder="Título")
                                slides_editados[i]["texto"]  = st.text_area("Texto",  value=slide["texto"],  key=f"txt_{_sk}", label_visibility="collapsed", placeholder="Texto", height=100)
                                if slide.get("prompt_imagem"):
                                    st.caption(f"🖼️ {slide['prompt_imagem']}")
                                if st.button("💾 Salvar slide", key=f"sv_{_sk}", width='content'):
                                    db.atualizar_conteudo(cid, {"slides": slides_editados})
                                    st.success(f"Slide {slide['slide']} salvo.")
                                    st.rerun()
                                st.divider()

                with sub_tweet:
                    docs_tw = listar_conteudos(emp["id"], "carrossel_tweet")
                    if not docs_tw:
                        st.caption("Nenhum Carrossel Tweet gerado.")
                    for doc_tw in docs_tw:
                        cid_tw  = doc_tw["_id"]
                        stem_tw = doc_tw.get("stem", cid_tw)
                        data_tw = doc_tw["criado_em"].strftime("%d/%m/%Y %H:%M") if doc_tw.get("criado_em") else "—"
                        if doc_tw.get("status", {}).get("drive_enviado"):
                            _mid_tw = f"dm_{cid_tw}"
                            st.markdown(
                                f'<div id="{_mid_tw}"></div><style>div[data-testid="element-container"]:has(#{_mid_tw}) + div[data-testid="element-container"] div[data-testid="stExpander"]{{background-color:rgba(34,197,94,0.07)!important;border-radius:8px;}}</style>',
                                unsafe_allow_html=True,
                            )
                        with st.expander(f"{doc_tw['tema']}  ·  {data_tw}"):
                            _checklist_status(doc_tw)
                            col_del_tw, col_regen_tw, _esp_tw = st.columns([1, 2, 3])
                            if col_del_tw.button("Excluir", key=f"del_tw_{emp['id']}_{cid_tw}", type="secondary"):
                                excluir_conteudo(cid_tw)
                                st.success("Excluído.")
                                st.rerun()
                            if col_regen_tw.button("↺ Regenerar texto", key=f"regen_tw_{cid_tw}", width='stretch'):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novos_tw = llm_brain.gerar_carrossel_tweet(tema=doc_tw["tema"], empresa=emp["nome"], empresa_id=emp["id"], publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""))
                                        db.atualizar_conteudo(cid_tw, {"slides": novos_tw["slides"], "legenda": novos_tw.get("legenda", "")})
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            imagens_tw = gerador_imagens.listar_imagens_tweet(emp["id"], stem_tw)
                            iv_tw = {**emp.get("identidade_visual", {}), "estilo_imagem": emp.get("estilo_imagem", "")}
                            _prim_entry = (emp.get("identidade_visual", {}).get("primarias") or [{}])[0]
                            _cor_prim_emp = _prim_entry.get("hex", "#1d9bf0") if isinstance(_prim_entry, dict) else str(_prim_entry)
                            _logo_idx_tw = 2
                            _cor_circ_tw = _cor_prim_emp
                            _tw_col1, _tw_col2 = st.columns([2, 1])
                            with _tw_col1:
                                if gerador_imagens.logo_empresa(emp["id"], 2):
                                    _logos_opts_tw = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                    _logo_sel_tw = st.radio("Logo", _logos_opts_tw, index=1, horizontal=True, key=f"logo_tw_{cid_tw}", label_visibility="collapsed")
                                    _logo_idx_tw = 2 if _logo_sel_tw == _logos_opts_tw[1] else 1
                            with _tw_col2:
                                _cor_circ_tw = st.color_picker("Cor do círculo", value=_cor_prim_emp, key=f"cor_tw_{cid_tw}")

                            _leg_tw = doc_tw.get("legenda", "")
                            _col_leg_tw, _col_gerar_leg_tw = st.columns([4, 1])
                            with _col_leg_tw:
                                _nova_leg_tw = st.text_area("Legenda", value=_leg_tw, key=f"leg_tw_{cid_tw}", height=100, label_visibility="collapsed", placeholder="Legenda para o post...")
                            with _col_gerar_leg_tw:
                                if st.button("✨ Gerar legenda", key=f"gerar_leg_tw_{cid_tw}", width='stretch'):
                                    with st.spinner("Gerando..."):
                                        try:
                                            _nova_leg_tw = llm_brain.gerar_legenda(doc_tw["tema"], emp["nome"], emp["id"], emp["publico_alvo"], doc_tw.get("slides", []))
                                            db.atualizar_conteudo(cid_tw, {"legenda": _nova_leg_tw})
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if _nova_leg_tw != _leg_tw:
                                    if st.button("💾 Salvar legenda", key=f"sv_leg_tw_{cid_tw}", width='stretch'):
                                        db.atualizar_conteudo(cid_tw, {"legenda": _nova_leg_tw})
                                        st.success("Legenda salva.")

                            if imagens_tw:
                                col_cap_tw, col_baixar_tw, col_drive_tw, col_regen_img_tw = st.columns([2, 1, 1, 1])
                                col_cap_tw.caption(f"{len(imagens_tw)} imagem(ns) gerada(s)")
                                regen_tw_tudo = col_regen_img_tw.button("↺ Regenerar tudo", key=f"regen_tw_img_{cid_tw}", width='stretch')
                                folder_id_tw = emp.get("drive_folder_id", "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                                if col_drive_tw.button("📤 Drive", key=f"drive_tw_{cid_tw}", width='stretch', disabled=not folder_id_tw):
                                    with st.spinner("Enviando..."):
                                        try:
                                            resultados, nome_pasta, folder_link = drive.enviar_carrossel_drive(imagens_tw, folder_id_tw)
                                            db.marcar_drive_enviado(cid_tw, folder_link)
                                            st.success(f"{len(resultados)} imagens enviadas para **{nome_pasta}**!")
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if not folder_id_tw:
                                    col_drive_tw.caption("Configure o ID da pasta na aba Empresas")
                                zip_buf_tw = io.BytesIO()
                                with zipfile.ZipFile(zip_buf_tw, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, ip in enumerate(imagens_tw):
                                        zf.write(ip, arcname=f"{idx+1}.png")
                                zip_buf_tw.seek(0)
                                col_baixar_tw.download_button("↓ Baixar tudo", data=zip_buf_tw, file_name=f"{stem_tw}_tweet.zip", mime="application/zip", key=f"dl_zip_tw_{cid_tw}", width='stretch')
                                cols_tw = st.columns(3)
                                for idx, img_path_tw in enumerate(imagens_tw):
                                    slide_n_tw = int(img_path_tw.stem.split("_")[-1])
                                    with cols_tw[idx % 3]:
                                        st.image(str(img_path_tw), width='stretch')
                                        col_dl_tw, col_rs_tw = st.columns(2)
                                        with open(img_path_tw, "rb") as img_f_tw:
                                            col_dl_tw.download_button("↓ Baixar", data=img_f_tw.read(), file_name=img_path_tw.name, mime="image/png", key=f"dl_tw_{cid_tw}_{idx}", width='stretch')
                                        if col_rs_tw.button("↺ Slide", key=f"rs_tw_{cid_tw}_{idx}", width='stretch'):
                                            sd_tw = next((s for s in doc_tw.get("slides", []) if s.get("slide") == slide_n_tw), None)
                                            if sd_tw:
                                                with st.spinner(f"Regenerando slide {slide_n_tw}..."):
                                                    try:
                                                        gerador_imagens.gerar_imagem_slide_tweet(slide=sd_tw, empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_tw, identidade_visual=iv_tw, logo_index=_logo_idx_tw, cor_circulo_hex=_cor_circ_tw)
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regen_tw_tudo = False

                            if not imagens_tw or regen_tw_tudo:
                                if regen_tw_tudo or st.button("Gerar Imagens", key=f"gen_img_tw_{cid_tw}", type="primary"):
                                    barra_tw = st.progress(0, text="Iniciando...")
                                    status_tw = st.empty()
                                    def _prog_tw(n, total): barra_tw.progress(n/total, text=f"Slide {n}/{total}..."); status_tw.caption(f"Slide {n}/{total}")
                                    try:
                                        gerador_imagens.gerar_imagens_carrossel_tweet(slides=doc_tw.get("slides", []), empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_tw, identidade_visual=iv_tw, logo_index=_logo_idx_tw, cor_circulo_hex=_cor_circ_tw, callback=_prog_tw)
                                        db.marcar_imagens_geradas(cid_tw)
                                        barra_tw.empty(); status_tw.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            slides_tw_ed = list(doc_tw.get("slides", []))
                            for i, slide in enumerate(slides_tw_ed):
                                _sk = f"tw_{cid_tw}_{slide['slide']}"
                                st.caption(f"Slide {slide['slide']}")
                                slides_tw_ed[i]["titulo"] = st.text_input("Título", value=slide["titulo"], key=f"tit_{_sk}", label_visibility="collapsed", placeholder="Título")
                                slides_tw_ed[i]["texto"]  = st.text_area("Texto",  value=slide["texto"],  key=f"txt_{_sk}", label_visibility="collapsed", placeholder="Texto", height=100)
                                if slide.get("prompt_imagem") is not None:
                                    slides_tw_ed[i]["prompt_imagem"] = st.text_area("Prompt", value=slide["prompt_imagem"], key=f"prm_{_sk}", label_visibility="collapsed", placeholder="Prompt de imagem", height=68)
                                _cs_tw, _csr_tw = st.columns(2)
                                if _cs_tw.button("💾 Salvar", key=f"sv_{_sk}", width='stretch'):
                                    db.atualizar_conteudo(cid_tw, {"slides": slides_tw_ed})
                                    st.success(f"Slide {slide['slide']} salvo.")
                                    st.rerun()
                                if _csr_tw.button("💾 Salvar e Regenerar", key=f"svr_{_sk}", width='stretch'):
                                    db.atualizar_conteudo(cid_tw, {"slides": slides_tw_ed})
                                    with st.spinner(f"Regenerando slide {slide['slide']}..."):
                                        try:
                                            gerador_imagens.gerar_imagem_slide_tweet(slide=slides_tw_ed[i], empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_tw, identidade_visual=iv_tw, logo_index=_logo_idx_tw, cor_circulo_hex=_cor_circ_tw)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro: {e}")

                with sub_misto_dd:
                    docs_mdd = listar_conteudos(emp["id"], "carrossel_misto_dd")
                    if not docs_mdd:
                        st.caption("Nenhum Carrossel Misto DD gerado.")
                    for doc_mdd in docs_mdd:
                        cid_mdd  = doc_mdd["_id"]
                        stem_mdd = doc_mdd.get("stem", cid_mdd)
                        data_mdd = doc_mdd["criado_em"].strftime("%d/%m/%Y %H:%M") if doc_mdd.get("criado_em") else "—"
                        if doc_mdd.get("status", {}).get("drive_enviado"):
                            _mid_mdd = f"dm_{cid_mdd}"
                            st.markdown(
                                f'<div id="{_mid_mdd}"></div><style>div[data-testid="element-container"]:has(#{_mid_mdd}) + div[data-testid="element-container"] div[data-testid="stExpander"]{{background-color:rgba(34,197,94,0.07)!important;border-radius:8px;}}</style>',
                                unsafe_allow_html=True,
                            )
                        with st.expander(f"{doc_mdd['tema']}  ·  {data_mdd}"):
                            _checklist_status(doc_mdd)
                            col_del_mdd, col_regen_mdd, _esp_mdd = st.columns([1, 2, 3])
                            if col_del_mdd.button("Excluir", key=f"del_mdd_{emp['id']}_{cid_mdd}", type="secondary"):
                                excluir_conteudo(cid_mdd)
                                st.success("Excluído.")
                                st.rerun()
                            if col_regen_mdd.button("↺ Regenerar texto", key=f"regen_mdd_{cid_mdd}", width='stretch'):
                                with st.spinner("Regenerando..."):
                                    try:
                                        novos_mdd = llm_brain.gerar_carrossel_misto_dd(tema=doc_mdd["tema"], empresa=emp["nome"], empresa_id=emp["id"], publico_alvo=emp["publico_alvo"], url_site=emp.get("url_site", ""))
                                        db.atualizar_conteudo(cid_mdd, {"slides": novos_mdd["slides"], "legenda": novos_mdd.get("legenda", "")})
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            imagens_mdd = gerador_imagens.listar_imagens_misto_dd(emp["id"], stem_mdd)
                            iv_mdd = {**emp.get("identidade_visual", {}), "estilo_imagem": emp.get("estilo_imagem", ""), "url_site": emp.get("url_site", "")}
                            _logo_idx_mdd = 1
                            if gerador_imagens.logo_empresa(emp["id"], 2):
                                _logos_opts_mdd = ["Logo 1 (principal)", "Logo 2 (alternativa)"]
                                _logo_sel_mdd = st.radio("Logo", _logos_opts_mdd, horizontal=True, key=f"logo_mdd_{cid_mdd}", label_visibility="collapsed")
                                _logo_idx_mdd = 2 if _logo_sel_mdd == _logos_opts_mdd[1] else 1

                            _leg_mdd = doc_mdd.get("legenda", "")
                            _col_leg_mdd, _col_gerar_leg_mdd = st.columns([4, 1])
                            with _col_leg_mdd:
                                _nova_leg_mdd = st.text_area("Legenda", value=_leg_mdd, key=f"leg_mdd_{cid_mdd}", height=100, label_visibility="collapsed", placeholder="Legenda para o post...")
                            with _col_gerar_leg_mdd:
                                if st.button("✨ Gerar legenda", key=f"gerar_leg_mdd_{cid_mdd}", width='stretch'):
                                    with st.spinner("Gerando..."):
                                        try:
                                            _nova_leg_mdd = llm_brain.gerar_legenda(doc_mdd["tema"], emp["nome"], emp["id"], emp["publico_alvo"], doc_mdd.get("slides", []))
                                            db.atualizar_conteudo(cid_mdd, {"legenda": _nova_leg_mdd})
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if _nova_leg_mdd != _leg_mdd:
                                    if st.button("💾 Salvar legenda", key=f"sv_leg_mdd_{cid_mdd}", width='stretch'):
                                        db.atualizar_conteudo(cid_mdd, {"legenda": _nova_leg_mdd})
                                        st.success("Legenda salva.")

                            if imagens_mdd:
                                col_cap_mdd, col_baixar_mdd, col_drive_mdd, col_regen_mdd_img = st.columns([2, 1, 1, 1])
                                col_cap_mdd.caption(f"{len(imagens_mdd)} imagem(ns) gerada(s)")
                                regen_mdd_tudo = col_regen_mdd_img.button("↺ Regenerar tudo", key=f"regen_mdd_img_{cid_mdd}", width='stretch')
                                folder_id_mdd = emp.get("drive_folder_id", "") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
                                if col_drive_mdd.button("📤 Drive", key=f"drive_mdd_{cid_mdd}", width='stretch', disabled=not folder_id_mdd):
                                    with st.spinner("Enviando..."):
                                        try:
                                            resultados, nome_pasta, folder_link = drive.enviar_carrossel_drive(imagens_mdd, folder_id_mdd)
                                            db.marcar_drive_enviado(cid_mdd, folder_link)
                                            st.success(f"{len(resultados)} imagens enviadas para **{nome_pasta}**!")
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                if not folder_id_mdd:
                                    col_drive_mdd.caption("Configure o ID da pasta na aba Empresas")
                                zip_buf_mdd = io.BytesIO()
                                with zipfile.ZipFile(zip_buf_mdd, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for idx, ip in enumerate(imagens_mdd):
                                        zf.write(ip, arcname=f"{idx+1}.png")
                                zip_buf_mdd.seek(0)
                                col_baixar_mdd.download_button("↓ Baixar tudo", data=zip_buf_mdd, file_name=f"{stem_mdd}_misto_dd.zip", mime="application/zip", key=f"dl_zip_mdd_{cid_mdd}", width='stretch')
                                cols_mdd = st.columns(3)
                                for idx, img_path_mdd in enumerate(imagens_mdd):
                                    slide_n_mdd = int(img_path_mdd.stem.split("_")[-1])
                                    with cols_mdd[idx % 3]:
                                        st.image(str(img_path_mdd), width='stretch')
                                        fundo_ok = st.checkbox("Fundo ok", key=f"fundo_mdd_{cid_mdd}_{idx}")
                                        col_dl_mdd, col_rs_mdd = st.columns(2)
                                        with open(img_path_mdd, "rb") as img_f_mdd:
                                            col_dl_mdd.download_button("↓ Baixar", data=img_f_mdd.read(), file_name=img_path_mdd.name, mime="image/png", key=f"dl_mdd_{cid_mdd}_{idx}", width='stretch')
                                        if col_rs_mdd.button("↺ Slide", key=f"rs_mdd_{cid_mdd}_{idx}", width='stretch'):
                                            sd_mdd = next((s for s in doc_mdd.get("slides", []) if s.get("slide") == slide_n_mdd), None)
                                            if sd_mdd:
                                                with st.spinner(f"Regenerando slide {slide_n_mdd}..."):
                                                    try:
                                                        gerador_imagens.gerar_imagem_slide_misto_dd(slide=sd_mdd, empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_mdd, identidade_visual=iv_mdd, logo_index=_logo_idx_mdd, fundo_fixo=fundo_ok)
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Erro: {e}")
                            else:
                                regen_mdd_tudo = False

                            if not imagens_mdd or regen_mdd_tudo:
                                if regen_mdd_tudo or st.button("Gerar Imagens", key=f"gen_img_mdd_{cid_mdd}", type="primary"):
                                    barra_mdd = st.progress(0, text="Iniciando...")
                                    status_mdd = st.empty()
                                    def _prog_mdd(n, total): barra_mdd.progress(n/total, text=f"Slide {n}/{total}..."); status_mdd.caption(f"Slide {n}/{total}")
                                    try:
                                        gerador_imagens.gerar_imagens_carrossel_misto_dd(slides=doc_mdd.get("slides", []), empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_mdd, identidade_visual=iv_mdd, logo_index=_logo_idx_mdd, callback=_prog_mdd)
                                        db.marcar_imagens_geradas(cid_mdd)
                                        barra_mdd.empty(); status_mdd.empty()
                                        st.success("Imagens geradas!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")

                            st.divider()
                            st.caption("Slides (texto)")
                            slides_mdd_ed = list(doc_mdd.get("slides", []))
                            for i, slide in enumerate(slides_mdd_ed):
                                _sk = f"mdd_{cid_mdd}_{slide['slide']}"
                                st.caption(f"Slide {slide['slide']}")
                                slides_mdd_ed[i]["titulo"] = st.text_input("Título", value=slide["titulo"], key=f"tit_{_sk}", label_visibility="collapsed", placeholder="Título")
                                slides_mdd_ed[i]["texto"]  = st.text_area("Texto",  value=slide["texto"],  key=f"txt_{_sk}", label_visibility="collapsed", placeholder="Texto", height=100)
                                if slide.get("prompt_imagem") is not None:
                                    slides_mdd_ed[i]["prompt_imagem"] = st.text_area("Prompt", value=slide["prompt_imagem"], key=f"prm_{_sk}", label_visibility="collapsed", placeholder="Prompt de imagem", height=68)
                                _cs, _csr = st.columns(2)
                                if _cs.button("💾 Salvar", key=f"sv_{_sk}", width='stretch'):
                                    db.atualizar_conteudo(cid_mdd, {"slides": slides_mdd_ed})
                                    st.success(f"Slide {slide['slide']} salvo.")
                                    st.rerun()
                                if _csr.button("💾 Salvar e Regenerar", key=f"svr_{_sk}", width='stretch'):
                                    db.atualizar_conteudo(cid_mdd, {"slides": slides_mdd_ed})
                                    with st.spinner(f"Regenerando slide {slide['slide']}..."):
                                        try:
                                            gerador_imagens.gerar_imagem_slide_misto_dd(slide=slides_mdd_ed[i], empresa_id=emp["id"], empresa_nome=emp["nome"], stem=stem_mdd, identidade_visual=iv_mdd, logo_index=_logo_idx_mdd)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro: {e}")
                                st.divider()

                with sub_linkedin:
                    _listar_md("linkedin", "post_linkedin", 300, "li",
                        fn_regenerar=lambda tema: llm_brain.gerar_linkedin(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))

                with sub_video:
                    _listar_md("video", "narracao_video", 200, "vid",
                        fn_regenerar=lambda tema: llm_brain.gerar_narracao(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))

                with sub_blog:
                    _listar_md("blog", "blog", 500, "blg",
                        fn_regenerar=lambda tema: llm_brain.gerar_blog(
                            tema, emp["nome"], emp["id"], emp["publico_alvo"], emp.get("url_site", "")
                        ))
