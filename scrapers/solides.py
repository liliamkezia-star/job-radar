from datetime import date, datetime, timezone
import json
import re
import time
import unicodedata

import requests

from core.job import Job
from core.logger import get_logger
from scrapers.base import BaseScraper

logger = get_logger()

# COMO A SOLIDES E LIDA HOJE, E POR QUE MUDOU (07-08/09/2026).
#
# Ate 07/09 este scraper chamava a API que o portal usava:
#
#     apigw.solides.com.br/jobs/v3/portal-vacancies-new
#
# Ela foi APOSENTADA. Passou a responder 403 com
# {"message":"Missing Authentication Token"} -- mensagem do AWS API Gateway
# pra rota que nao existe. MEDIDO de tres lugares, pra descartar as causas
# faceis antes de reconstruir qualquer coisa:
#
#   · do IP de datacenter do GitHub Actions ............. 403
#   · do IP residencial, com 4 variacoes de cabecalho ... 403
#   · de DENTRO da pagina do portal, num Chrome com a
#     sessao do site (mesma origem, mesmos cookies) ..... 403
#
# Nao era IP, nao era cabecalho, nao era cookie: a porta foi fechada. O
# portal foi refeito em Next.js com rotas novas (/vagas/<termo>/todas), e
# nao chama mais aquele endpoint -- 118 requisicoes capturadas em varios
# carregamentos, nenhuma pro apigw.
#
# O QUE SALVOU A FONTE: o portal novo entrega as vagas no HTML da propria
# pagina, dentro dos blocos RSC do Next.js (self.__next_f.push), e com os
# MESMOS NOMES DE CAMPO da API velha:
#
#     {"id":917373,"title":"...","companyName":"OPEN LABS S.A.",
#      "state":{"name":"Rio de Janeiro","code":"RJ"},"city":{...},
#      "jobType":...,"homeOffice":...,"createdAt":...,"redirectLink":...}
#
# Por isso montar_job, montar_local, montar_modalidade e pagina_toda_antiga
# continuam valendo SEM UMA LINHA de mudanca, com os testes que ja tinham.
# Trocou so a camada que busca e extrai.
#
# E continua SEM NAVEGADOR: o HTML cru ja traz tudo, entao o ciclo nao volta
# aos ~7 minutos do Playwright, que foi de onde a gente saiu em 29/08.
#
# ALCANCE CONFERIDO contra a API velha, mesmo termo:
#     analista de dados ... 209 (API) -> 204 (portal novo)
#     power bi ............ 516 (API) -> 502 (portal novo)
#
# O RISCO, dito com todas as letras: bloco RSC e detalhe interno do Next.js
# e pode mudar sem aviso -- e menos estavel que uma API documentada. A
# mitigacao esta em extrair_vagas(): quando o formato muda, ela grita no log
# em vez de devolver zero em silencio. Zero silencioso foi exatamente o erro
# que custou uma semana de diagnostico nesta base.
URL_BASE = "https://vagas.solides.com.br/vagas"

# MEDIDO: o portal novo entrega 14 vagas por pagina (a API velha dava 10).
POR_PAGINA = 14


