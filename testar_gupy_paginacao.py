"""As duas perguntas abertas da reconstrucao da Gupy.

  1. O "total: 100" e o total de verdade ou e teto? (a API velha dizia 252
     pro mesmo termo). Mede com termo estreito e com termo larguissimo: se os
     dois derem exatamente 100, e corte.
  2. Qual URL pede a pagina 2? Testa os candidatos e imprime, de cada um, o
     status, o offset que a resposta declara e o PRIMEIRO titulo. Offset que
     nao anda ou titulo repetido = a URL nao paginou, mesmo com status 200.

Nao usa navegador de proposito: se der pra fazer com requests, a Gupy
continua sem Playwright, como e hoje.
"""
import json
import re
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 30

# Busca POSICIONAL da tag, sem supor ordem de atributo: supor a ordem
# ("<script id=... type=...>") foi exatamente o erro que me custou uma
# rodada na sonda anterior da Gupy.
_ABERTURA = re.compile(r"<script[^>]*__NEXT_DATA__[^>]*>", re.IGNORECASE)


def next_data(html: str) -> dict | None:
    m = _ABERTURA.search(html)
    if not m:
        return None
    fim = html.find("</script>", m.end())
    if fim == -1:
        return None
    try:
        return json.loads(html[m.end():fim])
    except ValueError:
        return None


def ler(url: str) -> tuple[int, dict | None]:
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception as e:
        print(f"    ERRO de rede: {e}")
        return 0, None
    if r.status_code != 200:
        return r.status_code, None
    if r.headers.get("content-type", "").startswith("application/json"):
        try:
            return 200, r.json()
        except ValueError:
            return 200, None
    return 200, next_data(r.text)


def lista(dados: dict | None) -> tuple[dict, list]:
    """(pagination, data) de onde estiver — HTML do portal ou JSON do _next."""
    if not dados:
        return {}, []
    alvo = dados.get("pageProps") or (dados.get("props") or {}).get("pageProps") or {}
    bloco = alvo.get("initialJobList") or {}
    return bloco.get("pagination") or {}, bloco.get("data") or []


def resumir(rotulo: str, url: str) -> None:
    status, dados = ler(url)
    pag, vagas = lista(dados)
    primeiro = (vagas[0].get("name") if vagas else None)
    print(f"    [{rotulo}] status={status} pagination={pag} vagas={len(vagas)}")
    print(f"        1o titulo: {primeiro!r}")


print("=== 1) O total e teto? ===")
for termo in ("analista de dados", "analista", "a"):
    url = f"https://portal.gupy.io/job-search/term={requests.utils.quote(termo)}"
    status, dados = ler(url)
    pag, vagas = lista(dados)
    print(f"  termo={termo!r:22} status={status} pagination={pag} vagas_na_pagina={len(vagas)}")
print("  LEITURA: se todos derem total=100 exato, 100 e corte do portal.")

TERMO = sys.argv[1] if len(sys.argv) > 1 else "analista de dados"
Q = requests.utils.quote(TERMO)
BASE = f"https://portal.gupy.io/job-search/term={Q}"

print(f"\n=== 2) Campos da primeira vaga — '{TERMO}' ===")
status, dados = ler(BASE)
pag, vagas = lista(dados)
if vagas:
    v = vagas[0]
    for campo in ("name", "careerPageName", "publishedDate", "jobUrl",
                  "city", "state", "workplaceType", "isRemoteWork"):
        print(f"    {campo:16} = {v.get(campo)!r}")
    print(f"    (todas as chaves: {sorted(v.keys())})")
else:
    print("    nenhuma vaga — status", status)

build_id = (dados or {}).get("buildId")
print(f"\n    buildId = {build_id!r}")

print(f"\n=== 3) Candidatos pra pagina 2 ===")
print("    (offset tem que ANDAR e o 1o titulo tem que MUDAR)")
resumir("pagina 1, referencia", BASE)
resumir("?page=2", f"{BASE}?page=2")
resumir("?offset=12", f"{BASE}?offset=12")
resumir("?page=2&limit=12", f"{BASE}?page=2&limit=12")
resumir("/page=2 no caminho", f"{BASE}/page=2")
if build_id:
    resumir("_next/data .json?page=2",
            f"https://portal.gupy.io/_next/data/{build_id}/job-search/term={Q}.json?page=2")

print("\n=== 4) A pagina declara link de paginacao? ===")
try:
    html = requests.get(BASE, timeout=TIMEOUT, headers={"User-Agent": UA}).text
    achados = sorted(set(re.findall(r'href="([^"]*(?:page|offset)[^"]*)"', html, re.IGNORECASE)))
    print("\n".join(f"    {h}" for h in achados[:20]) or "    nenhum href com page/offset.")
except Exception as e:
    print(f"    ERRO: {e}")
