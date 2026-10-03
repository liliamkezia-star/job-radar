
import json
import re
import time
from datetime import date
from urllib.parse import urljoin, urlsplit

import requests

from core.job import Job, _normalizar
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

# itjobs.pt — o unico de cinco sites portugueses que passou na medicao.
#
# MEDIDO em 03/10/2026, nos cinco que a usuaria pediu pra avaliar:
#
#   itjobs.pt      ~630 vagas remotas, 36 paginas, 2 aprovadas de 52 = 3,8%
#   emprego.sapo   9 vagas alcancaveis (page=2 repete a 1), 0 aprovada
#   michaelpage    8 a 30 por rota, termo+remoto nao combinam, 0 aprovada
#   randstad       30 vagas (page=2 repete a 1), 0 aprovada em 75 titulos
#   net-empregos   feed de 1.000 sem filtro, 15 de tecnologia, ~0
#
# Os 3,8% ficam acima da Gupy (2,6%) e da Solides (1,1%). Os outros quatro
# falham pelo mesmo motivo: sao boards generalistas e de BPO (apoio ao
# cliente, industria, bancario). O nicho desta busca e servido pelo site
# ESPECIFICO de TI — isso prediz a proxima fonte melhor que qualquer lista.
#
# POR QUE ESTA FONTE E DIFERENTE DAS OUTRAS DO PROJETO: a pagina da VAGA
# publica schema.org/JobPosting. Contrato, nao marcacao. A empresa publica
# isso de proposito pro Google indexar, entao nao muda quando o layout muda —
# e layout mudando em silencio foi o que matou a Solides, a Gupy e a
# GeekHunter neste mesmo projeto. Alem disso o JSON-LD traz dois campos que
# NENHUMA fonte atual tem:
#
#   datePosted    — a base inteira tem data em 57,9% das vagas; a GeekHunter
#                   em 0%. Aqui vem sempre.
#   validThrough  — quando o anuncio expira. Hoje isso e adivinhado por
#                   "mais de 30 dias, pode estar preenchida". Aqui o proprio
#                   anuncio diz, e vaga expirada nem e devolvida.
#
# DESENHO, e o custo de cada parte: a listagem e barata (66 KB, 18 vagas,
# sem navegador) e o detalhe custa uma requisicao por vaga. Entao varre a
# listagem toda pegando titulo e link, cruza o titulo com os termos de busca,
# e abre o detalhe SO do que casou. Nada de 630 requisicoes de detalhe.
#
# POR QUE NAO CORTO A PAGINACAO em 3 ou 5 paginas como em outras fontes: eu
# NAO SEI a ordem da listagem. Nao foi medida. Cortar sem saber a ordem
# perderia vaga de forma sistematica e invisivel — exatamente o tipo de
# silencio que este projeto ja pagou caro. A listagem inteira custa ~36
# requisicoes leves uma vez por dia; quando alguem medir a ordem, dai da pra
# cortar com fundamento.
#
# ARMADILHA MEDIDA: 'Digital Marketing Specialist' aparece nas paginas 1, 2 e
# 3 da rota de remoto — e anuncio fixo. E o JSON-LD dele NAO tem
# jobLocationType, enquanto o da vaga real tem TELECOMMUTE. Ou seja: estar na
# rota /emprego/remote NAO prova que a vaga e remota. Quem prova e o dado
# estruturado. Por isso a modalidade sai do JSON-LD e nao da rota, e por isso
# nao existe aqui nenhuma heuristica de "apareceu duas vezes, e anuncio":
# lista paginada que recebe vaga nova no meio da varredura repete item no
# limite de pagina, e a heuristica descartaria vaga boa. Uma autoridade so.
URL_REMOTO = "https://www.itjobs.pt/emprego/remote"

# Medido: 18 por pagina, e a propria pagina declara ?page=35 e ?page=36.
POR_PAGINA = 18
MAX_PAGINAS = 40

# Teto de requisicoes de detalhe por ciclo. Nao e limite do site — e escolha,
# pra uma mudanca no site (ou nos termos) nao transformar esta fonte em
# centenas de requisicoes sem ninguem perceber. Ao bater, AVISA.
MAX_DETALHES_POR_CICLO = 80

TIMEOUT = 25
PAUSA_ENTRE_DETALHES = 1
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# A forma do link de vaga, descoberta contando a frequencia das formas de
# href na pagina (nao chutada: eu chutei '/emprego/\d+' e '/offers/' antes, e
# os dois deram zero).
_ANCORA_DE_VAGA = re.compile(r'href="([^"#?]*/oferta/\d+/[^"#?]+)"([^>]*>[^<]{0,200})')
_PAGINA_NO_LINK = re.compile(r"[?&]page=(\d+)")
_SCRIPT_JSONLD = re.compile(
    r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I
)


