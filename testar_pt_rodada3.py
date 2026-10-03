"""Rodada 3: as quatro pistas que a rodada 2 abriu.

Cada bloco responde UMA pergunta que decide um site:

  A. net-empregos: trovit_all.asp e careerjet_all.asp sao FEEDS DE PARCEIRO
     (Trovit e Careerjet sao agregadores). O site declara os dois no
     robots.txt. Feed de parceiro costuma trazer o catalogo inteiro com campo
     de local e modalidade. Se tiver, e o melhor contrato dos cinco sites.

  B. sapo: o navegador renderizou 14 links de vaga, e NENHUMA resposta XHR
     trouxe vaga. Logo os dados provavelmente vem embutidos no HTML inicial e
     o JavaScript so os pinta. Teste: procurar no HTML cru (requests) um
     titulo que o navegador mostrou. Se achar, da pra ler sem navegador — e
     os 34,5s por pagina caem pra menos de 1s.

  C. randstad: o slug da vaga JA diz a modalidade
     (..._remote-in-portugal-, ..._lisbon-hybrid) e existe
     <option value="remote-in-portugal-">. Duas coisas a achar: como separar
     link de VAGA de link de CATEGORIA (a vaga tem "_" no slug) e se existe
     URL que filtre remoto.

  D. michaelpage: a faceta "Trabalho Remoto / Hibrido" tem CONTADOR (181 no
     geral, 2 em /jobs/data-analyst). Falta achar como pedir essa faceta por
     URL.

Os candidatos de URL estao marcados como CHUTE onde sao chute.
"""
import json
import re
from collections import Counter
from urllib.parse import urljoin, urlsplit

import requests

from avaliar_fonte import caminho_permitido, regras_do_robots
from core.job import Job
from core.perfis import PERFIL_INTL

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30
VOCAB_REMOTO = r"teletrabalh|remot|dist[aâ]ncia|home.?office|h[ií]brid|hybrid"
_robots = {}


def pegar(url: str):
    p = urlsplit(url)
    raiz = f"{p.scheme}://{p.netloc}"
    if raiz not in _robots:
        try:
            _robots[raiz] = requests.get(f"{raiz}/robots.txt", timeout=TIMEOUT,
                                         headers={"User-Agent": UA}).text
        except Exception:
            _robots[raiz] = ""
    if _robots[raiz] and not caminho_permitido(regras_do_robots(_robots[raiz]), p.path or "/"):
        print(f"      robots.txt NAO permite {p.path} — nao acessei.")
        return None
    try:
        return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except Exception as e:
        print(f"      ERRO: {e}")
        return None


regras = PERFIL_INTL.regras

print("#" * 72)
print("# A) net-empregos: os feeds de parceiro (Trovit e Careerjet)")
print("#" * 72)
for url in ("http://www.net-empregos.com/careerjet_all.asp",
            "http://www.net-empregos.com/trovit_all.asp"):
    print(f"\n=== {url}")
    r = pegar(url)
    if not r:
        continue
    texto = r.text
    print(f"    status={r.status_code} bytes={len(r.content)} "
          f"tipo={r.headers.get('content-type','?')[:40]}")
    print(f"    primeiros 400 caracteres:")
    print("      " + re.sub(r"\s+", " ", texto[:400]))
    # Qual tag repete? Essa e a unidade do feed (<job>, <ad>, <item>...)
    tags = Counter(t.lower() for t in re.findall(r"<(\w+)[\s>]", texto))
    print(f"    tags que mais repetem: {tags.most_common(12)}")
    unidade = None
    for tag, n in tags.most_common(12):
        if n >= 20 and tag not in ("loc", "url", "urlset", "channel", "rss"):
            unidade = tag
            break
    if not unidade:
        print("    nao identifiquei a unidade do feed.")
        continue
    blocos = re.findall(rf"<{unidade}\b.*?</{unidade}>", texto, re.S | re.I)
    print(f"    unidade do feed: <{unidade}> | {len(blocos)} registro(s)")
    if blocos:
        print(f"    CAMPOS do primeiro registro:")
        for tag in dict.fromkeys(re.findall(r"<(\w+)[\s>]", blocos[0])):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", blocos[0], re.S | re.I)
            if m:
                v = re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))
                valor = re.sub(r"\s+", " ", v).strip()[:80]
                print(f"      {tag:16} = {valor!r}")
        com_remoto = [b for b in blocos if re.search(VOCAB_REMOTO, b, re.I)]
        print(f"    registros que mencionam remoto/teletrabalho: {len(com_remoto)} de {len(blocos)}")
        titulos = []
        for b in blocos:
            m = re.search(r"<title[^>]*>(.*?)</title>", b, re.S | re.I)
            if m:
                bruto = re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))
                titulos.append(re.sub(r"\s+", " ", bruto).strip())
        aprov = []
        for t in dict.fromkeys(titulos):
            job = Job(titulo=t, empresa="?", local="Portugal", link="https://x/y",
                      site="net-empregos", publicado_em="", modalidade="Remoto")
            if job.combina_com(regras):
                aprov.append((job.pontuar_relevancia(regras), t))
        print(f"    APROVADAS pelo filtro, no feed inteiro: {len(aprov)} de {len(set(titulos))}")
        for nota, t in sorted(aprov, reverse=True)[:10]:
            print(f"      nota {nota}: {t[:80]}")

