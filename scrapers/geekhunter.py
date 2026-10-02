
import re
import time
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from core.job import Job, extrair_data_publicacao
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

_MODALIDADES = {"presencial", "híbrido", "hibrido", "remoto"}

# Ver comentário equivalente em scrapers/gupy.py: só a 1a página nunca
# alcançava vaga de cidade menor (Recife, Natal, Maceió etc.).
MAX_PAGINAS = 3


def _empresa_da_url(path: str) -> str:
    """A listagem não mostra o nome da empresa, só o slug na URL
    (/pt/{empresa}/jobs/{vaga}). Deriva um nome legível a partir dele."""
    partes = path.strip("/").split("/")
    if len(partes) >= 2:
        slug = partes[1]
        return slug.replace("-", " ").title()
    return "Não informado"


# MEDIDO em 02/10/2026: o layout do card mudou e o scraper passou a trazer
# cidade E modalidade vazias em 100% das vagas (21 brutas -> 0 aprovadas
# num ciclo; nenhuma reprovou pelo titulo). Duas causas, as duas vistas na
# sonda, nao supostas:
#
# 1. A ancora a[href*="/jobs/"] hoje envolve SO o titulo. Senioridade,
#    modalidade e cidade estao no DIV bisavo dela:
#      <a>   ['Analista de Dados - Presencial /SP']
#      <h3>  idem
#      <div> idem
#      <div> ['Analista de Dados - Presencial /SP', 'PLENO',
#             'PRESENCIAL', 'Sao Paulo, SP, Brasil']
#    Antes o texto da ancora trazia tudo, entao card.inner_text() bastava.
# 2. A bandeira do Brasil que marcava a linha de cidade nao existe mais. O
#    formato agora e "Cidade, UF, Brasil" — a regra antiga
#    re.match(r"^<bandeira>", linha) nunca mais casava.
#
# Por que SUBIR ate achar, em vez de fixar o bisavo: um wrapper a mais no
# meio (acontece quando o site troca o grid) voltaria a zerar tudo em
# silencio. Sobe no maximo _MAX_NIVEIS_ACIMA.
#
# Guarda contra subir DEMAIS: se o nivel achado contem mais de uma ancora
# de vaga, ele e a LISTA e nao o card — dado de uma vaga vazaria pra outra.
# Nesse caso devolve None e o chamador AVISA, em vez de inventar cidade.
_MAX_NIVEIS_ACIMA = 5

_SELETOR_VAGA = 'a[href*="/jobs/"]'

# "Sao Paulo, SP, Brasil", "Recife, PE, Brasil" e tambem "Brasil" sozinho
# (vaga remota). Exige o pais no fim pra nao confundir com titulo que tem
# virgula.
_RE_LINHA_DE_LOCAL = re.compile(r"^(.*,\s*)?brasil\.?$", re.IGNORECASE)


def linhas_do_texto(texto: str) -> list[str]:
    return [l.strip() for l in texto.split("\n") if l.strip()]


def container_do_card(ancora, max_niveis: int = _MAX_NIVEIS_ACIMA):
    """Sobe na arvore a partir da ancora ate o elemento que tem mais que o
    titulo. None quando nao achou, ou quando o que achou e a lista inteira."""
    atual = ancora
    for _ in range(max_niveis):
        pai = atual.query_selector("xpath=..")
        if pai is None:
            return None
        atual = pai
        if len(linhas_do_texto(atual.inner_text())) <= 1:
            continue
        if len(atual.query_selector_all(_SELETOR_VAGA)) > 1:
            return None
        return atual
    return None


def extrair_campos(linhas: list[str]) -> tuple[str, str, str]:
    """titulo, local e modalidade a partir das linhas do card."""
    if not linhas:
        return "", "", ""
    titulo = linhas[0]
    modalidade = ""
    local = ""
    for linha in linhas[1:]:
        if linha.lower() in _MODALIDADES:
            modalidade = linha.capitalize()
        elif _RE_LINHA_DE_LOCAL.match(linha):
            local = linha
        elif linha.startswith("\U0001F1E7\U0001F1F7"):
            # Formato antigo (bandeira). Mantido porque custa uma linha e,
            # se o site voltar pra ele, a cidade continua sendo lida.
            local = linha.replace("\U0001F1E7\U0001F1F7", "").strip()
    return titulo, local, modalidade