def url_da_pagina(pagina: int) -> str:
    return URL_REMOTO if pagina <= 1 else f"{URL_REMOTO}?page={pagina}"


def titulo_do_slug(caminho: str) -> str:
    """O slug E o titulo em kebab-case (/oferta/517552/data-analyst). Serve de
    reserva quando a ancora embrulha outro elemento em vez de ter o texto
    direto. Reserva declarada, nao adivinhacao de marcacao."""
    pedaco = (caminho or "").rstrip("/").rsplit("/", 1)[-1]
    return pedaco.replace("-", " ").strip()


def vagas_da_listagem(html: str, base: str = URL_REMOTO) -> list[tuple[str, str]]:
    """(titulo, link) de cada vaga da pagina de listagem."""
    achadas: dict[str, str] = {}
    for caminho, resto in _ANCORA_DE_VAGA.findall(html or ""):
        link = urljoin(base, caminho)
        texto = re.sub(r"^[^>]*>", "", resto)
        titulo = re.sub(r"\s+", " ", texto).strip()
        if len(titulo) < 6:
            titulo = titulo_do_slug(urlsplit(link).path)
        achadas.setdefault(link, titulo)
    return [(t, l) for l, t in achadas.items()]


def ultima_pagina_declarada(html: str) -> int | None:
    """O maior ?page=N que a propria pagina oferece. Medido: 36."""
    numeros = [int(n) for n in _PAGINA_NO_LINK.findall(html or "")]
    return max(numeros) if numeros else None


def _achatar(no):
    """JSON-LD vem como objeto, como lista ou dentro de @graph."""
    if isinstance(no, list):
        for item in no:
            yield from _achatar(item)
    elif isinstance(no, dict):
        yield no
        for chave in ("@graph", "itemListElement", "mainEntity"):
            if chave in no:
                yield from _achatar(no[chave])


def jobposting(html: str) -> dict | None:
    """O JobPosting do schema.org na pagina da vaga. None quando nao tem — e
    ai GRITA, porque a fonte inteira depende disso."""
    for bruto in _SCRIPT_JSONLD.findall(html or ""):
        try:
            dados = json.loads(bruto.strip())
        except ValueError:
            continue
        for no in _achatar(dados):
            tipo = no.get("@type")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if any(str(t).lower() == "jobposting" for t in tipos):
                return no
    return None


def e_remota(jp: dict) -> bool:
    """TELECOMMUTE e o que o schema.org usa pra remoto. Nao infere remoto do
    titulo nem da rota: ver a armadilha do anuncio fixo, no topo."""
    return str((jp or {}).get("jobLocationType") or "").strip().upper() == "TELECOMMUTE"


def local_da_vaga(jp: dict) -> str:
    """"Cidade, Portugal" quando o endereco diz a cidade; "Portugal" quando
    nao diz.

    addressLocality NAO foi confirmado no dado real — a sondagem truncou o
    endereco no postalCode. Por isso a reserva: na pior hipotese o local sai
    "Portugal", que e o que o filtro internacional precisa (mercado lusofono),
    e nunca sai errado. testar_itjobs_rede.py imprime o endereco inteiro pra
    confirmar a chave."""
    locais = (jp or {}).get("jobLocation")
    if isinstance(locais, dict):
        locais = [locais]
    for lugar in locais or []:
        endereco = (lugar or {}).get("address") or {}
        cidade = (endereco.get("addressLocality")
                  or endereco.get("addressRegion") or "").strip()
        if cidade:
            return f"{cidade}, Portugal"
    return "Portugal"


def expirada(jp: dict, hoje: date | None = None) -> bool:
    """validThrough no passado = anuncio encerrado. Data ilegivel NAO conta
    como expirada: na duvida, mostra (mesma regra do scrapers/senior.py)."""
    fim = (jp or {}).get("validThrough")
    if not fim:
        return False
    try:
        return date.fromisoformat(str(fim)[:10]) < (hoje or date.today())
    except ValueError:
        return False


def montar_job(titulo_da_listagem: str, link: str, jp: dict,
               hoje: date | None = None) -> Job | None:
    """Converte o JSON-LD num Job. None quando a vaga nao serve.

    Funcao pura de proposito: e o que da pra testar sem rede, e e onde mora
    todo o risco (mapear campo errado nao quebra nada, so muda em silencio o
    que e aprovado)."""
    if not jp or not link:
        return None
    if expirada(jp, hoje):
        return None

    titulo = str(jp.get("title") or titulo_da_listagem or "").strip()
    if not titulo:
        return None

    empresa = (jp.get("hiringOrganization") or {})
    if not isinstance(empresa, dict):
        empresa = {}

    return Job(
        titulo=titulo,
        empresa=str(empresa.get("name") or "Não informada").strip(),
        local=local_da_vaga(jp),
        link=link,
        site="ITJobs",
        publicado_em=str(jp.get("datePosted") or "")[:10],
        modalidade="Remoto" if e_remota(jp) else "",
    )


