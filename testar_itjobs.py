"""itjobs.pt — o unico dos cinco sites portugueses que sobreviveu.

POR QUE SO ELE. Dos cinco, sapo/randstad/michaelpage montam os cards por
JavaScript (zero link de vaga no HTML do servidor) e o net-empregos tem feed
bom mas serve outro mercado: 15 de 1.000 titulos sao de tecnologia, e as
categorias do feed sao Industria, Transportes, Restauracao e Construcao.

O itjobs expoe /oferta/N/<slug> no HTML do servidor. Na sonda anterior eu nao
vi isso porque a minha lista de pistas nao tinha a palavra "oferta" — erro
meu, nao do site.

Quatro perguntas:
  1. quantas vagas a rota /emprego/remote lista de verdade, e tem paginacao?
  2. qual o rendimento delas com PERFIL_INTL.regras (nao olhometro)?
  3. a pagina da vaga tem JSON-LD? E se nao, tem modalidade e data no HTML?
  4. da pra buscar por TERMO? Os candidatos abaixo sao CHUTE DECLARADO — a
     sonda imprime o que cada um devolve pra gente comparar, em vez de eu
     assumir que funcionam.
"""
import re
from collections import Counter
from urllib.parse import urljoin, urlsplit

import requests

from avaliar_fonte import caminho_permitido, extrair_jobpostings, regras_do_robots
from core.job import Job
from core.perfis import PERFIL_INTL

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 25
FORMA_VAGA = re.compile(r"^/oferta/(\d+)/([^/?#]+)")


def baixar(url: str, silencioso: bool = False) -> str | None:
    p = urlsplit(url)
    try:
        rb = requests.get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=TIMEOUT,
                          headers={"User-Agent": UA}).text
        if not caminho_permitido(regras_do_robots(rb), p.path or "/"):
            print(f"    robots.txt NAO permite {p.path} — nao acessei.")
            return None
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception as e:
        print(f"    ERRO: {e}")
        return None
    if not silencioso:
        print(f"    status={r.status_code} bytes={len(r.content)}")
    return r.text if r.status_code == 200 else None


def vagas_da_pagina(html: str, base: str) -> list[tuple[str, str]]:
    """(titulo, link). O titulo sai do texto da ancora; quando a ancora
    embrulha outro elemento, cai pro slug da URL, que E o titulo em
    kebab-case. Fallback declarado pra nao depender de marcacao."""
    achados = {}
    for href, texto in re.findall(r'href="([^"]+)"([^>]*>[^<]{0,160})', html):
        m = FORMA_VAGA.match(urlsplit(href).path or "")
        if not m:
            continue
        limpo = re.sub(r"^[^>]*>", "", texto)
        titulo = re.sub(r"\s+", " ", limpo).strip()
        if len(titulo) < 6:
            titulo = m.group(2).replace("-", " ").strip()
        achados.setdefault(urljoin(base, href), titulo)
    return [(t, l) for l, t in achados.items()]


print("=" * 72)
print("1) A ROTA DE REMOTO: quantas vagas, e tem pagina 2?")
print("=" * 72)
BASE = "https://www.itjobs.pt/emprego/remote"
todas = []
for pagina in (1, 2, 3):
    url = BASE if pagina == 1 else f"{BASE}?page={pagina}"
    print(f"\n--- pagina {pagina}: {url}")
    html = baixar(url)
    if not html:
        continue
    vagas = vagas_da_pagina(html, url)
    print(f"    vagas na pagina: {len(vagas)}")
    for t, l in vagas[:4]:
        print(f"      · {t[:70]:72} {l[-45:]}")
    if pagina > 1:
        iguais = {l for _, l in vagas} == {l for _, l in todas[:len(vagas)]}
        print(f"    e a mesma pagina 1 de novo? {iguais}   <<< se SIM, ?page= nao pagina")
    todas.extend(vagas)
    # o que a propria pagina declara de paginacao
    pag = sorted({h for h in re.findall(r'href="([^"]*(?:page|pagina)[^"]*)"', html)})[:6]
    print(f"    links de paginacao declarados: {pag if pag else 'nenhum'}")

unicas = {l: t for t, l in todas}
print(f"\n    TOTAL de vagas distintas coletadas: {len(unicas)}")

print("\n" + "=" * 72)
print("2) RENDIMENTO COM AS SUAS REGRAS (perfil internacional, remoto)")
print("=" * 72)
regras = PERFIL_INTL.regras
aprovadas = []
for link, titulo in unicas.items():
    job = Job(titulo=titulo, empresa="?", local="Portugal", link=link,
              site="ITJobs", publicado_em="", modalidade="Remoto")
    if job.combina_com(regras):
        aprovadas.append((job.pontuar_relevancia(regras), titulo, link))
print(f"    {len(aprovadas)} aprovada(s) de {len(unicas)}")
for nota, t, l in sorted(aprovadas, reverse=True):
    print(f"      nota {nota}: {t[:70]}")
    print(f"               {l}")
if not aprovadas and unicas:
    print("    nenhuma aprovada. Os titulos que havia, pra voce julgar:")
    for t in list(unicas.values())[:15]:
        print(f"      · {t[:85]}")

print("\n" + "=" * 72)
print("3) A PAGINA DA VAGA: JSON-LD, modalidade, data")
print("=" * 72)
for link in list(unicas)[:2]:
    print(f"\n--- {link}")
    det = baixar(link)
    if not det:
        continue
    jp = extrair_jobpostings(det)
    print(f"    JobPosting (JSON-LD): {len(jp)}")
    if jp:
        for campo in ("title", "datePosted", "validThrough", "jobLocationType",
                      "employmentType", "hiringOrganization", "jobLocation"):
            if campo in jp[0]:
                print(f"      {campo:18} = {str(jp[0][campo])[:85]}")
    else:
        texto = re.sub(r"<script.*?</script>", " ", det, flags=re.S)
        texto = re.sub(r"<[^>]+>", " ", texto)
        texto = re.sub(r"\s+", " ", texto)
        for rotulo, padrao in (("modalidade", r"(Remoto|Teletrabalho|H[íi]brido|Presencial)"),
                               ("data", r"(\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2})"),
                               ("local", r"(Lisboa|Porto|Braga|Coimbra|Aveiro|Portugal)")):
            achados = Counter(re.findall(padrao, texto, re.I)).most_common(3)
            print(f"      {rotulo:12} no HTML: {achados if achados else 'nao achei'}")

print("\n" + "=" * 72)
print("4) DA PRA BUSCAR POR TERMO? (candidatos = CHUTE DECLARADO)")
print("=" * 72)
CANDIDATOS = [
    "https://www.itjobs.pt/emprego/data",
    "https://www.itjobs.pt/emprego/power-bi",
    "https://www.itjobs.pt/emprego?q=data+analyst",
    "https://www.itjobs.pt/emprego/pesquisa?q=data+analyst",
    "https://www.itjobs.pt/emprego/remote?q=data",
]
for url in CANDIDATOS:
    print(f"\n--- {url}")
    html = baixar(url)
    if not html:
        continue
    vagas = vagas_da_pagina(html, url)
    print(f"    vagas: {len(vagas)}")
    for t, _ in vagas[:4]:
        print(f"      · {t[:80]}")
    if vagas and len(unicas) and {l for _, l in vagas} == set(unicas):
        print("    <<< devolveu EXATAMENTE a mesma lista de /emprego/remote: nao filtrou")
