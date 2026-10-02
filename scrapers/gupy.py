import json
import re
import time
from urllib.parse import quote

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

# A API do portal (employability-portal.gupy.io/api/v1/jobs) MORREU.
#
# MEDIDO (2026-10-02): 404 em todo termo, 404 sem parametro nenhum e 404 na
# raiz /api/v1/. Nao e parametro errado nem bloqueio — a rota saiu do ar. A
# Gupy trouxe ZERO vaga em tres ciclos seguidos, e isso foi descoberto por
# acaso, lendo log por outro motivo. (O alerta de fonte morta de d664da2
# nasceu exatamente dessa falha.)
#
# Os dados agora vem embutidos no HTML da propria pagina de busca, no dialeto
# antigo do Next (__NEXT_DATA__, um JSON unico), em
# props.pageProps.initialJobList. Nao e o mesmo dialeto da Solides, que usa
# RSC em pedacos (self.__next_f.push) — ali foi preciso remontar o payload,
# aqui e um json.loads e pronto.
#
# O QUE NAO MUDOU: montar_job, montar_local, montar_modalidade, o Job, o
# filtro, a pontuacao, a deduplicacao, o formato do log e os testes de
# tests/test_gupy_api.py. Trocou SO a camada de busca — e continua sem
# navegador, com requests, como era.
#
# MEDIDO sobre a paginacao, com o criterio escrito antes do resultado ("o
# offset tem que andar E o primeiro titulo tem que mudar"):
#
#     ?page=2       -> offset 12, primeiro titulo diferente.  PAGINOU.
#     ?offset=12    -> offset 0, primeiro titulo igual.       NAO PAGINOU.
#     /page=2       -> 200 com pagination vazia e 0 vaga.     NAO PAGINOU.
#
# Os tres respondem 200. Se o criterio fosse "status 200", eu teria escolhido
# o ?offset= e a Gupy leria a pagina 1 oito vezes por termo, achando que
# paginava. E por isso que a guarda de offset abaixo existe.
#
# MEDIDO sobre o alcance. O portal declara total=100 tanto pra "analista de
# dados" quanto pra "analista" — numero identico pra termo estreito e pra termo
# largo e teto declarado, nao total. A API velha dizia 252 pro primeiro.
#
# Eu tratei isso como perda de alcance antes de medir a ORDEM da lista, e
# estava exagerando. A ordem e por recencia, medido pagina por pagina:
#
#     pagina 1 (offset 0)  -> 2026-10-01 .. 2026-09-29
#     pagina 2 (offset 12) -> 2026-09-29 .. 2026-09-29
#     pagina 5 (offset 48) -> 2026-09-24 .. 2026-09-23
#     pagina 9 (offset 96) -> 2026-09-16 .. 2026-09-15
#
# As ~100 mais recentes de "analista de dados" cobrem 16 DIAS. Com
# DIAS_PARA_PARAR = 30 e ciclo de 3h, nada dentro da janela fica de fora em
# regime: quando o termo volta no rodizio, o que ele precisa ver sao os
# ultimos dias, nao os ultimos 252 anuncios. O teto custaria algo so numa
# partida a frio, com banco vazio.
#
# Curiosidade medida que vale guardar: declarando total=100, o portal SERVIU
# 108 itens (9 paginas cheias de 12). O total declarado nao e exato — mais um
# motivo pra guarda de offset existir em vez de confiar na aritmetica dele.
URL_PORTAL = "https://portal.gupy.io/job-search/term="

# Quantas vagas o portal manda por pagina. E ELE quem decide (vem em
# pagination.limit); isto e so o palpite inicial pro caso de a resposta nao
# declarar.
POR_PAGINA_PADRAO = 12

# Teto de vagas por termo. Hoje o portal corta antes (100), entao este numero
# nao morde — fica porque e escolha do scraper e nao da fonte, e se o portal
# voltar a servir 252 ele e que manda.
MAX_VAGAS_POR_TERMO = 300

TIMEOUT = 30
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Busca POSICIONAL da tag: nao supor ordem de atributo. Supor
# '<script id="__NEXT_DATA__" type="application/json">' na ordem que eu
# imaginei foi o que fez a primeira sondagem desta reconstrucao nao achar
# nada numa pagina que tinha o dado.
_ABERTURA_NEXT_DATA = re.compile(r"<script[^>]*__NEXT_DATA__[^>]*>", re.IGNORECASE)


def url_da_busca(termo: str, pagina: int) -> str:
    """quote() e nao quote_plus(): aqui o termo vai no CAMINHO da URL
    ("/job-search/term=analista%20de%20dados"), nao na query string, e "+"
    no caminho e um "+" literal, nao um espaco."""
    base = f"{URL_PORTAL}{quote(termo)}"
    return base if pagina <= 1 else f"{base}?page={pagina}"


def extrair_next_data(html: str) -> dict | None:
    """O JSON do __NEXT_DATA__. None quando a pagina nao tem (ou nao e JSON)."""
    abertura = _ABERTURA_NEXT_DATA.search(html)
    if not abertura:
        return None
    fim = html.find("</script>", abertura.end())
    if fim == -1:
        return None
    try:
        return json.loads(html[abertura.end():fim])
    except ValueError:
        return None


