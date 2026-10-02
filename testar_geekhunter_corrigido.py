"""Verificacao de rede da GeekHunter DEPOIS do conserto do card.

Imprime TODOS os campos de cada vaga — inclusive local, modalidade e link.
Nao e detalhe: a sonda da Solides imprimia titulo/local/data e nao o link,
e por isso o link ficou quebrado 24 dias sem ninguem ver. Sonda que nao
imprime o campo nao prova o campo.

Imprime tambem as linhas cruas do container, pra virarem teste com texto
real em vez de fixture inventada.
"""
import sys

from playwright.sync_api import sync_playwright

from core.perfis import PERFIL_BR
from scrapers.geekhunter import (
    GeekHunterScraper,
    container_do_card,
    extrair_campos,
    linhas_do_texto,
    _SELETOR_VAGA,
)

TERMO = sys.argv[1] if len(sys.argv) > 1 else "analista de dados"

print(f"=== 1) LINHAS CRUAS DO CONTAINER — '{TERMO}' pagina 1 ===")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(
        f"https://www.geekhunter.com/pt/vagas?searchTerm={TERMO.replace(' ', '+')}&page=1",
        timeout=60000,
    )
    page.wait_for_selector(_SELETOR_VAGA, timeout=15000)
    page.wait_for_timeout(2000)
    for i, card in enumerate(page.query_selector_all(_SELETOR_VAGA), 1):
        container = container_do_card(card)
        onde = "container" if container is not None else "SEM CONTAINER (caiu pra ancora)"
        linhas = linhas_do_texto((container or card).inner_text())
        print(f"\nCARD {i} [{onde}]")
        print(f"  linhas = {linhas!r}")
        titulo, local, modalidade = extrair_campos(linhas)
        print(f"  -> titulo={titulo!r} local={local!r} modalidade={modalidade!r}")
    browser.close()

print(f"\n\n=== 2) O SCRAPER DE VERDADE — '{TERMO}' ===")
vagas = GeekHunterScraper([TERMO]).buscar_vagas()
regras = PERFIL_BR.regras
aprovadas = 0
for v in vagas:
    ok = v.combina_com(regras)
    aprovadas += ok
    print(f"\n[{'APROVADA' if ok else 'reprovada'}] {v.titulo}")
    print(f"  empresa     : {v.empresa}")
    print(f"  local       : {v.local!r}")
    print(f"  modalidade  : {v.modalidade!r}")
    print(f"  publicado_em: {v.publicado_em!r}")
    print(f"  link        : {v.link}")
    if ok:
        print(f"  nota        : {v.pontuar_relevancia(regras)}")

print(f"\n=== {len(vagas)} bruta(s), {aprovadas} aprovada(s) ===")
sem_local = sum(1 for v in vagas if v.local == "Não informado")
sem_modalidade = sum(1 for v in vagas if not v.modalidade)
print(f"sem local: {sem_local}/{len(vagas)} | sem modalidade: {sem_modalidade}/{len(vagas)}")
print("ANTES do conserto esses dois eram 21/21 e 21/21.")