def slug_do_termo(termo: str) -> str:
    """'Inteligência de Mercado' -> 'inteligencia-de-mercado'.

    A rota do portal e /vagas/<slug>/todas. Sem acento, sem espaco.
    """
    texto = unicodedata.normalize("NFD", (termo or "").strip().lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def url_da_busca(termo: str, pagina: int) -> str:
    url = f"{URL_BASE}/{slug_do_termo(termo)}/todas"
    return url if pagina <= 1 else f"{url}?page={pagina}"


# Os blocos que o Next.js usa pra mandar os dados junto com o HTML. Cada um
# carrega um literal de string JSON; o conteudo de verdade so aparece depois
# de desescapar.
_BLOCO_RSC = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')

# Onde uma lista de objetos comeca dentro do payload ja desescapado. De
# proposito NAO procura chave nenhuma pelo nome: assim a extracao sobrevive a
# eles renomearem ou reordenarem campo, que e a mudanca mais provavel. Quem
# decide se a lista e de vagas e a validacao abaixo (precisa ter id e title).
_INICIO_DE_LISTA = re.compile(r'\[\s*\{\s*"')


def _payload_desescapado(html: str) -> str:
    """Junta e desescapa os blocos RSC. Vazio quando nao ha bloco nenhum."""
    partes = []
    for literal in _BLOCO_RSC.findall(html or ""):
        try:
            partes.append(json.loads(literal))
        except ValueError:
            continue
    return "".join(partes)


def _lista_de_vagas(payload: str) -> list[dict]:
    """A maior lista de objetos com id e title. Varre todas as candidatas em vez
    de confiar numa ancora fixa -- a pagina traz varias listas (filtros, links,
    empresas) e a das vagas e a maior que passa na validacao."""
    decodificador = json.JSONDecoder()
    melhor: list[dict] = []
    for achado in _INICIO_DE_LISTA.finditer(payload):
        try:
            valor, _ = decodificador.raw_decode(payload, achado.start())
        except ValueError:
            continue
        if not isinstance(valor, list):
            continue
        vagas = [v for v in valor
                 if isinstance(v, dict) and v.get("id") and v.get("title")]
        if len(vagas) > len(melhor):
            melhor = vagas
    return melhor

def extrair_vagas(html: str, termo: str = "") -> list[dict]:
    """Tira a lista de vagas do HTML do portal novo.

    GRITA quando nao acha. A diferenca entre 'esta pagina nao tem vaga' e 'o
    formato mudou e eu nao sei mais ler' e a coisa mais importante deste
    arquivo: confundir as duas foi o que fez a fonte cair de 400 pra 70 vagas
    sem ninguem perceber, em 01/09.
    """
    payload = _payload_desescapado(html)
    if not payload:
        logger.error(
            f"[Solides] Nenhum bloco RSC no HTML de '{termo}' — o portal mudou "
            "de tecnologia, ou a resposta não é a página de vagas. "
            "Isto NÃO é busca vazia."
        )
        return []

    vagas = _lista_de_vagas(payload)
    if not vagas and '"companyName"' in payload:
        logger.error(
            f"[Solides] Achei bloco RSC com dados de vaga em '{termo}', mas não "
            "consegui ler a lista — o formato do payload mudou. Isto NÃO é "
            "busca vazia; ver _lista_de_vagas em scrapers/solides.py."
        )
    return vagas


def total_de_vagas(html: str) -> int | None:
    """Quantas vagas o portal diz existir pro termo. None quando não declara."""
    achado = re.search(r'"count"\s*:\s*(\d+)', _payload_desescapado(html))
    return int(achado.group(1)) if achado else None

# ONDE PARAR DE PAGINAR.
#
# MEDIDO (30/08), sondando os 45 termos do perfil BR: nenhum termo passa da
# pagina 7 antes das vagas ficarem com mais de uma semana. O teto fixo de 15
# paginas que existia antes nunca cortou vaga nova -- ele lia 9 paginas a
# mais de vaga VELHA. Estava frouxo, nao apertado.
#
# Por isso o criterio nao e "quantas paginas" e sim "ate quando". A lista vem
# da mais recente pra mais antiga, entao basta parar quando as vagas ficarem
# velhas demais. Custo medido, em requisicoes por termo:
#
#     teto fixo de 15 paginas   4,6
#     parar apos  7 dias        2,2
#     parar apos 14 dias        3,0
#     parar apos 30 dias        4,8   <- escolhido
#
# 30 dias e tambem o limiar de Job.publicacao_antiga: alem disso a vaga ja
# ganharia o aviso de "pode ja estar preenchida" e sairia do alerta imediato.
# Ler mais fundo seria buscar o que o filtro desprioriza.
#
# NOTA 08/09: estes numeros foram medidos na API antiga, que dava 10 vagas
# por pagina. O portal novo da 14, entao cada pagina cobre mais dias e o
# custo por termo tende a CAIR. O criterio nao muda; so fica mais barato.
DIAS_PARA_PARAR = 30

# Trava de seguranca, nao criterio: impede laco infinito se o portal passar a
# devolver data invalida ou parar de ordenar por data.
MAX_PAGINAS = 30

PAUSA_ENTRE_PAGINAS = 0.5
TIMEOUT = 30
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# jobType da API -> vocabulario que o filtro ja usa (ver core/job.py).
_MODALIDADE = {
    "presencial": "Presencial",
    "hibrido": "Híbrido",
    "híbrido": "Híbrido",
    "remoto": "Remoto",
    "home office": "Remoto",
    "homeoffice": "Remoto",
}


def pagina_toda_antiga(itens: list[dict], dias: int, hoje: date | None = None) -> bool:
    """A vaga MAIS NOVA desta pagina ja passou do limite de idade?

    A lista da API vem ordenada da mais recente pra mais antiga, entao a
    partir daqui so vem coisa ainda mais velha -- da pra parar.

    Devolve False quando nenhuma data da pra ler: sem data nao ha o que
    concluir, e parar por engano custa vaga. Errar pro lado de continuar
    custa uma requisicao.
    """
    hoje = hoje or datetime.now(timezone.utc).date()
    idades = []
    for vaga in itens:
        bruto = (vaga.get("createdAt") or "").strip()[:10]
        try:
            idades.append((hoje - date.fromisoformat(bruto)).days)
        except ValueError:
            continue
    if not idades:
        return False
    return min(idades) > dias


def montar_local(vaga: dict) -> str:
    """Monta `local` como "Cidade - UF", que e um dos formatos que o filtro
    ja reconhece.

    A Solides entrega a SIGLA em state.code ("ES"), diferente da Gupy, que
    so da o nome por extenso. Sigla e o caminho mais curto e mais seguro na
    conferencia de UF (ver _uf_declarada em core/job.py).
    """
    cidade = ((vaga.get("city") or {}).get("name") or "").strip()
    sigla = ((vaga.get("state") or {}).get("code") or "").strip()
    if cidade and sigla:
        return f"{cidade} - {sigla}"
    return cidade or sigla or "Não informado"


def montar_modalidade(vaga: dict) -> str:
    """Traduz jobType. homeOffice entra como reforco: sao campos
    independentes, e vaga remota as vezes chega com so um deles."""
    bruto = (vaga.get("jobType") or "").strip().lower()
    if bruto in _MODALIDADE:
        return _MODALIDADE[bruto]
    if vaga.get("homeOffice") is True:
        return "Remoto"
    return ""


def montar_job(vaga: dict) -> Job | None:
    """Converte um item da API num Job. None quando falta o essencial.

    Funcao pura de proposito: e o que da pra testar sem rede, e onde mora
    todo o risco da troca -- mapear campo errado nao quebra nada, so muda
    silenciosamente o que e aprovado.
    """
    titulo = (vaga.get("title") or "").strip()
    link = (vaga.get("redirectLink") or "").strip()
    if not titulo or not link:
        return None

    return Job(
        titulo=titulo,
        empresa=(vaga.get("companyName") or "Não informado").strip(),
        local=montar_local(vaga),
        link=link,
        site="Solides",
        publicado_em=(vaga.get("createdAt") or "").strip()[:10],
        modalidade=montar_modalidade(vaga),
    )


class SolidesScraper(BaseScraper):
    """Busca vagas na API publica do portal da Sólides."""

    def __init__(self, termos_busca: list[str]):
        self.termos_busca = termos_busca

    def buscar_vagas(self) -> list[Job]:
        vagas: list[Job] = []
        # Termos cuja PRIMEIRA pagina veio com count=0. Ver _segunda_passada.
        self._incompletos = []
        self._registrar_incompletos = True
        for termo in self.termos_busca:
            vagas.extend(self._buscar_termo(termo))
        vagas.extend(self._segunda_passada(vagas))
        logger.info(f"[Solides] {len(vagas)} vaga(s) encontrada(s) no total")
        return vagas

    def _segunda_passada(self, vagas_da_primeira: list[Job]) -> list[Job]:
        """Repete, no fim do ciclo, so os termos que voltaram com count=0.

        MEDIDO (01/09). No ciclo das 08:14 a Solides devolveu 70 vagas no total
        contra ~400 dos ciclos anteriores, com "0 resultados reais" nos CINCO
        termos prioritarios. Sondada minutos depois, a mesma API respondeu 200
        com:

            analista de dados     209 vagas, 21 paginas
            analista de bi         33 vagas,  4 paginas
            business intelligence 133 vagas, 14 paginas
            power bi              516 vagas, 52 paginas
            sql                   613 vagas, 62 paginas

        O zero era falso. No dia anterior essa API ja tinha devolvido um 504.

        POR QUE AQUI DOI MAIS QUE NO LINKEDIN: count=0 faz o laco de paginacao
        parar no primeiro request. Um zero mentiroso nao custa uma busca --
        custa o TERMO INTEIRO, com todas as suas paginas. Foi assim que a fonte
        caiu de ~400 para 70 vagas sem disparar nenhum alerta: ela nao falhou,
        ela "respondeu".

        Mesmo desenho da segunda passada do LinkedIn (ver scrapers/linkedin.py),
        que no primeiro ciclo em producao recuperou 43 vagas ineditas. Segura
        por construcao -- so repete termo que ja voltou zero -- e barata: a API
        responde em menos de um segundo, entao sao ~15 requisicoes no pior caso.

        CRITERIO DE MORTE, escrito antes do resultado: se as vagas recuperadas
        ficarem em ~0 por alguns ciclos, esta passada nao se paga e sai.
        """
        if not self._incompletos:
            return []

        self._registrar_incompletos = False
        pendentes = self._incompletos
        logger.info(
            f"[Solides] Segunda passada: repetindo {len(pendentes)} termo(s) "
            "que ficaram incompletos na primeira."
        )

        recuperadas: list[Job] = []
        termos_que_voltaram = 0
        for termo in pendentes:
            achadas = self._buscar_termo(termo)
            if achadas:
                termos_que_voltaram += 1
                recuperadas.extend(achadas)
                logger.info(
                    f"[Solides] Segunda passada recuperou {len(achadas)} vaga(s) "
                    f"em '{termo}' — a primeira passada não trouxe nada."
                )

        ja_vistos = {v.id for v in vagas_da_primeira}
        ineditas = [v for v in recuperadas if v.id not in ja_vistos]
        logger.info(
            f"[Solides] Segunda passada: {termos_que_voltaram}/{len(pendentes)} "
            f"termo(s) voltaram com vaga, {len(recuperadas)} vaga(s) bruta(s), "
            f"{len(ineditas)} inédita(s) neste ciclo."
        )
        return ineditas

    def _anotar_incompleto(self, termo: str) -> None:
        """Marca um termo que terminou SEM resposta confiavel, pra segunda passada.

        Sao quatro saidas diferentes com a mesma consequencia: o laco de
        paginacao para e o termo fica pela metade (ou em nada). count=0, erro de
        rede, status != 200 e resposta nao-JSON.

        MEDIDO no ciclo de 01/09 18:07, que e o que fez esta funcao existir: a
        Solides devolveu 504 em NOVE termos ('analista de bi', 'business
        intelligence', 'data analyst', 'sql', 'python', 'tableau' e outros --
        quase todos ja na PAGINA 1, ou seja, o termo trouxe zero vaga). A fonte
        fechou o ciclo com 67 vagas contra ~400 do normal.

        A versao anterior desta segunda passada so anotava count=0 e deixava os
        504 passarem. Ou seja: eu tinha coberto o modo de falha que descobri
        primeiro e nao o que mais doeu no dia seguinte. As quatro saidas contam
        igual porque a consequencia e a mesma -- vaga que existe nao foi vista.
        """
        if getattr(self, "_registrar_incompletos", False) and termo not in self._incompletos:
            self._incompletos.append(termo)

    def _buscar_termo(self, termo: str) -> list[Job]:
        logger.info(f"[Solides] Buscando: {termo}")
        vagas: list[Job] = []
        total_paginas = None

        for pagina in range(1, MAX_PAGINAS + 1):
            url = url_da_busca(termo, pagina)
            try:
                resposta = requests.get(
                    url,
                    timeout=TIMEOUT,
                    headers={"User-Agent": UA, "Accept": "text/html"},
                )
            except Exception as erro:
                logger.error(f"[Solides] Erro ao buscar '{termo}' (página {pagina}): {erro}")
                self._anotar_incompleto(termo)
                break

            if resposta.status_code != 200:
                logger.warning(
                    f"[Solides] Status {resposta.status_code} em '{termo}' "
                    f"(página {pagina}) — resposta inesperada do portal, não é busca vazia."
                )
                self._anotar_incompleto(termo)
                break

            lote = extrair_vagas(resposta.text, termo)

            if total_paginas is None:
                # O portal declara o total; as paginas saem dele. Quando nao
                # declara, o laco para sozinho na primeira pagina sem vaga.
                total = total_de_vagas(resposta.text)
                if total:
                    total_paginas = -(-total // POR_PAGINA)   # divisao pra cima
                if not lote:
                    # MEDIDO 01/09, e vale igual aqui: pagina sem vaga NAO quer
                    # dizer "nao ha vaga". Anota pra segunda passada, e o texto
                    # nao afirma o que nao da pra saber. Se o motivo tiver sido
                    # formato mudado, extrair_vagas ja gritou no log acima.
                    self._anotar_incompleto(termo)
                    logger.info(
                        f"[Solides] nenhuma vaga na página 1 de '{termo}' — pode "
                        "ser ausência de vaga ou resposta instável do portal; "
                        "medido, não dá pra distinguir (ver _segunda_passada)."
                    )
                    break

            for item in lote:
                job = montar_job(item)
                if job is not None:
                    vagas.append(job)

            if not lote or (total_paginas and pagina >= total_paginas):
                break

            if pagina_toda_antiga(lote, DIAS_PARA_PARAR):
                logger.info(
                    f"[Solides] '{termo}': parou na página {pagina} de "
                    f"{total_paginas or '?'} — daqui pra frente só vaga com mais "
                    f"de {DIAS_PARA_PARAR} dias."
                )
                break

            time.sleep(PAUSA_ENTRE_PAGINAS)

        else:
            # BUG CORRIGIDO (introduzido em d6253e9): o aviso antigo testava
            # "total_paginas > MAX_PAGINAS", ou seja, se o termo TEM mais
            # paginas que a trava -- nao se a trava foi realmente atingida.
            # No ciclo de 30/08 'power bi' parou certinho na pagina 18 de 53
            # POR IDADE, como devia, e mesmo assim disparou o aviso. Alarme
            # falso, da mesma familia dos que passamos a semana eliminando.
            #
            # O 'else' de um 'for' em Python so roda quando o laco termina SEM
            # break. Como toda parada legitima (0 resultado, ultima pagina,
            # pagina toda antiga, erro de rede, status inesperado) sai por
            # break, chegar aqui significa exatamente uma coisa: rodou as
            # MAX_PAGINAS inteiras e nenhuma pagina era antiga o bastante pra
            # parar -- que e o unico caso em que o aviso e verdade.
            logger.warning(
                f"[Solides] '{termo}': bateu a trava de {MAX_PAGINAS} páginas sem "
                f"chegar em vaga de {DIAS_PARA_PARAR} dias ({total_paginas} páginas no "
                "total) — a API pode ter parado de ordenar por data."
            )
        return vagas