class GeekHunterScraper(BaseScraper):
    """Busca vagas no https://www.geekhunter.com/pt/vagas."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))

        logger.info(f"[GeekHunter] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[GeekHunter] Buscando: {termo}")
        vagas: list[Job] = []
        # quote_plus (não um .replace(" ", "+") manual) porque termo pode ter
        # caractere reservado de query string — ex: "BI & Analytics Analyst"
        # tem "&", que sem escapar cortaria a URL no meio e criaria um
        # parâmetro falso, quebrando a busca silenciosamente pra esse termo.
        termo_url = quote_plus(termo)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                for pagina in range(1, MAX_PAGINAS + 1):
                    url = f"https://www.geekhunter.com/pt/vagas?searchTerm={termo_url}&page={pagina}"
                    page.goto(url, timeout=60000)
                    sem_resultados = False
                    try:
                        page.wait_for_selector('a[href*="/jobs/"]', timeout=15000)
                    except PlaywrightTimeoutError:
                        if pagina > 1:
                            # Ver comentário equivalente em scrapers/gupy.py: timeout
                            # de verdade é DIFERENTE de "acabaram as vagas" (isso é
                            # sinalizado abaixo, quando a página carrega normal mas
                            # devolve 0 cards). Sem separar os dois, a perda por
                            # timeout ficava invisível — virava break silencioso
                            # idêntico ao fim natural da paginação.
                            logger.warning(
                                f"[GeekHunter] Timeout esperando resultados na página "
                                f"{pagina} de '{termo}' — parando de paginar por falha "
                                "de carregamento, não por fim real dos resultados. "
                                "Pode ter ficado vaga de página seguinte de fora."
                            )
                            break
                        if "0 vagas disponíveis" in page.inner_text("body"):
                            logger.info(f"[GeekHunter] 0 resultados reais para '{termo}'.")
                            sem_resultados = True
                        else:
                            raise
                    if not sem_resultados:
                        time.sleep(2)

                    cards = [] if sem_resultados else page.query_selector_all('a[href*="/jobs/"]')
                    if not cards:
                        break

                    sem_container = 0
                    for card in cards:
                        try:
                            # O container tem o texto da ancora MAIS cidade,
                            # modalidade e senioridade. Quando nao da pra
                            # achar, cai pra ancora (titulo + link ainda
                            # valem) e conta pro aviso no fim da pagina.
                            container = container_do_card(card)
                            if container is None:
                                sem_container += 1
                            texto = (container or card).inner_text()

                            linhas = linhas_do_texto(texto)
                            if not linhas:
                                continue

                            titulo, cidade, modalidade = extrair_campos(linhas)
                            local = cidade or "Não informado"

                            link = card.get_attribute("href")
                            if not link:
                                continue

                            path = urlparse(link).path if link.startswith("http") else link
                            empresa = _empresa_da_url(path)

                            if link.startswith("/"):
                                link = f"https://www.geekhunter.com{link}"

                            publicado_em = extrair_data_publicacao(texto)

                            vagas.append(Job(
                                titulo=titulo,
                                empresa=empresa,
                                local=local,
                                link=link,
                                site="GeekHunter",
                                publicado_em=publicado_em,
                                modalidade=modalidade,
                            ))
                        except Exception as e:
                            logger.warning(f"[GeekHunter] Erro ao processar card: {e}")
                            continue

                    if sem_container:
                        # GRITA: sem o container, cidade e modalidade voltam
                        # vazias e a vaga morre no filtro de local. Foi
                        # exatamente isso acontecendo em silencio desde a
                        # mudanca de layout.
                        logger.warning(
                            f"[GeekHunter] {sem_container} de {len(cards)} card(s) da "
                            f"pagina {pagina} de '{termo}' sem container legivel — "
                            "cidade e modalidade ficaram vazias nesses. O layout do "
                            "card provavelmente mudou de novo."
                        )

                    if sem_resultados:
                        break

            except Exception as e:
                logger.error(f"[GeekHunter] Erro ao buscar '{termo}': {e}")
            finally:
                browser.close()

        return vagas
