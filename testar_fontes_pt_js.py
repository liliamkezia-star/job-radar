"""sapo, randstad e michaelpage com navegador — o que faltava medir.

POR QUE COM PLAYWRIGHT. Nos tres, o HTML do servidor nao tem UM link de vaga:
sapo devolveu 263 KB e zero, e nos outros dois nem cheguei a extrair. Isso
significa que os cards sao montados por JavaScript. Sem navegador nao da pra
medir rendimento nenhum — e medir e a condicao pra entrar.

O QUE ELA MEDE, e as duas coisas pesam igual:

  1. RENDIMENTO: quantas vagas a pagina mostra e quantas passam em
     PERFIL_INTL.regras. Nao olhometro — o filtro de verdade.
  2. CUSTO: quanto tempo cada pagina leva. Hoje o LinkedIn come 19 dos 26
     minutos do ciclo; fonte de navegador soma a isso em TODA execucao, pra
     sempre. Rendimento alto com custo alto pode nao passar.

COMO ELA ACHA O LINK DA VAGA. Nao por chute: colhe (href, texto) de TODAS as
ancoras da pagina RENDERIZADA numa chamada de JS, troca digito por N e conta
a frequencia das formas. A forma da vaga e a que repete muito. Foi assim que
o /oferta/N/<slug> do itjobs apareceu, depois de eu ter chutado errado duas
vezes.

O QUE ELA NAO FAZ: nao clica em nada. Nem em banner de cookie. Se um banner
estiver tapando a pagina, ela diz isso e o numero fica sem medir — aceitar
termo de uso nao e decisao de sonda.
"""
import re
import time
from collections import Counter
from urllib.parse import urljoin, urlsplit

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from avaliar_fonte import caminho_permitido, extrair_jobpostings, regras_do_robots
from core.job import Job
from core.perfis import PERFIL_INTL

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# URLs candidatas. As de remoto sao CHUTE onde o site nao declara filtro —
# marcado como chute pra sonda imprimir o resultado em vez de eu assumir.
ALVOS = {
    "sapo": [
        "https://emprego.sapo.pt/offers?modelo=teletrabalho",          # filtro declarado pelo site
    ],
    "randstad": [
        "https://www.randstad.pt/empregos/",                            # listagem geral
        "https://www.randstad.pt/empregos/?q=analista%20de%20dados",    # CHUTE: termo
    ],
    "michaelpage": [
        "https://www.michaelpage.pt/jobs/",                             # listagem geral
        "https://www.michaelpage.pt/jobs/data-analyst",                 # CHUTE: termo no caminho
    ],
}

PISTAS = ("oferta", "offer", "emprego", "vaga", "job", "anuncio", "opportunit")

# O site pode ter filtro de remoto com OUTRA palavra. "remote" e o termo
# ingles; em Portugal aparece "teletrabalho", "trabalho remoto", "a
# distancia", "home office". Procurar so por "remote" e supor o vocabulario
# do site — entao a sonda procura o campo semantico inteiro, em ancora, em
# <option> de filtro e em <label> de caixa de selecao, e imprime a palavra
# que o site usa junto com a URL ou o valor que ela carrega.
VOCAB_REMOTO = r"teletrabalh|remot|dist[aâ]ncia|home.?office|h[ií]brid|hybrid"
_robots_lido = {}


def permitido(url: str) -> bool:
    p = urlsplit(url)
    raiz = f"{p.scheme}://{p.netloc}"
    if raiz not in _robots_lido:
        try:
            _robots_lido[raiz] = requests.get(f"{raiz}/robots.txt", timeout=20,
                                              headers={"User-Agent": UA}).text
        except Exception as e:
            print(f"    robots.txt ilegivel ({e}) — nao acesso.")
            return False
    ok = caminho_permitido(regras_do_robots(_robots_lido[raiz]), p.path or "/")
    if not ok:
        print(f"    robots.txt NAO permite {p.path} — nao acessei.")
    return ok


def ancoras_renderizadas(page) -> list[tuple[str, str]]:
    """(href, texto) de toda ancora da pagina DEPOIS do JavaScript."""
    return page.eval_on_selector_all(
        "a",
        "els => els.map(e => [e.getAttribute('href') || '', "
        "(e.innerText || '').replace(/\\s+/g,' ').trim().slice(0,140)])",
    )


def forma(caminho: str) -> str:
    f = re.sub(r"\d+", "N", caminho)
    return re.sub(r"/[^/]{25,}", "/<slug-longo>", f)


