"""A Solides aposentou a API que o scraper usava. MEDIDO em 07-08/09:

    GET apigw.solides.com.br/jobs/v3/portal-vacancies-new
    -> 403 {"message":"Missing Authentication Token"}

Essa mensagem e do AWS API Gateway e e o que ele responde quando a ROTA NAO
EXISTE. O 403 veio de tres lugares: do datacenter do Actions, do IP residencial
com quatro variacoes de cabecalho, e de DENTRO da propria pagina do portal num
Chrome com sessao do site. Nao e IP, nao e cabecalho, nao e cookie.

O portal foi refeito: URLs novas (/vagas/todas, /vagas/area/tecnologia/todas,
/vagas/recife-pe), e a pagina mostra "Encontramos 72.920 oportunidades" com as
vagas no proprio HTML.

ESTE SCRIPT DECIDE SE VALE RECONSTRUIR, E COMO. A pergunta e uma so:

    as vagas vem no HTML CRU (requests, sem navegador)?

  · SE VIEREM -> da pra raspar com requests, rapido como a API era, e a
    reconstrucao vale a pena.
  · SE SO APARECEREM depois do JavaScript rodar -> seria voltar pro Playwright,
    que e lento e e exatamente de onde a gente saiu ha uma semana. Ai o custo
    da reconstrucao muda de figura.

Checa tambem o robots.txt das rotas novas ANTES de qualquer coisa.

Rode com o robo parado.
"""
import re

import requests

from avaliar_fonte import caminho_permitido, extrair_jobpostings, regras_do_robots

BASE = "https://vagas.solides.com.br"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ROTAS = [
    "/vagas/todas",
    "/vagas/analista-de-dados/todas",
    "/vagas/area/tecnologia/todas",
    "/vagas/recife-pe",
]

print("=" * 72)
print("1) ROBOTS.TXT -- o que eles permitem")
print("=" * 72)
try:
    texto = requests.get(f"{BASE}/robots.txt", timeout=20,
                         headers={"User-Agent": UA}).text
    regras = regras_do_robots(texto)
    for rota in ROTAS:
        ok = caminho_permitido(regras, rota)
        print(f"  {'PERMITIDO' if ok else 'BLOQUEADO':10} {rota}")
    if not regras:
        print("  (robots.txt sem regra pro agente '*' -- nada bloqueado)")
except Exception as erro:
    print(f"  nao deu pra ler o robots.txt: {type(erro).__name__}")

print()
print("=" * 72)
print("2) O HTML CRU TEM AS VAGAS? (requests, sem navegador)")
print("=" * 72)
for rota in ROTAS:
    try:
        r = requests.get(f"{BASE}{rota}", timeout=30, headers={"User-Agent": UA})
    except Exception as erro:
        print(f"\n  {rota}\n    ERRO: {type(erro).__name__}")
        continue

    html = r.text
    # Links de vaga no portal novo: subdominio da empresa + /vagas/<id>
    links = set(re.findall(r"https://[a-z0-9-]+\.vagas\.solides\.com\.br/vagas/\d+", html))
    contagem = re.search(r"Encontramos\s+([\d.]+)\s+oportunidades", html)
    jsonld = extrair_jobpostings(html)

    print(f"\n  {rota}")
    print(f"    status {r.status_code} | {len(html):>7} bytes")
    print(f"    links de vaga no HTML cru ....... {len(links)}")
    print(f"    'Encontramos N oportunidades' ... {contagem.group(1) if contagem else 'nao'}")
    print(f"    JobPosting em JSON-LD ........... {len(jsonld)}")
    for link in list(links)[:3]:
        print(f"      · {link}")

print()
print("=" * 72)
print("COMO LER")
print("=" * 72)
print("  · links de vaga > 0 no HTML cru -> DA pra raspar com requests. A")
print("    reconstrucao e viavel e rapida, e a rota que achou mais vagas e o")
print("    ponto de partida.")
print("  · links = 0 em todas, mas a pagina abre no navegador -> o conteudo so")
print("    existe depois do JavaScript. Reconstruir significa voltar pro")
print("    Playwright: ~7 minutos de ciclo, que foi o que a migracao pra API")
print("    eliminou. Ai a conta muda e vale reconsiderar desligar a fonte.")
print("  · JobPosting em JSON-LD > 0 -> melhor cenario de todos: e formato")
print("    padronizado (schema.org), o mais estavel que existe pra raspar.")
print("  · Qualquer rota BLOQUEADA no robots.txt sai da lista, nao importa o")
print("    que ela devolva.")
