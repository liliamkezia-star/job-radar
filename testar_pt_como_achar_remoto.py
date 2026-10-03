"""Como encontrar vaga REMOTA nesses sites — estudo antes de descartar.

O erro que motiva este arquivo e meu: eu media a porta de entrada obvia e
concluia sobre o site. No net-empregos medi o FEED GERAL (1.000 vagas de
industria, transporte e restauracao) e dei o site por perdido — mas ele tem
filtro de "Teletrabalho" na interface e tem categorias. Busca filtrada nao e
o mesmo que canhao.

Tres tecnicas, nenhuma depende de eu imaginar a URL:

  A. SITEMAP. O site declara os sitemaps no robots.txt, e sitemap e lista de
     URLs que existem DE VERDADE. Procurar nele o vocabulario de remoto e de
     dados responde "que URL pedir" sem chute nenhum.

  B. O FORMULARIO. Pagina de busca declara os proprios campos: <select>,
     <input>, <option>. Ler o formulario diz exatamente como montar a query
     ("categoria=X&tipo=teletrabalho"), em vez de eu tentar parametro por
     parametro.

  C. O CORPO DA RESPOSTA, nao o nome dela. Nos sites de JavaScript, a lista
     de vagas vem por XHR. Julgar endpoint pelo NOME foi o que fez a
     avaliacao apontar previsao do tempo e login do SAPO como "nome sugere
     vagas" — e, antes disso, escolher 569 feature flags da Gupy em vez das
     12 vagas. Aqui a sonda le o CONTEUDO de cada resposta JSON e pontua pelo
     que tem dentro.
"""
import json
import re
import time
from collections import Counter
from urllib.parse import urljoin, urlsplit

import requests

from avaliar_fonte import caminho_permitido, regras_do_robots

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 25

VOCAB_REMOTO = r"teletrabalh|remot|dist[aâ]ncia|home.?office|h[ií]brid|hybrid"
VOCAB_DADOS = (r"\bdados\b|\bdata\b|\bbi\b|business.intelligence|power.?bi|"
               r"analytic|analista|analyst|informatic|informátic|tecnolog")

SITES = {
    "net-empregos": "https://www.net-empregos.com",
    "sapo":         "https://emprego.sapo.pt",
    "randstad":     "https://www.randstad.pt",
    "michaelpage":  "https://www.michaelpage.pt",
}

_robots = {}


def pegar(url: str, checar_robots: bool = True):
    p = urlsplit(url)
    raiz = f"{p.scheme}://{p.netloc}"
    if checar_robots:
        if raiz not in _robots:
            try:
                _robots[raiz] = requests.get(f"{raiz}/robots.txt", timeout=TIMEOUT,
                                             headers={"User-Agent": UA}).text
            except Exception as e:
                print(f"      robots.txt ilegivel ({e}) — nao acesso.")
                return None
        if not caminho_permitido(regras_do_robots(_robots[raiz]), p.path or "/"):
            print(f"      robots.txt NAO permite {p.path} — nao acessei.")
            return None
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
        return r
    except Exception as e:
        print(f"      ERRO: {e}")
        return None


