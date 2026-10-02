"""BUG: desde a reconstrucao de 08/09, TODO link da Solides sai quebrado.

    https://cybersolutions./vacancies/922903?origem=portal   <- falta o dominio
    https:///vacancies/924159?origem=portal                  <- sem host nenhum

Antes da reconstrucao: 1 quebrado em 27. Depois: 9 em 9.

Os testes nao pegaram porque o redirectLink do exemplo era uma URL completa,
escrita a mao. No payload real ele vem de outro jeito -- e este script mostra
QUAL, pra correcao ser no lugar certo e nao um remendo na string.

Rode com o robo parado.
"""
import json
import re

import requests

from scrapers.solides import UA, _payload_desescapado, extrair_vagas, url_da_busca

url = url_da_busca("analista de dados", 1)
print(f"buscando {url}\n")
html = requests.get(url, timeout=30, headers={"User-Agent": UA}).text
vagas = extrair_vagas(html, "analista de dados")
print(f"{len(vagas)} vaga(s) extraida(s)\n")

print("=" * 70)
print("O QUE VEM EM redirectLink (valor cru, 5 primeiras)")
print("=" * 70)
for v in vagas[:5]:
    print(f"  {v.get('title', '')[:40]:40} -> {v.get('redirectLink')!r}")

print()
print("=" * 70)
print("TODAS AS CHAVES DE UMA VAGA (pra achar de onde sai o dominio)")
print("=" * 70)
if vagas:
    for chave, valor in sorted(vagas[0].items()):
        bruto = repr(valor)
        print(f"  {chave:24} {bruto[:90]}")

print()
print("=" * 70)
print("O PAYLOAD MENCIONA solides.jobs EM ALGUM LUGAR?")
print("=" * 70)
payload = _payload_desescapado(html)
achados = set(re.findall(r"[a-z0-9.-]*solides\.jobs[^\"',\\\s]{0,40}", payload))
print(f"  {len(achados)} ocorrencia(s) distinta(s):")
for a in list(achados)[:10]:
    print(f"    {a}")
if not achados:
    print("    NENHUMA -- o dominio nao esta no payload; o portal monta o link")
    print("    no navegador, e o scraper precisa montar tambem (ver companySlug).")
