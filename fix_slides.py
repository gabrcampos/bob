#!/usr/bin/env python3
"""Corrige slides problemáticos: DD slides 2-5 (fonte AnkaCoder) e TS slide 2 (texto na imagem)."""
import sys
sys.path.insert(0, "/home/campos_1122/bob")

from modulos.db import buscar_empresa, atualizar_empresa, buscar_conteudo
from modulos.gerador_imagens import (
    gerar_imagem_slide_misto_dd,
    gerar_imagem_slide,
    listar_imagens_misto_dd,
    listar_imagens,
    imagens_para_pdf,
)
from pathlib import Path

DD_CONTEUDO_ID = "6a3bef086348e5bbe08132e1"
TS_CONTEUDO_ID = "6a3bef1d069456fbe3524d51"
DD_STEM = "como_restaurantes_perdem_avaliacoes_no_horario_de_pico_por_f_20260624_145152"
TS_STEM = "a_integracao_wms_tms_oms_como_elo_perdido_da_ultima_milha_no_20260624_145213"

# ── 1. Atualizar fonte AnkaCoder → Space Mono no MongoDB ─────────────────────
print("=" * 60)
print("PASSO 1: Atualizando fonte DeliveryDash no MongoDB")
dd_empresa = buscar_empresa("deliverydash")
fontes_atuais = dd_empresa.get("identidade_visual", {}).get("fontes", [])
print(f"  Fontes atuais: {fontes_atuais}")

atualizar_empresa("deliverydash", {"identidade_visual.fontes": ["Anton", "Space Mono"]})
dd_empresa = buscar_empresa("deliverydash")
fontes_novas = dd_empresa.get("identidade_visual", {}).get("fontes", [])
print(f"  Fontes novas:  {fontes_novas}")

# ── 2. Regenerar DD slides 2, 3, 4, 5 com fundo_fixo=True ───────────────────
print()
print("PASSO 2: Regenerando DD slides 2, 3, 4, 5 (fundo_fixo=True)")
dd_conteudo = buscar_conteudo(DD_CONTEUDO_ID)
dd_slides = dd_conteudo.get("slides", [])
dd_iv = dd_empresa.get("identidade_visual", {})

for slide in dd_slides:
    n = int(slide.get("slide", 0))
    if n in (2, 3, 4, 5):
        print(f"  → Slide {n}: {slide.get('titulo', '')}")
        path = gerar_imagem_slide_misto_dd(
            slide=slide,
            empresa_id="deliverydash",
            empresa_nome="DeliveryDash",
            stem=DD_STEM,
            identidade_visual=dd_iv,
            logo_index=1,
            fundo_fixo=True,
        )
        print(f"    Salvo: {path}")

# ── 3. Regenerar TS slide 2 com novo prompt (sem celular com texto) ───────────
print()
print("PASSO 3: Regenerando TS slide 2 (novo prompt_imagem)")
ts_empresa = buscar_empresa("tecnosolve")
ts_conteudo = buscar_conteudo(TS_CONTEUDO_ID)
ts_slides = ts_conteudo.get("carrossel", [])
ts_iv = ts_empresa.get("identidade_visual", {})

novo_prompt_ts2 = (
    "A logistics manager at a standing desk reviewing printed delivery reports "
    "in a modern warehouse office, focused expression, natural light, no screens visible"
)

for slide in ts_slides:
    n = int(slide.get("slide", 0))
    if n == 2:
        slide_corrigido = dict(slide)
        slide_corrigido["prompt_imagem"] = novo_prompt_ts2
        print(f"  → Slide 2: {slide.get('titulo', '')}")
        print(f"    Novo prompt: {novo_prompt_ts2}")
        path = gerar_imagem_slide(
            slide=slide_corrigido,
            empresa_id="tecnosolve",
            stem=TS_STEM,
            identidade_visual=ts_iv,
            is_ultimo=False,
            logo_index=1,
            fundo_fixo=False,
        )
        print(f"    Salvo: {path}")
        break

# ── 4. Regenerar PDFs ─────────────────────────────────────────────────────────
print()
print("PASSO 4: Regenerando PDFs")

# DD PDF
dd_imagens = listar_imagens_misto_dd("deliverydash", DD_STEM)
print(f"  DD: {len(dd_imagens)} imagens encontradas")
dd_pdf_bytes = imagens_para_pdf(dd_imagens)
dd_pdf_path = Path(f"outputs/deliverydash/{DD_STEM}_misto_dd.pdf")
dd_pdf_path.write_bytes(dd_pdf_bytes)
print(f"  DD PDF salvo: {dd_pdf_path}")

# TS PDF
ts_imagens = listar_imagens("tecnosolve", TS_STEM)
print(f"  TS: {len(ts_imagens)} imagens encontradas")
ts_pdf_bytes = imagens_para_pdf(ts_imagens)
ts_pdf_path = Path(f"outputs/tecnosolve/{TS_STEM}.pdf")
ts_pdf_path.write_bytes(ts_pdf_bytes)
print(f"  TS PDF salvo: {ts_pdf_path}")

print()
print("✓ Correções concluídas!")
