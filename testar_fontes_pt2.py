"""Segunda tentativa — agora DESCOBRINDO o padrao em vez de adivinhar.

Na rodada anterior eu chutei 'href="/emprego/\\d+..."' e 'href="/offers/..."'
e os dois deram zero. Chute de marcacao e o erro que mais me custou tempo
nesta base (tres vezes nesta semana). Entao aqui a sonda:

  1. coleta TODOS os href da pagina, troca digito por N e conta a frequencia
     das FORMAS. O padrao da vaga aparece sozinho: e a forma que repete 10,
     20, 50 vezes. Nada de eu imaginar como e.
  2. so depois extrai titulo dos links da forma mais provavel e roda o filtro
     internacional de verdade.
  3. no net-empregos, imprime amostra de titulos do feed e conta quanta vaga
     de TECNOLOGIA existe ali — pra separar "o site nao tem dados/BI" de "meu
     regex nao pegou".
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


def baixar(url: str) -> str | None:
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
    print(f"    status={r.status_code} bytes={len(r.content)}")
    return r.text if r.status_code == 200 else None


def formas_de_href(html: str, host: str) -> Counter:
    """Frequencia das FORMAS de caminho (digito -> N). O link de vaga e o que
    repete muito; menu e rodape aparecem uma ou duas vezes."""
    formas = Counter()
    bruto = {}
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        p = urlsplit(href)
        if p.netloc and host not in p.netloc:
            continue
        caminho = p.path or "/"
        forma = re.sub(r"\d+", "N", caminho)
        forma = re.sub(r"/[^/]{25,}", "/<slug-longo>", forma)
        formas[forma] += 1
        bruto.setdefault(forma, href)
    return formas, bruto


ALVOS = {
    "itjobs": ("https://www.itjobs.pt/emprego/remote", "itjobs.pt"),
    "sapo":   ("https://emprego.sapo.pt/offers?modelo=teletrabalho", "sapo.pt"),
}

print("=" * 72)
print("1) QUAL E A FORMA DO LINK DE VAGA (descoberta, nao chute)")
print("=" * 72)
guardados = {}
for nome, (url, host) in ALVOS.items():
    print(f"\n--- {nome}: {url}")
    html = baixar(url)
    if not html:
        continue
    guardados[nome] = (html, url)
    formas, exemplo = formas_de_href(html, host)
    print(f"    {len(formas)} forma(s) distinta(s). As 12 que mais repetem:")
    for forma, n in formas.most_common(12):
        print(f"      {n:4}x  {forma[:62]:64} ex: {exemplo[forma][:60]}")

print("\n" + "=" * 72)
print("2) TITULO E RENDIMENTO, usando a forma mais repetida que parece vaga")
print("=" * 72)
regras = PERFIL_INTL.regras
PISTAS = ("emprego", "offer", "vaga", "job", "anuncio")
for nome, (html, url) in guardados.items():
    _, _host = ALVOS[nome]
    formas, exemplo = formas_de_href(html, _host)
    # candidata: mais repetida cujo caminho tem pista de vaga E mais de 1
    # segmento (evita cair na propria listagem, que repete no menu)
    candidatas = [(n, f) for f, n in formas.items()
                  if n >= 5 and any(p in f.lower() for p in PISTAS)
                  and f.count("/") >= 2]
    if not candidatas:
        print(f"\n--- {nome}: nenhuma forma repetida com pista de vaga. "
              "A listagem provavelmente monta os cards por JavaScript.")
        continue
    n, forma = max(candidatas)
    padrao = "^" + re.escape(forma).replace("N", r"\d+").replace(r"<slug\-longo>", r"[^\"/]+") + "$"
    print(f"\n--- {nome}: usando a forma {forma!r} ({n}x)")
    titulos, links = [], []
    for href, texto in re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{4,140})', html):
        caminho = urlsplit(href).path or "/"
        if re.match(padrao, re.sub(r"\d+", "N", caminho)):
            t = re.sub(r"\s+", " ", texto).strip()
            if len(t) >= 6:
                titulos.append(t)
                links.append(urljoin(url, href))
    unicos = list(dict.fromkeys(titulos))
    print(f"    titulos extraidos: {len(unicos)}")
    for t in unicos[:8]:
        print(f"      · {t[:85]}")
    aprovadas = []
    for t in unicos:
        job = Job(titulo=t, empresa="?", local="Portugal", link="https://x/y",
                  site=nome, publicado_em="", modalidade="Remoto")
        if job.combina_com(regras):
            aprovadas.append((job.pontuar_relevancia(regras), t))
    print(f"    APROVADAS pelo filtro internacional: {len(aprovadas)} de {len(unicos)}")
    for nota, t in sorted(aprovadas, reverse=True)[:10]:
        print(f"      nota {nota}: {t[:85]}")
    if links:
        print(f"    JSON-LD na pagina da primeira vaga ({links[0][:70]}):")
        det = baixar(links[0])
        if det:
            vagas = extrair_jobpostings(det)
            print(f"      JobPosting encontrados: {len(vagas)}")
            if vagas:
                for campo in ("title", "datePosted", "jobLocationType",
                              "employmentType", "hiringOrganization", "jobLocation"):
                    if campo in vagas[0]:
                        print(f"        {campo:18} = {str(vagas[0][campo])[:80]}")

print("\n" + "=" * 72)
print("3) O NET-EMPREGOS TEM VAGA DE TECNOLOGIA? (checando o meu proprio 0/1000)")
print("=" * 72)
xml = baixar("https://www.net-empregos.com/rss.asp")
if xml:
    itens = re.findall(r"<item\b.*?</item>", xml, re.S | re.I)
    titulos = []
    for i in itens:
        m = re.search(r"<title[^>]*>(.*?)</title>", i, re.S | re.I)
        if m:
            t = m.group(1)
            t = re.sub(r"<!\[CDATA\[|\]\]>", "", t)
            titulos.append(re.sub(r"\s+", " ", t).strip())
    print(f"    {len(titulos)} titulos lidos")
    print("    AMOSTRA de 15, pra ver a cara do site:")
    for t in titulos[:15]:
        print(f"      · {t[:85]}")
    grupos = {
        "dados/BI": r"dados|data\b|\bbi\b|business intelligence|power ?bi|analytics",
        "tecnologia em geral": r"program|developer|software|informátic|informatic|"
                               r"tecnolog|sistemas|web|python|java|sql|devops|\bti\b",
    }
    for rotulo, padrao in grupos.items():
        achados = [t for t in titulos if re.search(padrao, t, re.I)]
        print(f"    {rotulo:22}: {len(achados)} de {len(titulos)}")
        for t in achados[:6]:
            print(f"      · {t[:85]}")
    # categoria vem na descricao do item
    cats = Counter()
    for i in itens:
        m = re.search(r"Categoria:\s*(?:&lt;/b&gt;)?\s*([^&<]{3,40})", i)
        if m:
            cats[m.group(1).strip()] += 1
    print(f"    categorias mais comuns no feed: {cats.most_common(8)}")