print("\n" + "#" * 72)
print("# B) sapo: a vaga esta no HTML cru, sem navegador?")
print("#" * 72)
# Titulos que o NAVEGADOR mostrou nessa mesma URL, na rodada anterior.
TITULOS_VISTOS = [
    "Cobol Developer (Remoto, Portugal)",
    "QA Automation Engineer - French Speaker (Remoto, Portugal)",
    "Buyer Onboarding Support Agent",
]
r = pegar("https://emprego.sapo.pt/offers?modelo=teletrabalho")
if r:
    html = r.text
    print(f"    HTML cru: {len(html)} caracteres")
    for t in TITULOS_VISTOS:
        achou = t.lower() in html.lower()
        print(f"    {'ACHOU' if achou else 'nao achou':10} {t[:60]!r}")
        if achou:
            i = html.lower().find(t.lower())
            trecho = re.sub(r"\s+", " ", html[max(0, i - 220):i + 120])
            print(f"      contexto: ...{trecho}...")
    # o payload pode estar num <script>
    for m in re.finditer(r"<script[^>]*>(.{200,}?)</script>", html, re.S):
        corpo = m.group(1)
        if re.search(r"\"(title|jobTitle|offers|slug)\"\s*:", corpo):
            print(f"    <script> com cara de payload de vaga ({len(corpo)} chars):")
            print("      " + re.sub(r"\s+", " ", corpo[:300]))
            break
    else:
        print("    nenhum <script> com payload de vaga no HTML cru.")

print("\n" + "#" * 72)
print("# C) randstad: separar vaga de categoria, e achar o filtro de remoto")
print("#" * 72)
CANDIDATOS_RANDSTAD = [
    "https://www.randstad.pt/empregos/",                                  # referencia
    "https://www.randstad.pt/empregos/remote-in-portugal-/",              # CHUTE: o value da option como caminho
    "https://www.randstad.pt/empregos/?localidade=remote-in-portugal-",   # CHUTE
    "https://www.randstad.pt/empregos/?location=remote-in-portugal-",     # CHUTE
]
for url in CANDIDATOS_RANDSTAD:
    print(f"\n=== {url}")
    r = pegar(url)
    if not r or r.status_code != 200:
        print(f"    status={r.status_code if r else 'erro'}")
        continue
    html = r.text
    # vaga tem "_" no slug; categoria nao. Isso veio dos dados, nao de chute.
    vagas = sorted(set(re.findall(r'href="(/empregos/[^"]*_[^"]*)"', html)))
    print(f"    status=200 bytes={len(r.content)} | links com '_' (vaga): {len(vagas)}")
    for v in vagas[:6]:
        print(f"      · {v[:95]}")
    if vagas:
        modalidades = Counter()
        for v in vagas:
            sufixo = v.rstrip("/").rsplit("_", 1)[-1]
            modalidades[sufixo] += 1
        print(f"    sufixos de modalidade/local no slug: {modalidades.most_common(10)}")
        remotas = [v for v in vagas if re.search(VOCAB_REMOTO, v, re.I)]
        print(f"    vagas com remoto no slug: {len(remotas)} de {len(vagas)}")

print("\n" + "#" * 72)
print("# D) michaelpage: como pedir a faceta de remoto por URL")
print("#" * 72)
CANDIDATOS_MP = [
    "https://www.michaelpage.pt/jobs/data-analyst",                        # referencia
    "https://www.michaelpage.pt/jobs/data-analyst?remote=true",            # CHUTE
    "https://www.michaelpage.pt/jobs/data-analyst?workfromhome=true",      # CHUTE
    "https://www.michaelpage.pt/jobs/remote-working",                      # CHUTE
    "https://www.michaelpage.pt/jobs/teletrabalho",                        # CHUTE
]
for url in CANDIDATOS_MP:
    print(f"\n=== {url}")
    r = pegar(url)
    if not r:
        continue
    html = r.text
    vagas = sorted(set(re.findall(r'href="(/job-detail/[^"]+)"', html)))
    contador = re.findall(r"Trabalho Remoto\s*/\s*H[íi]brido[^\d]{0,40}(\d+)", html, re.I)
    print(f"    status={r.status_code} bytes={len(r.content)} | "
          f"links de vaga no HTML cru: {len(vagas)}")
    print(f"    contador da faceta 'Trabalho Remoto / Hibrido': {contador[:3] or 'nao achei'}")
    # o HTML pode declarar o parametro da faceta num input/checkbox
    facetas = re.findall(r'<input[^>]*(?:name|id|value)="([^"]*(?:remote|hibrid|hybrid|work)[^"]*)"[^>]*>',
                         html, re.I)
    if facetas:
        print(f"    campos de faceta declarados no HTML: {sorted(set(facetas))[:8]}")
