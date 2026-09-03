"""A Senior esta ha 15 dias no ar e nunca trouxe UMA vaga. No ciclo de 03/09
02:43 ela buscou e devolveu 1847 vagas brutas -- e ZERO passou no filtro.

POR QUE ISSO NAO E VEREDITO AINDA: 1847 vagas brutas e muita coisa. Se a fonte
tem volume, o zero pode ter duas causas MUITO diferentes:

  (A) A Senior nao tem vaga de Dados/BI que sirva -- as 1847 sao de outras
      areas, ou fora das cidades aceitas. Ai a fonte esta funcionando e o
      veredito e "nao rende", que e criterio de remocao pelo seu proprio
      criterio escrito.

  (B) O mapeamento esta errado -- titulo, local ou modalidade vindo torto do
      JSON, e ai VAGA BOA esta sendo rejeitada em silencio. Ai a fonte esta
      quebrada e remover seria jogar fora o que nunca funcionou de verdade.

Distinguir e barato: basta olhar o que a API devolve, cru, e passar pelo filtro
de verdade mostrando o motivo de cada rejeicao.

Rode com o robo parado.
"""
from collections import Counter

from core.perfis import PERFIL_BR
from scrapers.senior import SeniorScraper, montar_job

TERMOS = ["analista de dados", "power bi", "business intelligence"]

scraper = SeniorScraper(termos_busca=TERMOS)
for termo in TERMOS:
    print(f"\n{'=' * 70}\nTERMO: {termo}\n{'=' * 70}")
    try:
        dados = scraper._consultar(termo, 0)
    except Exception as erro:
        print(f"  ERRO na API: {type(erro).__name__}: {erro}")
        continue

    itens = dados.get("contents") or []
    print(f"  a API devolveu {dados.get('totalPages')} pagina(s), "
          f"{len(itens)} item(ns) nesta primeira\n")

    if not itens:
        continue

    print("  COMO A API ENTREGA (5 primeiros, campos crus):")
    for item in itens[:5]:
        vaga = (item or {}).get("vacancy") or {}
        print(f"    titulo={vaga.get('title')!r}")
        print(f"      localization={vaga.get('localization')!r}")
        print(f"      jobModel={vaga.get('jobModel')!r}")

    print("\n  COMO O SCRAPER MONTA (5 primeiros):")
    for item in itens[:5]:
        job = montar_job(item)
        if job is None:
            print("    (descartada em montar_job: sem id, sem titulo ou expirada)")
            continue
        print(f"    {job.titulo[:44]:44} | {job.local[:26]:26} | {job.modalidade}")

    montadas = [j for j in (montar_job(i) for i in itens) if j is not None]
    aprovadas = [j for j in montadas if j.combina_com(PERFIL_BR.regras)]
    print(f"\n  {len(itens)} brutas -> {len(montadas)} montadas -> "
          f"{len(aprovadas)} aprovadas pelo filtro")

    if montadas and not aprovadas:
        locais = Counter(j.local for j in montadas)
        print("\n  LOCAIS que apareceram (e o filtro rejeitou):")
        for local, n in locais.most_common(8):
            print(f"    {n:3}x  {local!r}")
        print("\n  TITULOS (amostra), pra ver se ha vaga de Dados aqui:")
        for j in montadas[:10]:
            print(f"    · {j.titulo}")

print(f"\n{'=' * 70}")
print("COMO LER:")
print("  · Se os LOCAIS vierem vazios/estranhos ('', 'None', so o pais) -> (B),")
print("    mapeamento quebrado: vaga boa sendo rejeitada por local ilegivel.")
print("  · Se os TITULOS nao tiverem nada de Dados/BI -> (A), a fonte nao tem")
print("    o que a gente procura, e o veredito de remocao esta maduro.")
print("  · Se houver titulo de Dados EM cidade aceita e mesmo assim 0 aprovada")
print("    -> (B) tambem, e o problema esta no filtro, nao na fonte.")