print("#" * 72)
print("# A) SITEMAP: que URLs de remoto o site DECLARA que existem")
print("#" * 72)
for site, raiz in SITES.items():
    print(f"\n=== {site}")
    r = pegar(f"{raiz}/robots.txt", checar_robots=False)
    if not r:
        continue
    mapas = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
    print(f"    sitemaps declarados no robots.txt: {len(mapas)}")
    for m in mapas[:6]:
        print(f"      {m}")
    urls = []
    for mapa in mapas[:4]:
        rm = pegar(mapa)
        if not rm or rm.status_code != 200:
            print(f"      {mapa} -> status {rm.status_code if rm else 'erro'}")
            continue
        achadas = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", rm.text)
        # sitemap index: os <loc> apontam pra outros sitemaps
        filhos = [u for u in achadas if u.endswith((".xml", ".xml.gz"))]
        if filhos and len(filhos) == len(achadas):
            print(f"      {mapa} -> indice com {len(filhos)} sitemap(s); abrindo 3")
            for f in filhos[:3]:
                rf = pegar(f)
                if rf and rf.status_code == 200:
                    urls += re.findall(r"<loc>\s*([^<]+?)\s*</loc>", rf.text)
        else:
            urls += achadas
        print(f"      {mapa} -> {len(achadas)} <loc>")
    urls = list(dict.fromkeys(urls))
    print(f"    TOTAL de URLs coletadas: {len(urls)}")
    if not urls:
        continue
    rem = [u for u in urls if re.search(VOCAB_REMOTO, u, re.I)]
    dad = [u for u in urls if re.search(VOCAB_DADOS, u, re.I)]
    print(f"    URLs com vocabulario de REMOTO: {len(rem)}")
    for u in rem[:8]:
        print(f"      · {u[:100]}")
    print(f"    URLs com vocabulario de DADOS/TI: {len(dad)}")
    for u in dad[:8]:
        print(f"      · {u[:100]}")

print("\n" + "#" * 72)
print("# B) O FORMULARIO DE BUSCA: como montar a query, declarado pelo site")
print("#" * 72)
FORMULARIOS = {
    "net-empregos": "https://www.net-empregos.com/pesquisa-empregos.asp",
    "sapo":         "https://emprego.sapo.pt/offers",
}
for site, url in FORMULARIOS.items():
    print(f"\n=== {site}: {url}")
    r = pegar(url)
    if not r or r.status_code != 200:
        continue
    html = r.text
    for i, forma in enumerate(re.findall(r"<form\b[^>]*>.*?</form>", html, re.S | re.I)[:4], 1):
        acao = re.search(r'action="([^"]*)"', forma, re.I)
        metodo = re.search(r'method="([^"]*)"', forma, re.I)
        print(f"\n    --- formulario {i}: action={acao.group(1) if acao else '(mesma pagina)'!r} "
              f"method={metodo.group(1).upper() if metodo else 'GET'}")
        campos = re.findall(r'<(input|select|textarea)\b([^>]*)>', forma, re.I)
        for tag, attrs in campos[:18]:
            nome = re.search(r'name="([^"]*)"', attrs, re.I)
            tipo = re.search(r'type="([^"]*)"', attrs, re.I)
            valor = re.search(r'value="([^"]*)"', attrs, re.I)
            if nome:
                print(f"        <{tag.lower():6}> name={nome.group(1):24} "
                      f"type={(tipo.group(1) if tipo else '-'):10} "
                      f"value={(valor.group(1)[:28] if valor else '-')!r}")
        # os <option> que falam de remoto ou de informatica
        for sel in re.findall(r"<select\b([^>]*)>(.*?)</select>", forma, re.S | re.I):
            nome = re.search(r'name="([^"]*)"', sel[0], re.I)
            opcoes = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', sel[1], re.I)
            quentes = [(v, t.strip()) for v, t in opcoes
                       if re.search(VOCAB_REMOTO + "|" + VOCAB_DADOS, f"{v} {t}", re.I)]
            if quentes:
                print(f"        OPCOES RELEVANTES de name={nome.group(1) if nome else '?'!r}:")
                for v, t in quentes[:12]:
                    print(f"            value={v!r:22} -> {t[:50]!r}")

print("\n" + "#" * 72)
print("# C) O CORPO DA RESPOSTA: achar a lista de vagas pelo CONTEUDO")
print("#" * 72)
print("Pontua cada resposta JSON pelo que tem DENTRO (lista de objetos com")
print("cara de vaga), nao pelo nome do endpoint. Nome foi o que fez a")
print("avaliacao apontar previsao do tempo do SAPO como 'sugere vagas'.")

