"""Confere, contra o portal DE VERDADE, o scraper reconstruido em 08/09.

Os testes automatizados rodam contra um HTML montado a partir de um trecho real
capturado do portal. Isso guarda a extracao, mas nao prova que a ROTA, o SLUG e
a paginacao continuam de pe hoje -- so a rede prova isso.

Este script roda o scraper de verdade em tres termos e mostra o funil inteiro.

Rode com o robo parado.
"""
from core.perfis import PERFIL_BR
from scrapers.solides import SolidesScraper, url_da_busca

TERMOS = ["analista de dados", "power bi", "inteligência de mercado"]

for termo in TERMOS:
    print(f"\n{'=' * 72}\n{termo}  ->  {url_da_busca(termo, 1)}\n{'=' * 72}")
    scraper = SolidesScraper([termo])
    vagas = scraper.buscar_vagas()
    aprovadas = [v for v in vagas if v.combina_com(PERFIL_BR.regras)]
    print(f"  {len(vagas)} vaga(s) montada(s) | {len(aprovadas)} passam no filtro")
    for job in vagas[:5]:
        print(f"    {job.titulo[:40]:40} | {job.local[:24]:24} | "
              f"{job.modalidade or '-':10} | {job.publicado_em}")
        # O LINK entra aqui porque em 08/09 esta verificacao imprimia TODOS
        # os campos menos ele -- e foi exatamente o link que quebrou, por
        # 24 dias. Conferir o que nao quebrou e facil; o truque e conferir
        # tudo.
        print(f"      {job.link}")
    if not vagas:
        print("    (nada — ver se o log acima gritou 'portal mudou' ou 'formato')")

print(f"\n{'=' * 72}")
print("O QUE CONFERIR:")
print("  · vagas montadas > 0 nos tres termos -> rota, slug e extracao de pe.")
print("  · local no formato 'Cidade - UF' e data em AAAA-MM-DD -> mapeamento ok.")
print("  · 'parou na pagina N' no log -> a parada por idade continua funcionando.")
print("  · TODO link no formato https://<empresa>.solides.jobs/vacancies/<id>.")
print("    Host truncado (https://empresa./...) e o bug de 08/09 voltando.")
print("  · zero em tudo COM erro no log -> o formato mudou de novo, e o log diz.")
print("  · zero em tudo SEM erro no log -> a rota mudou; conferir url acima no")
print("    navegador antes de mexer em codigo.")
