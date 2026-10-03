"""Segunda rodada nas fontes portuguesas: o feed do net-empregos e o
rendimento real de itjobs e sapo com OS SEUS termos.

Tres perguntas, nessa ordem de importancia:

  1. O net-empregos declara TRES feeds no proprio robots.txt (rssfeed.asp,
     rss.asp, rss_pesquisas.asp). "rss_pesquisas" sugere feed POR PESQUISA —
     se aceitar termo, e contrato filtrado, o melhor caso possivel.
  2. itjobs e sapo nao tem JSON-LD na LISTAGEM. Falta saber se a pagina da
     VAGA tem: muita vez o schema.org esta so no detalhe. A sonda descobre o
     link da primeira vaga na propria listagem em vez de eu inventar a URL.
  3. Rendimento: das vagas remotas que esses sites tem, quantas passariam no
     filtro internacional de verdade? Rodado com PERFIL_INTL.regras, nao com
     olhometro.

Nao guarda nada. Respeita robots.txt antes de cada acesso, usando as mesmas
funcoes de avaliar_fonte.py.
"""
import re
import sys
from urllib.parse import urlsplit, urljoin

import requests

from avaliar_fonte import caminho_permitido, extrair_jobpostings, regras_do_robots
from core.job import Job
from core.perfis import PERFIL_INTL

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 25


def permitido(url: str) -> bool:
    partes = urlsplit(url)
    raiz = f"{partes.scheme}://{partes.netloc}"
    try:
        txt = requests.get(f"{raiz}/robots.txt", timeout=TIMEOUT,
                           headers={"User-Agent": UA}).text
    except Exception as e:
        print(f"    (nao deu pra ler robots.txt: {e}) — abortando este acesso")
        return False
    ok = caminho_permitido(regras_do_robots(txt), partes.path or "/")
    if not ok:
        print(f"    robots.txt NAO permite {partes.path} — nao vou acessar.")
    return ok


def baixar(url: str) -> str | None:
    if not permitido(url):
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception as e:
        print(f"    ERRO de rede: {e}")
        return None
    print(f"    status={r.status_code} tipo={r.headers.get('content-type','?')[:40]} "
          f"bytes={len(r.content)}")
    return r.text if r.status_code == 200 else None


print("=" * 72)
print("1) OS TRES FEEDS DO NET-EMPREGOS")
print("=" * 72)
FEEDS = [
    "https://www.net-empregos.com/rssfeed.asp",
    "https://www.net-empregos.com/rss.asp",
    "https://www.net-empregos.com/rss_pesquisas.asp",
    # Se rss_pesquisas aceitar termo, estes dois mostram como. Chute
    # declarado COMO chute: a sonda imprime o resultado dos dois pra gente
    # comparar com o feed sem parametro, nao pra eu assumir que funciona.
    "https://www.net-empregos.com/rss_pesquisas.asp?pesquisa=analista+de+dados",
    "https://www.net-empregos.com/rss_pesquisas.asp?q=analista+de+dados",
]
for url in FEEDS:
    print(f"\n--- {url}")
    xml = baixar(url)
    if not xml:
        continue
    itens = re.findall(r"<item\b.*?</item>", xml, re.S | re.I)
    print(f"    <item> encontrados: {len(itens)}")
    if itens:
        primeiro = itens[0]
        print("    CAMPOS do primeiro item:")
        for tag in re.findall(r"<(\w+)[ >]", primeiro):
            if tag.lower() in ("item",):
                continue
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", primeiro, re.S | re.I)
            if m:
                valor = re.sub(r"\s+", " ", m.group(1)).strip()[:95]
                print(f"      {tag:14} = {valor!r}")
        titulos = [re.sub(r"<.*?>", "", re.search(r"<title[^>]*>(.*?)</title>", i, re.S | re.I).group(1)).strip()
                   for i in itens if re.search(r"<title[^>]*>(.*?)</title>", i, re.S | re.I)]
        alvo = [t for t in titulos if re.search(r"dados|data|bi\b|business intelligence|power ?bi|analytics", t, re.I)]
        print(f"    titulos no feed: {len(titulos)} | de dados/BI: {len(alvo)}")
        for t in alvo[:6]:
            print(f"      · {t[:90]}")
    else:
        print("    (sem <item>; primeiros 400 caracteres do que veio:)")
        print("    " + re.sub(r"\s+", " ", xml[:400]))

print("\n" + "=" * 72)
print("2) A PAGINA DA VAGA TEM JSON-LD? (itjobs e sapo)")
print("=" * 72)
LISTAGENS = {
    "itjobs": ("https://www.itjobs.pt/emprego/remote", r'href="(/emprego/\d+[^"]*)"'),
    "sapo":   ("https://emprego.sapo.pt/offers?modelo=teletrabalho", r'href="(/offers?/[^"]+)"'),
}
for nome, (listagem, padrao) in LISTAGENS.items():
    print(f"\n--- {nome}: {listagem}")
    html = baixar(listagem)
    if not html:
        continue
    links = re.findall(padrao, html)
    print(f"    links de vaga achados na listagem: {len(links)}")
    if not links:
        print("    (padrao nao casou — trecho do HTML pra eu achar o certo:)")
        pos = max(html.lower().find("href"), 0)
        print("    " + re.sub(r"\s+", " ", html[pos:pos + 700]))
        continue
    primeiro = urljoin(listagem, links[0])
    print(f"    abrindo a primeira vaga: {primeiro}")
    detalhe = baixar(primeiro)
    if detalhe:
        vagas = extrair_jobpostings(detalhe)
        print(f"    JobPosting (JSON-LD) na pagina da VAGA: {len(vagas)}")
        if vagas:
            v = vagas[0]
            for campo in ("title", "datePosted", "employmentType", "jobLocationType",
                          "hiringOrganization", "jobLocation", "validThrough"):
                if campo in v:
                    print(f"      {campo:20} = {str(v[campo])[:85]}")

print("\n" + "=" * 72)
print("3) RENDIMENTO COM AS SUAS REGRAS (perfil internacional)")
print("=" * 72)
print("Conta so o que o filtro aprovaria de verdade. Local = Portugal,")
print("modalidade = Remoto, porque as duas URLs ja filtram remoto na origem.")
regras = PERFIL_INTL.regras
for nome, (listagem, padrao) in LISTAGENS.items():
    html = baixar(listagem)
    if not html:
        continue
    # titulo = texto do link da vaga
    pares = re.findall(padrao[:-1] + r'[^>]*>\s*([^<]{6,120})', html)
    titulos = [re.sub(r"\s+", " ", t).strip() for t in pares]
    if not titulos:
        print(f"\n--- {nome}: nao consegui extrair titulo com este padrao.")
        continue
    aprovadas = []
    for t in dict.fromkeys(titulos):
        job = Job(titulo=t, empresa="?", local="Portugal", link="https://x/y",
                  site=nome, publicado_em="", modalidade="Remoto")
        if job.combina_com(regras):
            aprovadas.append((job.pontuar_relevancia(regras), t))
    print(f"\n--- {nome}: {len(set(titulos))} titulo(s) remoto(s) na pagina 1, "
          f"{len(aprovadas)} aprovada(s)")
    for nota, t in sorted(aprovadas, reverse=True)[:10]:
        print(f"      nota {nota}: {t[:85]}")