def extrair_lista(html: str) -> tuple[dict, list] | None:
    """(pagination, data) de props.pageProps.initialJobList.

    Caminho CONHECIDO, de proposito, em vez de "a maior lista de dicionarios
    da pagina": essa heuristica, na sondagem, escolheu props.pageProps.toggles
    (569 feature flags) em vez das 12 vagas. Heuristica acha sempre alguma
    coisa, e quando acha a coisa errada ninguem percebe.

    None quando o formato mudou — e ai GRITA, porque o jeito silencioso de
    morrer e exatamente o que custou tres ciclos desta fonte.
    """
    dados = extrair_next_data(html)
    if dados is None:
        logger.error(
            "[Gupy] __NEXT_DATA__ não encontrado na página de busca. O formato "
            "da página mudou — nenhuma vaga vai sair daqui enquanto isso durar."
        )
        return None

    bloco = ((dados.get("props") or {}).get("pageProps") or {}).get("initialJobList")
    if not isinstance(bloco, dict):
        logger.error(
            "[Gupy] props.pageProps.initialJobList não existe mais no __NEXT_DATA__. "
            "A página carrega, o JSON está lá, e a lista de vagas mudou de lugar."
        )
        return None

    return bloco.get("pagination") or {}, bloco.get("data") or []


# workplaceType da API -> vocabulario que o filtro ja usa (ver
# _FLAGS_REMOTO e as regras de cidade em core/job.py).
_MODALIDADE = {
    "on-site": "Presencial",
    "onsite": "Presencial",
    "hybrid": "Híbrido",
    "remote": "Remoto",
}


def montar_local(vaga: dict) -> str:
    """Monta o campo `local` a partir de city/state.

    A API devolve o estado por EXTENSO ("São Paulo", "Ceará"), nao a sigla.
    Isso funciona porque a guarda de UF passou a ler estado por extenso em
    5e91895 -- antes desse commit, "Campina Grande, Paraná" passaria como se
    fosse a Campina Grande da Paraiba. Os testes cobrem exatamente esse caso.
    """
    cidade = (vaga.get("city") or "").strip()
    estado = (vaga.get("state") or "").strip()
    if cidade and estado:
        return f"{cidade}, {estado}"
    return cidade or estado or "Não informado"


def montar_modalidade(vaga: dict) -> str:
    """Traduz workplaceType. isRemoteWork entra como reforco: sao dois campos
    independentes na resposta, e vaga remota as vezes chega com um so."""
    bruto = (vaga.get("workplaceType") or "").strip().lower()
    if bruto in _MODALIDADE:
        return _MODALIDADE[bruto]
    if vaga.get("isRemoteWork") is True:
        return "Remoto"
    return ""


def montar_job(vaga: dict) -> Job | None:
    """Converte um item da API num Job. None quando falta o essencial.

    Funcao pura de proposito: e o que da pra testar sem rede, e onde mora
    todo o risco da troca (mapear campo errado passa despercebido).
    """
    titulo = (vaga.get("name") or "").strip()
    link = (vaga.get("jobUrl") or "").strip()
    if not titulo or not link:
        return None

    # publishedDate vem como "2026-08-28T21:28:28.868Z". Job.publicacao_antiga
    # e publicado_em_legivel esperam a data ISO pura (ver core/job.py).
    publicado = (vaga.get("publishedDate") or "")[:10]

    return Job(
        titulo=titulo,
        empresa=(vaga.get("careerPageName") or "Não informado").strip(),
        local=montar_local(vaga),
        link=link,
        site="Gupy",
        publicado_em=publicado,
        modalidade=montar_modalidade(vaga),
    )


class GupyScraper(BaseScraper):
    """Busca vagas no portal da Gupy, lendo o __NEXT_DATA__ da pagina."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))
        logger.info(f"[Gupy] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Gupy] Buscando: {termo}")
        vagas: list[Job] = []
        pagina = 1
        total = None
        por_pagina = POR_PAGINA_PADRAO

        while True:
            url = url_da_busca(termo, pagina)
            try:
                resposta = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
            except Exception as erro:
                logger.error(f"[Gupy] Erro ao buscar '{termo}' (página {pagina}): {erro}")
                break

            if resposta.status_code != 200:
                logger.warning(
                    f"[Gupy] Status {resposta.status_code} em '{termo}' (página {pagina}) "
                    "— resposta inesperada do portal, não é busca vazia."
                )
                break

            extraido = extrair_lista(resposta.text)
            if extraido is None:
                break
            paginacao, lote = extraido

            if total is None:
                total = paginacao.get("total") or 0
                if not total:
                    logger.info(f"[Gupy] 0 resultados reais para '{termo}'.")
                    break
                por_pagina = paginacao.get("limit") or POR_PAGINA_PADRAO

            # A guarda do ?offset=: ele responde 200, devolve 12 vagas e deixa
            # o offset em 0 — a pagina 1 de novo, com cara de pagina 2. Sem
            # conferir isso, o scraper leria a mesma pagina ate bater o teto e
            # nada no log diria que havia algo errado.
            offset_declarado = paginacao.get("offset")
            offset_esperado = (pagina - 1) * por_pagina
            if offset_declarado is not None and offset_declarado != offset_esperado:
                logger.warning(
                    f"[Gupy] '{termo}': pedi a página {pagina} (offset {offset_esperado}) "
                    f"e o portal devolveu offset {offset_declarado}. A paginação mudou de "
                    "forma; paro aqui pra não reler a mesma página como se fosse nova."
                )
                break

            if not lote:
                break

            for item in lote:
                job = montar_job(item)
                if job is not None:
                    vagas.append(job)

            lidas = pagina * por_pagina
            if lidas >= total or lidas >= MAX_VAGAS_POR_TERMO:
                break
            pagina += 1
            time.sleep(1)

        if total and total > MAX_VAGAS_POR_TERMO:
            logger.info(
                f"[Gupy] '{termo}': {total} vagas no total, lidas as {MAX_VAGAS_POR_TERMO} "
                "mais recentes (teto do scraper, não fim dos resultados)."
            )
        return vagas
