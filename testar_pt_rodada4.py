"""Rodada 4 — fechar com numero. O que cada bloco decide:

  A. sapo: o HTML cru traz as vagas em JSON, com offer_name, location,
     publication_date e job_description. Entao: quantas vagas vem por
     pagina, quantas sao de fato remotas, e quantas passam no filtro?
     E a pergunta extra que vale por si: das reprovadas SO PELO TITULO,
     quantas passariam se o filtro lesse a DESCRICAO? Isso mede, com dado
     real, a melhoria de precisao que a gente discutiu no abstrato.

  B. michaelpage: /jobs/remote-working existe e o HTML declara o campo
     "remote-working". Testa combinar termo + remoto, le a modalidade do
     proprio slug (-hybrid-, -remote-) e roda o filtro.

  C. randstad: ja deu 0 aprovada em 75 titulos. Aqui so confirma com
     paginacao, pra o descarte ser por numero e nao por impressao.

Tudo com requests. Nenhum dos tres precisa de navegador — eu estava errado
sobre isso nos tres.
"""
import json
import re
from collections import Counter
from urllib.parse import urlsplit

import requests

from avaliar_fonte import caminho_permitido, regras_do_robots
from core.job import Job
from core.perfis import PERFIL_INTL

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30
VOCAB_REMOTO = r"teletrabalh|remot|dist[aâ]ncia|home.?office"
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


def fatiar_json(texto: str, ancora: str):
    """Devolve o objeto JSON que CONTEM a ancora, achando o array que o
    envolve por contagem de chaves — respeitando string e escape. Nao usa
    regex pra isso: descricao de vaga tem chave, virgula e aspas dentro, e
    regex em JSON aninhado erra sem avisar."""
    i = texto.find(ancora)
    if i == -1:
        return None
    # recua ate o '[' que abre a lista
    inicio = texto.rfind("[", 0, i)
    while inicio > 0 and texto[inicio - 1] in " \t\r\n:":
        anterior = texto.rfind("[", 0, inicio)
        if anterior == -1:
            break
        if texto.count("]", anterior, inicio) == 0:
            inicio = anterior
        else:
            break
    if inicio == -1:
        return None
    prof, dentro, escapa = 0, False, False
    for j in range(inicio, len(texto)):
        c = texto[j]
        if escapa:
            escapa = False
            continue
        if c == "\\":
            escapa = True
            continue
        if c == '"':
            dentro = not dentro
            continue
        if dentro:
            continue
        if c in "[{":
            prof += 1
        elif c in "]}":
            prof -= 1
            if prof == 0:
                try:
                    return json.loads(texto[inicio:j + 1])
                except Exception as e:
                    print(f"      (fatia nao e JSON valido: {e})")
                    return None
    return None


regras = PERFIL_INTL.regras

print("#" * 72)
print("# A) sapo: as vagas do HTML cru, e o que a DESCRICAO acrescentaria")
print("#" * 72)
for url in ("https://emprego.sapo.pt/offers?modelo=teletrabalho",
            "https://emprego.sapo.pt/offers?modelo=teletrabalho&page=2"):
    print(f"\n=== {url}")
    r = pegar(url)
    if not r or r.status_code != 200:
        continue
    lista = fatiar_json(r.text, '"offer_name"')
    if not isinstance(lista, list):
        print(f"    nao consegui fatiar a lista (veio {type(lista).__name__}).")
        continue
    vagas = [v for v in lista if isinstance(v, dict) and "offer_name" in v]
    print(f"    status=200 | {len(vagas)} vaga(s) no payload")
    if not vagas:
        continue
    print(f"    CAMPOS disponiveis: {sorted(vagas[0].keys())}")
    v0 = vagas[0]
    for campo in ("offer_name", "location", "job_district", "job_district_all",
                  "job_country", "publication_date", "job_work_hours", "company_name"):
        if campo in v0:
            print(f"      {campo:20} = {str(v0[campo])[:70]!r}")
    desc = str(v0.get("job_description") or "")
    print(f"      job_description      = {len(desc)} caracteres")

    def e_remota(v):
        campos = f"{v.get('offer_name','')} {v.get('location','')} {v.get('job_district','')}"
        return bool(re.search(VOCAB_REMOTO, campos, re.I)) or v.get("job_district_all") is True

    remotas = [v for v in vagas if e_remota(v)]
    print(f"    remotas (pelo proprio dado): {len(remotas)} de {len(vagas)}")

    aprovadas, so_pelo_cargo = [], []
    for v in vagas:
        titulo = str(v.get("offer_name") or "")
        job = Job(titulo=titulo, empresa=str(v.get("company_name") or "?"),
                  local="Portugal", link="https://x/y", site="sapo",
                  publicado_em=str(v.get("publication_date") or "")[:10],
                  modalidade="Remoto" if e_remota(v) else "")
        if job.combina_com(regras):
            aprovadas.append((job.pontuar_relevancia(regras), titulo))
        elif job.rejeitada_so_pelo_cargo(regras):
            so_pelo_cargo.append(v)
    print(f"    APROVADAS pelo titulo: {len(aprovadas)} de {len(vagas)}")
    for nota, t in sorted(aprovadas, reverse=True)[:8]:
        print(f"      nota {nota}: {t[:78]}")

    print(f"\n    --- A PERGUNTA QUE VALE: reprovadas so pelo cargo: {len(so_pelo_cargo)}")
    print("    Dessas, quantas o filtro aprovaria se lesse a DESCRICAO?")
    ganhas = []
    for v in so_pelo_cargo:
        descricao = str(v.get("job_description") or "")
        falso = Job(titulo=str(v.get("offer_name") or "") + " " + descricao[:400],
                    empresa="?", local="Portugal", link="https://x/y", site="sapo",
                    publicado_em="", modalidade="Remoto" if e_remota(v) else "")
        if falso.combina_com(regras):
            ganhas.append((v.get("offer_name"), descricao[:140]))
    print(f"    GANHARIA {len(ganhas)} vaga(s) lendo a descricao:")
    for nome, trecho in ganhas[:6]:
        print(f"      · {str(nome)[:70]}")
        limpo = re.sub(r"\s+", " ", trecho)[:120]
        print(f"        descricao: {limpo}")

