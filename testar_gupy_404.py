"""A Gupy parou de responder. MEDIDO nos ciclos 388-390 (01-02/10): status 404
em TODO termo, zero vaga. A ultima vaga dela entrou em 28/09 as 21:02 -- ou
seja, a API funcionou ate 28/09 e quebrou nos dias seguintes.

404 e diferente dos outros erros que a gente ja viu nesta base:

    403 (Solides)  -> acesso recusado; a rota existe, voce nao entra
    504            -> servidor sobrecarregado, tenta depois
    404 (aqui)     -> a ROTA NAO EXISTE mais

Mesma classe do que aconteceu com a Solides em 07/09. E la a fonte foi salva
porque o portal novo servia os mesmos dados por outro caminho -- entao vale
sondar antes de desligar.

ESTE SCRIPT RESPONDE, EM ORDEM:

  1. A rota antiga mesmo morreu, ou foi coisa passageira?
  2. O portal da Gupy tem rota nova que devolva as vagas?
  3. O robots.txt permite?
  4. As vagas vem no HTML cru (requests, sem navegador) ou so depois do
     JavaScript? Essa e a pergunta que decide se reconstruir sai barato.

Rode com o robo parado.
"""
import re

import requests

from avaliar_fonte import caminho_permitido, extrair_jobpostings, regras_do_robots
# A API morta. Vivia em scrapers/gupy.py como URL_API; saiu de la na
# reconstrucao de 02/10 e ficou aqui, que e o unico lugar que ainda fala dela.
URL_API = "https://employability-portal.gupy.io/api/v1/jobs"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CABECALHO = {"User-Agent": UA, "Accept": "application/json"}

print("=" * 72)
print("1) A ROTA ANTIGA")
print("=" * 72)
for rotulo, url in (
    ("como o scraper chama", f"{URL_API}?jobName=analista+de+dados&limit=10&offset=0"),
    ("sem parametro nenhum", URL_API),
    ("raiz da API", URL_API.rsplit("/api/", 1)[0] + "/api/v1/"),
):
    try:
        r = requests.get(url, timeout=25, headers=CABECALHO)
        print(f"  {rotulo:24} {r.status_code}  {r.text[:90]!r}")
    except Exception as e:
        print(f"  {rotulo:24} ERRO {type(e).__name__}")

print()
print("=" * 72)
print("2) ROTAS CANDIDATAS NO PORTAL")
print("=" * 72)
CANDIDATAS = [
    "https://portal.gupy.io/job-search/term=analista%20de%20dados",
    "https://portal.gupy.io/api/job-search?term=analista+de+dados",
    "https://employability-portal.gupy.io/api/v2/jobs?jobName=analista+de+dados",
    "https://portal.api.gupy.io/api/v1/jobs?jobName=analista+de+dados",
]
for url in CANDIDATAS:
    try:
        r = requests.get(url, timeout=25, headers=CABECALHO)
        tipo = r.headers.get("content-type", "")[:30]
        vagas = len(re.findall(r'"jobId"|"careerPageName"|"jobUrl"', r.text))
        print(f"  {r.status_code}  {len(r.text):>7}b  {tipo:30}  marcas de vaga: {vagas}")
        print(f"       {url}")
    except Exception as e:
        print(f"  ERRO {type(e).__name__:22}  {url}")

print()
print("=" * 72)
print("3) ROBOTS.TXT DO PORTAL")
print("=" * 72)
try:
    texto = requests.get("https://portal.gupy.io/robots.txt", timeout=20,
                         headers={"User-Agent": UA}).text
    regras = regras_do_robots(texto)
    for caminho in ("/job-search", "/api/job-search", "/vagas"):
        print(f"  {'PERMITIDO' if caminho_permitido(regras, caminho) else 'BLOQUEADO':10} {caminho}")
    if not regras:
        print("  (sem regra pro agente '*')")
except Exception as e:
    print(f"  nao deu pra ler: {type(e).__name__}")

print()
print("=" * 72)
print("4) O HTML DA BUSCA TEM AS VAGAS?")
print("=" * 72)
url = "https://portal.gupy.io/job-search/term=analista%20de%20dados"
try:
    html = requests.get(url, timeout=30, headers={"User-Agent": UA}).text
    print(f"  {len(html)} bytes")
    print(f"  JobPosting em JSON-LD ....... {len(extrair_jobpostings(html))}")
    print(f"  ocorrencias de 'jobId' ...... {len(re.findall(r'jobId', html))}")
    # f-string nao aceita barra invertida dentro da expressao (ja me pegou
    # antes nesta base) -- calcula fora.
    links = set(re.findall(r"https://[a-z0-9-]+\.gupy\.io/job/[A-Za-z0-9=]+", html))
    print(f"  links de vaga (.gupy.io/job) {len(links)}")
    print(f"  blocos RSC do Next.js ....... {len(re.findall(r'self.__next_f.push', html))}")
    print(f"  __NEXT_DATA__ presente ...... {'__NEXT_DATA__' in html}")
except Exception as e:
    print(f"  ERRO: {type(e).__name__}")

print()
print("=" * 72)
print("COMO LER")
print("=" * 72)
print("  · se alguma rota da 200 com marcas de vaga -> ha API nova, e o conserto")
print("    e trocar a URL. Melhor caso.")
print("  · se nao, e o HTML da busca tiver jobId/JSON-LD/bloco RSC -> da pra")
print("    raspar com requests, como foi feito na Solides.")
print("  · se o HTML vier sem nada disso -> precisaria de navegador, e ai a conta")
print("    muda: a Gupy sao 107 vagas de 3.559 (3,0%) no historico.")