def combina_com_algum_termo(titulo: str, termos: list[str]) -> bool:
    """Pre-filtro de termo, dentro do scraper, porque o site NAO combina termo
    com remoto: /emprego/remote?q=data devolveu a lista sem o q (medido). As
    outras fontes pedem o termo ao site; aqui o cruzamento tem que ser nosso.

    Deliberadamente FROUXO (substring normalizada): quem decide de verdade e
    o filtro de tres niveis em core/job.py. Aqui so se evita abrir 630 paginas
    de detalhe."""
    alvo = _normalizar(titulo or "")
    return any(_normalizar(t) in alvo for t in (termos or []) if t)


class ITJobsScraper(BaseScraper):
    """Busca vaga remota no https://www.itjobs.pt/emprego/remote."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        candidatas = self._colher_listagem()
        vagas = self._abrir_detalhes(candidatas)
        logger.info(f"[ITJobs] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _baixar(self, url: str) -> str | None:
        try:
            resposta = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
        except Exception as erro:
            logger.error(f"[ITJobs] Erro de rede em {url}: {erro}")
            return None
        if resposta.status_code != 200:
            logger.warning(
                f"[ITJobs] Status {resposta.status_code} em {url} — resposta "
                "inesperada, não é busca vazia."
            )
            return None
        return resposta.text

    def _colher_listagem(self) -> list[tuple[str, str]]:
        """Titulo e link de toda vaga da rota de remoto, parando no fim real."""
        candidatas: dict[str, str] = {}
        ultima = None
        for pagina in range(1, MAX_PAGINAS + 1):
            html = self._baixar(url_da_pagina(pagina))
            if html is None:
                break
            vagas = vagas_da_listagem(html)
            if not vagas:
                logger.info(f"[ITJobs] Página {pagina} sem vaga — fim da listagem.")
                break
            for titulo, link in vagas:
                candidatas.setdefault(link, titulo)
            if ultima is None:
                ultima = ultima_pagina_declarada(html)
                if ultima:
                    logger.info(
                        f"[ITJobs] A listagem declara {ultima} página(s) de vaga remota."
                    )
            if ultima and pagina >= min(ultima, MAX_PAGINAS):
                break
        else:
            logger.warning(
                f"[ITJobs] Bateu o teto de {MAX_PAGINAS} páginas de listagem. Se o "
                "site cresceu, há vaga remota ficando de fora."
            )
        logger.info(f"[ITJobs] {len(candidatas)} vaga(s) remota(s) na listagem.")
        return [(t, l) for l, t in candidatas.items()]

    def _abrir_detalhes(self, candidatas: list[tuple[str, str]]) -> list[Job]:
        """Abre a página da vaga só do que casou com algum termo de busca."""
        casaram = [(t, l) for t, l in candidatas
                   if combina_com_algum_termo(t, self.termos_busca)]
        logger.info(
            f"[ITJobs] {len(casaram)} de {len(candidatas)} título(s) casaram com "
            f"os {len(self.termos_busca)} termo(s) deste ciclo."
        )
        if len(casaram) > MAX_DETALHES_POR_CICLO:
            logger.warning(
                f"[ITJobs] {len(casaram)} título(s) casaram, acima do teto de "
                f"{MAX_DETALHES_POR_CICLO} requisições de detalhe. Lendo as "
                f"{MAX_DETALHES_POR_CICLO} primeiras — teto do scraper, não fim "
                "dos resultados."
            )
            casaram = casaram[:MAX_DETALHES_POR_CICLO]

        vagas: list[Job] = []
        sem_jsonld = 0
        expiradas = 0
        for i, (titulo, link) in enumerate(casaram):
            if i:
                time.sleep(PAUSA_ENTRE_DETALHES)
            html = self._baixar(link)
            if html is None:
                continue
            jp = jobposting(html)
            if jp is None:
                sem_jsonld += 1
                continue
            if expirada(jp):
                expiradas += 1
                continue
            job = montar_job(titulo, link, jp)
            if job is not None:
                vagas.append(job)

        if expiradas:
            logger.info(
                f"[ITJobs] {expiradas} vaga(s) descartada(s) por validThrough no "
                "passado — o próprio anúncio diz que encerrou."
            )
        if sem_jsonld:
            # GRITA: a fonte inteira depende do JSON-LD. Sem ele, sobra titulo
            # e link, sem data, sem empresa e sem confirmacao de remoto — e a
            # vaga morreria no filtro sem ninguem saber por que.
            logger.error(
                f"[ITJobs] {sem_jsonld} de {len(casaram)} página(s) de vaga SEM "
                "schema.org/JobPosting. O site parou de publicar dado estruturado; "
                "esta fonte depende dele."
            )
        return vagas
