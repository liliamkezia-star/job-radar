"""Verificacao de rede da Gupy reconstruida.

Imprime TODOS os campos de cada vaga, LINK INCLUSO. A sonda da Solides
imprimia titulo, local e data e nao o link — e o link ficou quebrado 24 dias
sem ninguem ver. Sonda que nao imprime o campo nao prova o campo.

Responde tambem a pergunta que sobrou da sondagem: a ordem da lista. Se as
datas cairem de pagina em pagina, o corte em 100 custa pouco (o topo e o mais
recente, e o robo roda a cada 3h). Se vierem embaralhadas, o corte pode
esconder vaga nova, e ai o teto e problema de verdade.
"""
import sys

import requests

from core.perfis import PERFIL_BR
from scrapers.gupy import (
    GupyScraper,
    POR_PAGINA_PADRAO,
    TIMEOUT,
    UA,
    extrair_lista,
    url_da_busca,
)

TERMO = sys.argv[1] if len(sys.argv) > 1 else "analista de dados"

print(f"=== 1) A ORDEM DA LISTA — '{TERMO}' ===")
print("    (datas caindo = ordenado por recencia; embaralhadas = teto perigoso)")
for pagina in (1, 2, 5, 9):
    url = url_da_busca(TERMO, pagina)
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception as e:
        print(f"    pagina {pagina}: ERRO {e}")
        continue
    extraido = extrair_lista(r.text) if r.status_code == 200 else None
    if not extraido:
        print(f"    pagina {pagina}: status={r.status_code}, sem lista")
        continue
    paginacao, vagas = extraido
    datas = [(v.get("publishedDate") or "")[:10] for v in vagas]
    print(f"    pagina {pagina}: offset={paginacao.get('offset')} vagas={len(vagas)} "
          f"| 1a={datas[0] if datas else None} ultima={datas[-1] if datas else None}")

print(f"\n=== 2) O SCRAPER DE VERDADE — '{TERMO}' ===")
vagas = GupyScraper([TERMO]).buscar_vagas()
regras = PERFIL_BR.regras
aprovadas = [v for v in vagas if v.combina_com(regras)]

print(f"\n--- as {len(aprovadas)} aprovada(s), campo por campo ---")
for v in aprovadas:
    print(f"\n[APROVADA] {v.titulo}")
    print(f"  empresa     : {v.empresa}")
    print(f"  local       : {v.local!r}")
    print(f"  modalidade  : {v.modalidade!r}")
    print(f"  publicado_em: {v.publicado_em!r}")
    print(f"  link        : {v.link}")
    print(f"  nota        : {v.pontuar_relevancia(regras)}")

print("\n--- amostra de 5 reprovadas, pra ver se o campo veio certo ---")
for v in [x for x in vagas if x not in aprovadas][:5]:
    print(f"  {v.local!r:42} {v.modalidade!r:12} {v.publicado_em!r:12} {v.titulo[:45]!r}")

sem_link = sum(1 for v in vagas if not v.link)
sem_data = sum(1 for v in vagas if not v.publicado_em)
sem_local = sum(1 for v in vagas if v.local == "Não informado")
print(f"\n=== {len(vagas)} bruta(s), {len(aprovadas)} aprovada(s) ===")
print(f"sem link: {sem_link}/{len(vagas)} | sem data: {sem_data}/{len(vagas)} "
      f"| sem local: {sem_local}/{len(vagas)}")
print(f"(por_pagina padrao do codigo: {POR_PAGINA_PADRAO})")
print("ANTES da reconstrucao: 0 bruta, 0 aprovada, em tres ciclos seguidos.")
