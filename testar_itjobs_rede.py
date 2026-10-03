"""Verificacao de rede do scraper do itjobs, com os termos de verdade.

Imprime TODOS os campos de cada vaga, LINK INCLUSO — a sonda da Solides
imprimia titulo, local e data e nao o link, e o link ficou quebrado 24 dias
sem ninguem ver. Sonda que nao imprime o campo nao prova o campo.

Imprime tambem o endereco INTEIRO do primeiro JSON-LD, pra confirmar a chave
da cidade: local_da_vaga() le addressLocality, e essa chave NAO foi vista no
dado real (a sondagem truncou no postalCode). Enquanto nao confirmar, o local
sai "Portugal" pela reserva — que funciona, mas perde a cidade.
"""
import json
import sys
import time

import requests

from core.config_intl import TERMOS_BUSCA_INTL
from core.perfis import PERFIL_INTL
from scrapers.itjobs import (
    TIMEOUT,
    UA,
    ITJobsScraper,
    jobposting,
    url_da_pagina,
    vagas_da_listagem,
)

termos = sys.argv[1:] or TERMOS_BUSCA_INTL
print(f"=== termos deste teste ({len(termos)}): {termos[:8]}{' ...' if len(termos) > 8 else ''}")

print("\n=== 1) O ENDERECO INTEIRO DO JSON-LD (confirmar a chave da cidade) ===")
html = requests.get(url_da_pagina(1), timeout=TIMEOUT, headers={"User-Agent": UA}).text
listagem = vagas_da_listagem(html)
print(f"    {len(listagem)} vaga(s) na pagina 1")
if listagem:
    titulo, link = listagem[0]
    detalhe = requests.get(link, timeout=TIMEOUT, headers={"User-Agent": UA}).text
    jp = jobposting(detalhe)
    if jp:
        print(f"    vaga: {link}")
        print(f"    jobLocation inteiro:")
        print("      " + json.dumps(jp.get("jobLocation"), ensure_ascii=False)[:600])
        print(f"    jobLocationType = {jp.get('jobLocationType')!r}")
        print(f"    todas as chaves  = {sorted(jp.keys())}")
    else:
        print("    SEM JSON-LD nessa vaga — o site mudou.")

print("\n=== 2) O SCRAPER DE VERDADE ===")
comeco = time.monotonic()
vagas = ITJobsScraper(termos).buscar_vagas()
duracao = time.monotonic() - comeco

regras = PERFIL_INTL.regras
aprovadas = [v for v in vagas if v.combina_com(regras)]

print(f"\n--- as {len(aprovadas)} aprovada(s), campo por campo ---")
for v in sorted(aprovadas, key=lambda x: -x.pontuar_relevancia(regras)):
    print(f"\n[APROVADA nota {v.pontuar_relevancia(regras)}] {v.titulo}")
    print(f"  empresa     : {v.empresa}")
    print(f"  local       : {v.local!r}")
    print(f"  modalidade  : {v.modalidade!r}")
    print(f"  publicado_em: {v.publicado_em!r}")
    print(f"  link        : {v.link}")

print(f"\n--- amostra de 8 reprovadas, pra ver se o campo veio certo ---")
for v in [x for x in vagas if x not in aprovadas][:8]:
    print(f"  {v.local!r:24} {v.modalidade!r:10} {v.publicado_em!r:12} {v.titulo[:50]!r}")

sem_data = sum(1 for v in vagas if not v.publicado_em)
sem_mod = sum(1 for v in vagas if not v.modalidade)
sem_link = sum(1 for v in vagas if not v.link)
print(f"\n=== {len(vagas)} bruta(s), {len(aprovadas)} aprovada(s) em {duracao:.0f}s ===")
print(f"sem data: {sem_data}/{len(vagas)} | sem modalidade: {sem_mod}/{len(vagas)} "
      f"| sem link: {sem_link}/{len(vagas)}")
print("Compare: LinkedIn 8,5% | Gupy 2,6% | Solides 1,1% | GeekHunter <1% | Senior 0,3%.")
print("Custo pra comparar: o LinkedIn leva 19 min; este rodaria 1x por dia.")
