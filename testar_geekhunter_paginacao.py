"""Por que a pagina 2 da GeekHunter estoura o timeout.

NAO assume que &page=2 ainda e a paginacao do site. Pergunta tres coisas e
imprime a resposta crua de cada uma:
  1. quantas vagas o site DIZ ter pro termo (se ele diz);
  2. que controle de paginacao existe na pagina 1 (botao, link, numero);
  3. o que a URL com &page=2 devolve de verdade.
Imprime tambem as chamadas XHR/fetch, pra saber se existe um JSON por tras —
informacao pra decidir depois, nao pra trocar nada agora.
"""
import re
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from scrapers.geekhunter import _SELETOR_VAGA

TERMO = sys.argv[1] if len(sys.argv) > 1 else "analista de dados"
BASE = "https://www.geekhunter.com/pt/vagas?searchTerm=" + TERMO.replace(" ", "+")

RE_CONTROLE = re.compile(r"^\d+$|pr[oó]xim|next|carregar|ver mais|seguinte", re.IGNORECASE)


def abrir(page, url, rotulo):
    print(f"\n--- {rotulo}: {url}")
    page.goto(url, timeout=60000)
    try:
        page.wait_for_selector(_SELETOR_VAGA, timeout=15000)
        chegou = True
    except PlaywrightTimeoutError:
        chegou = False
    page.wait_for_timeout(3000)
    cards = page.query_selector_all(_SELETOR_VAGA)
    print(f"    seletor apareceu em 15s: {chegou} | cards: {len(cards)}")
    print(f"    URL final (redirecionou?): {page.url}")
    return cards


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    chamadas = []
    page.on("request", lambda r: chamadas.append((r.resource_type, r.method, r.url))
            if r.resource_type in ("xhr", "fetch") else None)

    cards1 = abrir(page, BASE + "&page=1", "PAGINA 1")
    corpo = page.inner_text("body")

    print("\n=== 1) O QUE O SITE DIZ SOBRE O TOTAL ===")
    achou = False
    for linha in corpo.split("\n"):
        linha = linha.strip()
        if re.search(r"\d+\s*(vaga|resultado|oportunidade)", linha, re.IGNORECASE):
            print(f"    {linha!r}")
            achou = True
    if not achou:
        print("    nenhuma linha com contagem de vagas.")

    print("\n=== 2) CONTROLES DE PAGINACAO NA PAGINA 1 ===")
    achou = False
    for el in page.query_selector_all("button, a"):
        try:
            texto = (el.inner_text() or "").strip()
        except Exception:
            continue
        if texto and RE_CONTROLE.match(texto) and len(texto) < 20:
            href = el.get_attribute("href")
            print(f"    <{el.evaluate('e => e.tagName')}> {texto!r} href={href!r} "
                  f"visivel={el.is_visible()}")
            achou = True
    if not achou:
        print("    nenhum botao/link de paginacao encontrado.")
    print(f"    fim do corpo da pagina (ultimas 300 letras):\n      {corpo[-300:]!r}")

    print("\n=== 3) A URL COM &page=2 ===")
    # Colher os href da pagina 1 ANTES de navegar: depois do goto os
    # ElementHandle morrem ("Execution context was destroyed") — foi o crash
    # da primeira rodada desta sonda, bug meu e nao do site.
    links1 = set()
    for c in cards1:
        try:
            links1.add(c.get_attribute("href"))
        except Exception:
            pass
    cards2 = abrir(page, BASE + "&page=2", "PAGINA 2")
    if cards2:
        print("    primeiros titulos da pagina 2:")
        for c in cards2[:3]:
            print(f"      {c.inner_text().strip()!r}")
        iguais = {c.get_attribute('href') for c in cards2} == links1
        print(f"    a pagina 2 e IGUAL a pagina 1? {iguais}")
    else:
        print("    zero card. Corpo da pagina (primeiras 400 letras):")
        print(f"      {page.inner_text('body')[:400]!r}")

    print("\n=== 4) CHAMADAS XHR/FETCH VISTAS ===")
    if not chamadas:
        print("    nenhuma. A listagem vem no HTML/RSC do servidor.")
    for tipo, metodo, url in chamadas[:25]:
        print(f"    {tipo:5} {metodo:4} {url[:160]}")

    browser.close()