CHAVES_DE_VAGA = ("title", "jobtitle", "titulo", "name", "company", "empresa",
                  "location", "local", "localidade", "city", "cidade", "url",
                  "link", "slug", "salary", "salario", "date", "data", "remote",
                  "teletrabalho", "modelo", "workplace")

ALVOS_JS = {
    "sapo":        "https://emprego.sapo.pt/offers?modelo=teletrabalho",
    "randstad":    "https://www.randstad.pt/empregos/",
    "michaelpage": "https://www.michaelpage.pt/jobs/",
}


def pontuar_corpo(texto: str) -> tuple[int, str]:
    """Pontua pela ESTRUTURA: lista de dicionarios cujas chaves parecem vaga."""
    try:
        dados = json.loads(texto)
    except Exception:
        return 0, "nao e JSON valido"
    melhor, onde = 0, ""

    def visitar(no, caminho=""):
        nonlocal melhor, onde
        if isinstance(no, list):
            dicts = [x for x in no if isinstance(x, dict)]
            if len(dicts) >= 3:
                chaves = set()
                for d in dicts[:5]:
                    chaves |= {k.lower() for k in d.keys()}
                batem = sum(1 for c in CHAVES_DE_VAGA if any(c in k for k in chaves))
                pontos = len(dicts) * batem
                if pontos > melhor:
                    melhor, onde = pontos, f"{caminho or '(raiz)'}: {len(dicts)} objetos, {batem} chave(s) de vaga"
            for i, x in enumerate(no[:3]):
                visitar(x, f"{caminho}[{i}]")
        elif isinstance(no, dict):
            for k, v in no.items():
                visitar(v, f"{caminho}.{k}" if caminho else k)

    visitar(dados)
    return melhor, onde


try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("\n(playwright nao instalado — bloco C nao roda)")
    raise SystemExit

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    for site, url in ALVOS_JS.items():
        print(f"\n=== {site}: {url}")
        pag = nav.new_page(user_agent=UA)
        corpos = []

        def ao_responder(resp, corpos=corpos):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                tipo = (resp.headers.get("content-type") or "").lower()
                if "json" not in tipo:
                    return
                corpos.append((resp.url, resp.text()))
            except Exception:
                pass

        pag.on("response", ao_responder)
        comeco = time.monotonic()
        try:
            pag.goto(url, timeout=60000)
            try:
                pag.wait_for_load_state("networkidle", timeout=20000)
            except PWTimeout:
                pass
            pag.wait_for_timeout(4000)
            # rolar pra baixo: lista por scroll so pede os dados depois
            for _ in range(3):
                pag.mouse.wheel(0, 2500)
                pag.wait_for_timeout(1200)
        except Exception as e:
            print(f"    ERRO ao abrir: {type(e).__name__}: {e}")
        print(f"    tempo: {time.monotonic() - comeco:.1f}s | "
              f"respostas JSON capturadas: {len(corpos)}")

        pontuadas = []
        for endereco, texto in corpos:
            pontos, onde = pontuar_corpo(texto)
            if pontos > 0:
                pontuadas.append((pontos, endereco, onde, len(texto)))
        pontuadas.sort(reverse=True)
        if not pontuadas:
            print("    NENHUMA resposta JSON com lista de objetos com cara de vaga.")
            print("    (ou a lista vem dentro do HTML, ou vem por outro transporte)")
        for pontos, endereco, onde, tam in pontuadas[:5]:
            print(f"    [{pontos:5}] {tam:>7} bytes  {endereco[:88]}")
            print(f"            {onde}")
        # o vocabulario de remoto aparece em algum corpo?
        for endereco, texto in corpos:
            if re.search(VOCAB_REMOTO, texto, re.I):
                achados = Counter(m.lower() for m in re.findall(VOCAB_REMOTO, texto, re.I))
                print(f"    vocabulario de remoto DENTRO de {endereco[:70]}: "
                      f"{dict(achados.most_common(5))}")
                break
        pag.close()
    nav.close()