regras = PERFIL_INTL.regras
resumo = []

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True)
    for site, urls in ALVOS.items():
        print("=" * 72)
        print(f"{site.upper()}")
        print("=" * 72)
        for url in urls:
            print(f"\n--- {url}")
            if not permitido(url):
                continue
            pagina = navegador.new_page(user_agent=UA)
            comeco = time.monotonic()
            try:
                pagina.goto(url, timeout=60000)
                try:
                    pagina.wait_for_load_state("networkidle", timeout=20000)
                except PlaywrightTimeoutError:
                    print("    (networkidle nao chegou em 20s — segue com o que renderizou)")
                pagina.wait_for_timeout(3000)
                segundos = time.monotonic() - comeco

                ancoras = ancoras_renderizadas(pagina)
                host = urlsplit(url).netloc
                formas, exemplo, textos = Counter(), {}, {}
                for href, texto in ancoras:
                    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                        continue
                    pp = urlsplit(href)
                    if pp.netloc and host.split(".")[-2] not in pp.netloc:
                        continue
                    f = forma(pp.path or "/")
                    formas[f] += 1
                    exemplo.setdefault(f, href)
                    textos.setdefault(f, []).append(texto)

                print(f"    CUSTO: {segundos:.1f}s | {len(ancoras)} ancora(s) renderizada(s)")
                print(f"    formas mais repetidas:")
                for f, n in formas.most_common(8):
                    print(f"      {n:4}x {f[:52]:54} ex: {exemplo[f][:48]}")

                # Qual palavra ESTE site usa pra remoto, e onde ela mora?
                controles = pagina.eval_on_selector_all(
                    "a, option, label, button, input",
                    "els => els.map(e => [e.tagName, "
                    "(e.innerText || e.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim().slice(0,70), "
                    "e.getAttribute('href') || e.getAttribute('value') || ''])",
                )
                achados = []
                for tag, texto, valor in controles:
                    if re.search(VOCAB_REMOTO, f"{texto} {valor}", re.I):
                        achados.append((tag, texto, valor))
                vistos = set()
                unicos_ctrl = [c for c in achados
                               if not (c[1:] in vistos or vistos.add(c[1:]))]
                print(f"    CONTROLE DE REMOTO no site: {len(unicos_ctrl)} achado(s)")
                for tag, texto, valor in unicos_ctrl[:10]:
                    print(f"      <{tag.lower()}> {texto[:46]!r} -> {valor[:60]!r}")
                if not unicos_ctrl:
                    print("      nenhum. Ou o site nao filtra remoto, ou o filtro"
                          " so aparece depois de uma busca.")

                candidatas = [(n, f) for f, n in formas.items()
                              if n >= 4 and any(x in f.lower() for x in PISTAS)
                              and f.count("/") >= 2]
                if not candidatas:
                    corpo = pagina.inner_text("body")[:300].replace("\n", " ")
                    print("    NENHUMA forma de vaga, mesmo renderizado.")
                    print(f"    inicio do texto visivel: {corpo!r}")
                    if re.search(r"cookie|consent|aceitar|privacidade", corpo, re.I):
                        print("    <<< parece banner de cookie tapando a pagina. Nao cliquei:")
                        print("        aceitar termo nao e decisao de sonda. Numero fica sem medir.")
                    resumo.append((site, url, segundos, 0, 0))
                    continue

                n, f = max(candidatas)
                titulos = [t for t in textos[f] if len(t) >= 6]
                unicos = list(dict.fromkeys(titulos))
                print(f"    forma da vaga: {f!r} ({n}x) | {len(unicos)} titulo(s) com texto")
                for t in unicos[:6]:
                    print(f"      · {t[:80]}")

                aprovadas = []
                for t in unicos:
                    job = Job(titulo=t, empresa="?", local="Portugal",
                              link="https://x/y", site=site, publicado_em="",
                              modalidade="Remoto")
                    if job.combina_com(regras):
                        aprovadas.append((job.pontuar_relevancia(regras), t))
                com_remoto = [t for t in unicos if re.search(VOCAB_REMOTO, t, re.I)]
                print(f"    titulos que mencionam remoto/hibrido: {len(com_remoto)} "
                      f"de {len(unicos)}")
                print(f"    APROVADAS: {len(aprovadas)} de {len(unicos)}")
                for nota, t in sorted(aprovadas, reverse=True)[:8]:
                    print(f"      nota {nota}: {t[:78]}")
                resumo.append((site, url, segundos, len(unicos), len(aprovadas)))

                # JSON-LD na pagina da vaga — o que decidiu a favor do itjobs
                primeiro = urljoin(url, exemplo[f])
                if permitido(primeiro):
                    try:
                        det = requests.get(primeiro, timeout=25, headers={"User-Agent": UA})
                        jp = extrair_jobpostings(det.text)
                        print(f"    JSON-LD na pagina da vaga (sem navegador): {len(jp)} JobPosting")
                        if jp:
                            for campo in ("title", "datePosted", "validThrough",
                                          "jobLocationType", "hiringOrganization"):
                                if campo in jp[0]:
                                    print(f"      {campo:18} = {str(jp[0][campo])[:75]}")
                        else:
                            print("      (nenhum — ou o detalhe tambem e montado por JS)")
                    except Exception as e:
                        print(f"    (nao deu pra abrir a vaga: {e})")
            except Exception as e:
                print(f"    ERRO: {type(e).__name__}: {e}")
            finally:
                pagina.close()

    navegador.close()

print("\n" + "=" * 72)
print("RESUMO — rendimento contra custo")
print("=" * 72)
print(f"{'site':14} {'custo':>8} {'vagas':>7} {'aprov.':>7} {'taxa':>7}")
for site, url, seg, vistas, aprov in resumo:
    taxa = f"{100*aprov/vistas:.1f}%" if vistas else "—"
    print(f"{site:14} {seg:7.1f}s {vistas:7} {aprov:7} {taxa:>7}")
print()
print("Compare com o que ja existe: LinkedIn 8,5% | itjobs 3,8% (medido ontem,")
print("sem navegador) | Gupy 2,6% | Solides 1,1% | GeekHunter <1% | Senior 0,3%.")
print("E com o custo: o LinkedIn come 19 dos 26 minutos do ciclo hoje.")
