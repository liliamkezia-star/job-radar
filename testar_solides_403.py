"""A Solides passou a responder 403 em TODOS os termos, no ciclo do GitHub
Actions de 07/09 18:16. Nao e 504 (servidor sobrecarregado) nem count=0
(resposta vazia): 403 e a API recusando o acesso, na pagina 1, em menos de um
segundo.

Foi a terceira falha diferente da Solides em uma semana. Antes de mexer em
qualquer coisa, este script separa as duas causas possiveis -- e elas pedem
correcoes opostas:

  (A) BLOQUEIO POR IP. Do IP residencial responde 200, do datacenter do Actions
      responde 403. Ai o problema e de onde a gente bate, e a saida e reduzir a
      pressao ou aceitar a perda -- mexer em header nao resolve.

  (B) MUDOU O CONTRATO. Responde 403 aqui tambem, e algum cabecalho novo passou
      a ser obrigatorio (Origin, Referer, token). Ai a saida e mandar o que
      falta, e o teste ja diz QUAL combinacao volta a funcionar.

Roda quatro variacoes de cabecalho no seu IP. Se alguma passar aqui e o ciclo
seguir dando 403, e (A). Se todas derem 403 aqui, e (B) -- e a que passar (se
alguma passar) e a correcao.

Rode com o robo parado.
"""
import time

import requests

from scrapers.solides import TAKE, TIMEOUT, UA, URL_API

PORTAL = "https://vagas.solides.com.br"

VARIACOES = {
    "como o scraper manda hoje": {
        "User-Agent": UA,
        "Accept": "application/json",
    },
    "+ Origin e Referer do portal": {
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": PORTAL,
        "Referer": f"{PORTAL}/",
    },
    "cabecalho de navegador completo": {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": PORTAL,
        "Referer": f"{PORTAL}/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    },
    "sem User-Agent nenhum": {
        "Accept": "application/json",
    },
}

print(f"{'variacao':34} {'status':>7}  {'count':>7}")
print("-" * 54)
resultados = {}
for nome, cabecalhos in VARIACOES.items():
    try:
        r = requests.get(
            URL_API,
            params={"title": "analista de dados", "take": TAKE, "page": 1},
            timeout=TIMEOUT,
            headers=cabecalhos,
        )
        try:
            conta = ((r.json() or {}).get("data") or {}).get("count")
        except ValueError:
            conta = "(nao-JSON)"
        print(f"{nome:34} {r.status_code:>7}  {str(conta):>7}")
        resultados[nome] = (r.status_code, conta)
    except Exception as erro:
        print(f"{nome:34}    ERRO  {type(erro).__name__}")
        resultados[nome] = (None, None)
    time.sleep(2)

print("-" * 54)
passou = [n for n, (s, c) in resultados.items() if s == 200 and c]
proibido = [n for n, (s, _) in resultados.items() if s == 403]

if passou and "como o scraper manda hoje" in passou:
    print("=> (A) BLOQUEIO POR IP. Do seu IP o scraper funciona SEM mudar nada,")
    print("   entao o 403 do ciclo veio de onde ele roda, nao do que ele manda.")
    print("   Mexer em cabecalho nao resolve. As saidas reais sao reduzir a")
    print("   pressao sobre a API ou aceitar a perda da fonte no Actions.")
elif passou:
    print(f"=> (B) MUDOU O CONTRATO, e a correcao e conhecida: {passou[0]!r}")
    print("   passou e o cabecalho de hoje nao. Ha o que consertar no scraper.")
elif proibido:
    print("=> 403 em TODAS as variacoes, inclusive daqui. A API fechou de vez")
    print("   pra requisicao sem navegador, ou exige token. Nao inventar header")
    print("   novo no chute: a sondagem certa e abrir o portal no navegador e")
    print("   olhar a requisicao real que ele faz (aba Network).")
else:
    print("=> Nem 200 nem 403. Ler a coluna de status antes de concluir.")