print("\n" + "#" * 72)
print("# B) michaelpage: termo + remoto, e a modalidade no slug")
print("#" * 72)
CANDIDATOS = [
    "https://www.michaelpage.pt/jobs/data-analyst",
    "https://www.michaelpage.pt/jobs/remote-working",
    "https://www.michaelpage.pt/jobs/data-analyst/remote-working",   # CHUTE: combinar
    "https://www.michaelpage.pt/jobs/remote-working/data-analyst",   # CHUTE: ordem inversa
    "https://www.michaelpage.pt/jobs/information-technology",
]
for url in CANDIDATOS:
    print(f"\n=== {url}")
    r = pegar(url)
    if not r:
        continue
    if r.status_code != 200:
        print(f"    status={r.status_code}")
        continue
    html = r.text
    pares = re.findall(r'href="(/job-detail/[^"]+)"[^>]*>\s*([^<]{6,120})', html)
    vistos = {}
    for href, texto in pares:
        vistos.setdefault(href, re.sub(r"\s+", " ", texto).strip())
    # a modalidade costuma estar no proprio slug
    mod = Counter()
    for href in vistos:
        achado = re.search(r"-(hybrid|remote|remoto|hibrido|onsite)-", href, re.I)
        mod[achado.group(1).lower() if achado else "nao-declarada"] += 1
    print(f"    status=200 | {len(vistos)} vaga(s) | modalidade no slug: {dict(mod)}")
    aprovadas = []
    for href, titulo in vistos.items():
        remoto = bool(re.search(r"-(remote|remoto)-", href, re.I)) or \
                 bool(re.search(VOCAB_REMOTO, titulo, re.I))
        job = Job(titulo=titulo, empresa="?", local="Portugal", link="https://x/y",
                  site="michaelpage", publicado_em="",
                  modalidade="Remoto" if remoto else "")
        if job.combina_com(regras):
            aprovadas.append((job.pontuar_relevancia(regras), titulo, remoto))
    print(f"    APROVADAS: {len(aprovadas)} de {len(vistos)}")
    for nota, t, remoto in sorted(aprovadas, reverse=True)[:8]:
        print(f"      nota {nota} {'[remoto]' if remoto else '[sem modalidade]'}: {t[:66]}")

print("\n" + "#" * 72)
print("# C) randstad: confirmar o descarte com paginacao")
print("#" * 72)
for pagina in (1, 2):
    url = "https://www.randstad.pt/empregos/" if pagina == 1 else \
          "https://www.randstad.pt/empregos/?page=2"
    print(f"\n=== {url}")
    r = pegar(url)
    if not r or r.status_code != 200:
        continue
    html = r.text
    pares = re.findall(r'href="(/empregos/[^"]*_[^"]*)"[^>]*>\s*([^<]{6,120})', html)
    vistos = {}
    for href, texto in pares:
        vistos.setdefault(href, re.sub(r"\s+", " ", texto).strip())
    remotas = [h for h in vistos if re.search(VOCAB_REMOTO, h, re.I)]
    print(f"    {len(vistos)} vaga(s) | com remoto no slug: {len(remotas)}")
    aprovadas = []
    for href, titulo in vistos.items():
        job = Job(titulo=titulo or href, empresa="?", local="Portugal",
                  link="https://x/y", site="randstad", publicado_em="",
                  modalidade="Remoto" if href in remotas else "")
        if job.combina_com(regras):
            aprovadas.append((job.pontuar_relevancia(regras), titulo or href))
    print(f"    APROVADAS: {len(aprovadas)} de {len(vistos)}")
    for nota, t in sorted(aprovadas, reverse=True)[:6]:
        print(f"      nota {nota}: {t[:74]}")
    if not aprovadas and vistos:
        print("    amostra dos titulos, pra voce julgar o mercado do site:")
        for t in list(vistos.values())[:8]:
            print(f"      · {t[:76]}")
