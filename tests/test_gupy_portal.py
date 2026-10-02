"""Gupy pelo portal: a camada de busca reconstruida em 02/10/2026.

POR QUE EXISTE. A API (employability-portal.gupy.io/api/v1/jobs) respondeu
404 em todo termo, sem parametro e na raiz /api/v1/. A fonte deu ZERO vaga em
tres ciclos e ninguem viu. Os dados passaram pro __NEXT_DATA__ da pagina de
busca.

tests/test_gupy_api.py continua valendo inteiro: ele guarda montar_job,
montar_local e montar_modalidade, que NAO mudaram. Este arquivo guarda o que
mudou — a URL, a extracao do JSON da pagina e a paginacao.

O DADO AQUI E REAL, capturado em 02/10. O link quebrado da Solides passou 24
dias escondido porque a fixture tinha um redirectLink que EU escrevi.
"""
import types

import pytest

from scrapers import gupy
from scrapers.gupy import (
    MAX_VAGAS_POR_TERMO,
    POR_PAGINA_PADRAO,
    extrair_lista,
    extrair_next_data,
    montar_job,
    url_da_busca,
)

# Primeira vaga de "analista de dados" no portal, campo por campo, como veio.
_VAGA_REAL = {
    "name": "0911-  Analista de Dados (Foco em ML/IA) - Sicredi União MS/TO "
            "e Oeste da BA - Campo Grande/MS",
    "careerPageName": "Sicredi",
    "publishedDate": "2026-10-01T20:32:59.372Z",
    "jobUrl": "https://sicredi.gupy.io/job/eyJqb2JJZCI6MTI2MDQxNTcsInNvdXJjZSI6"
              "Imd1cHlfcG9ydGFsIn0=?jobBoardSource=gupy_portal",
    "city": "Campo Grande",
    "state": "Mato Grosso do Sul",
    "workplaceType": "on-site",
    "applicationDeadline": "2026-10-31",
    "id": 12604157,
    "type": "vacancy_type_effective",
}


def _html(paginacao: dict, vagas: list[dict], ordem_invertida: bool = False,
          chave_da_lista: str = "initialJobList") -> str:
    """A pagina como o portal manda: um JSON unico dentro do __NEXT_DATA__."""
    import json

    dados = {
        "buildId": "cV0_DMl2AbEm4R-kj_nZu",
        "props": {"pageProps": {
            chave_da_lista: {"pagination": paginacao, "data": vagas},
            # 569 feature flags, como na pagina de verdade. Elas existem aqui
            # porque foram ELAS que a heuristica de "maior lista de
            # dicionarios" escolheu na sondagem, em vez das vagas.
            "toggles": [{"name": f"flag_{i}", "enabled": False} for i in range(569)],
        }},
    }
    atributos = ('type="application/json" id="__NEXT_DATA__"' if ordem_invertida
                 else 'id="__NEXT_DATA__" type="application/json"')
    return (
        "<html><body><div>vagas</div>"
        f"<script {atributos}>{json.dumps(dados)}</script>"
        "</body></html>"
    )


def _vagas(quantidade: int, prefixo: str = "") -> list[dict]:
    lote = []
    for i in range(quantidade):
        v = dict(_VAGA_REAL)
        v["name"] = f"{prefixo}{i} {_VAGA_REAL['name']}"
        v["jobUrl"] = f"{_VAGA_REAL['jobUrl']}&n={prefixo}{i}"
        lote.append(v)
    return lote


# --- a URL ------------------------------------------------------------


def test_a_primeira_pagina_nao_leva_page():
    assert url_da_busca("analista de dados", 1) == (
        "https://portal.gupy.io/job-search/term=analista%20de%20dados"
    )


def test_a_segunda_pagina_leva_page_2():
    assert url_da_busca("analista de dados", 2).endswith("?page=2")


def test_espaco_vira_porcento_20_e_nao_mais():
    """quote e nao quote_plus: o termo vai no CAMINHO da URL, e "+" no caminho
    e um "+" literal, nao um espaco. Com quote_plus a busca procuraria
    "analista+de+dados" ao pe da letra."""
    assert "+" not in url_da_busca("analista de dados", 1)
    assert "%20" in url_da_busca("analista de dados", 1)


def test_e_comercial_no_termo_nao_quebra_a_url():
    """"BI & Analytics" tem "&". Ele esta no caminho, nao na query, mas se um
    dia a rota virar query string de novo e o termo for pro lado errado da
    URL, este teste e que acusa."""
    assert "&" not in url_da_busca("BI & Analytics", 1).split("term=")[1]


# --- achar o JSON na pagina -------------------------------------------


def test_acha_o_json_independente_da_ordem_dos_atributos():
    """A busca e posicional de proposito. Supor
    '<script id=... type=...>' nessa ordem foi o que fez a primeira sondagem
    desta reconstrucao nao achar nada numa pagina que TINHA o dado."""
    for invertida in (False, True):
        html = _html({"total": 1, "limit": 12, "offset": 0}, _vagas(1), invertida)
        assert extrair_next_data(html) is not None


def test_pagina_sem_o_json_grita(caplog):
    assert extrair_lista("<html><body>oi</body></html>") is None
    assert "__NEXT_DATA__ não encontrado" in caplog.text


def test_json_quebrado_grita_em_vez_de_estourar(caplog):
    html = '<script id="__NEXT_DATA__" type="application/json">{isso nao e json</script>'
    assert extrair_lista(html) is None
    assert "__NEXT_DATA__ não encontrado" in caplog.text


def test_lista_que_mudou_de_lugar_grita(caplog):
    html = _html({"total": 1, "limit": 12, "offset": 0}, _vagas(1),
                 chave_da_lista="outroNomeQualquer")
    assert extrair_lista(html) is None
    assert "initialJobList" in caplog.text


def test_nao_confunde_as_569_flags_com_as_vagas():
    """A heuristica de "maior lista de dicionarios da pagina" escolheu
    props.pageProps.toggles na sondagem: 569 dicionarios contra 12 vagas. Por
    isso o codigo desce pelo caminho conhecido, e nao pelo tamanho."""
    html = _html({"total": 12, "limit": 12, "offset": 0}, _vagas(12))
    paginacao, vagas = extrair_lista(html)
    assert len(vagas) == 12
    assert all("jobUrl" in v for v in vagas)
    assert paginacao == {"total": 12, "limit": 12, "offset": 0}


# --- o link, que e onde eu ja errei antes -----------------------------


def test_o_link_real_chega_inteiro_no_job():
    """A Solides mandava redirectLink INCOMPLETO e meu teste nao viu porque a
    fixture era minha. Aqui o valor e o que o portal mandou de verdade, e o
    Job tem que preserva-lo byte a byte."""
    job = montar_job(_VAGA_REAL)
    assert job is not None
    assert job.link == _VAGA_REAL["jobUrl"]
    assert job.link.startswith("https://sicredi.gupy.io/job/")


def test_a_falta_de_isRemoteWork_nao_tira_a_modalidade():
    """O portal nao manda mais isRemoteWork (a API mandava). Em
    montar_modalidade ele sempre foi so reforco — workplaceType resolve. Este
    teste existe pra isso ficar provado, e nao suposto."""
    assert "isRemoteWork" not in _VAGA_REAL
    job = montar_job(_VAGA_REAL)
    assert job.modalidade == "Presencial"
    assert job.local == "Campo Grande, Mato Grosso do Sul"
    assert job.publicado_em == "2026-10-01"


# --- a paginacao ------------------------------------------------------


class _Resposta:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _Portal:
    """Portal de mentira. `offset_travado` reproduz a armadilha do ?offset=:
    responde 200, manda 12 vagas e deixa o offset em 0 pra sempre."""

    def __init__(self, total: int, por_pagina: int = 12, offset_travado: bool = False,
                 status: int = 200, corpo: str | None = None):
        self.total = total
        self.por_pagina = por_pagina
        self.offset_travado = offset_travado
        self.status = status
        self.corpo = corpo
        self.pedidos: list[str] = []

    def get(self, url, timeout=None, headers=None):
        self.pedidos.append(url)
        if self.status != 200:
            return _Resposta(self.status, "")
        if self.corpo is not None:
            return _Resposta(200, self.corpo)
        pagina = int(url.split("?page=")[1]) if "?page=" in url else 1
        offset = 0 if self.offset_travado else (pagina - 1) * self.por_pagina
        restante = max(0, self.total - (pagina - 1) * self.por_pagina)
        quantidade = min(self.por_pagina, restante)
        corpo = _html(
            {"total": self.total, "limit": self.por_pagina, "offset": offset},
            _vagas(quantidade, prefixo=f"p{pagina}-"),
        )
        return _Resposta(200, corpo)


@pytest.fixture
def portal(monkeypatch):
    def instalar(p: _Portal) -> _Portal:
        monkeypatch.setattr(gupy, "requests", types.SimpleNamespace(get=p.get))
        monkeypatch.setattr(gupy.time, "sleep", lambda _: None)
        return p
    return instalar


def test_le_as_paginas_ate_o_total(portal):
    p = portal(_Portal(total=30))
    vagas = gupy.GupyScraper(["analista de dados"]).buscar_vagas()
    assert len(vagas) == 30
    assert len(p.pedidos) == 3
    assert p.pedidos[1].endswith("?page=2")
    # vagas de paginas diferentes, nao a mesma tres vezes
    assert len({v.link for v in vagas}) == 30


def test_total_zero_para_na_primeira(portal):
    p = portal(_Portal(total=0))
    assert gupy.GupyScraper(["termo que nao existe"]).buscar_vagas() == []
    assert len(p.pedidos) == 1


def test_offset_que_nao_anda_para_a_paginacao_e_avisa(portal, caplog):
    """A armadilha medida: ?offset=12 responde 200 com 12 vagas e offset 0.
    Sem esta guarda o scraper leria a pagina 1 oito vezes por termo achando
    que avancava, e o log nao diria nada."""
    p = portal(_Portal(total=100, offset_travado=True))
    vagas = gupy.GupyScraper(["analista de dados"]).buscar_vagas()
    assert len(vagas) == 12
    assert len(p.pedidos) == 2
    assert "devolveu offset" in caplog.text


def test_status_ruim_avisa_que_nao_e_busca_vazia(portal, caplog):
    portal(_Portal(total=100, status=404))
    assert gupy.GupyScraper(["analista de dados"]).buscar_vagas() == []
    assert "não é busca vazia" in caplog.text


def test_pagina_sem_json_no_meio_da_paginacao_grita_e_para(portal, caplog):
    portal(_Portal(total=100, corpo="<html>manutenção</html>"))
    assert gupy.GupyScraper(["analista de dados"]).buscar_vagas() == []
    assert "__NEXT_DATA__ não encontrado" in caplog.text


def test_respeita_o_teto_de_vagas_por_termo(portal):
    p = portal(_Portal(total=MAX_VAGAS_POR_TERMO + 500))
    vagas = gupy.GupyScraper(["analista de dados"]).buscar_vagas()
    assert len(vagas) == MAX_VAGAS_POR_TERMO
    assert len(p.pedidos) == MAX_VAGAS_POR_TERMO // 12


def test_usa_o_limit_que_o_portal_declara_e_nao_o_palpite(portal):
    """POR_PAGINA_PADRAO e so chute inicial: quem decide e pagination.limit.
    Se o portal passar a mandar 24 por pagina, a conta de quando parar tem que
    acompanhar — senao o scraper pede paginas que nao existem ou para cedo."""
    assert POR_PAGINA_PADRAO == 12
    p = portal(_Portal(total=48, por_pagina=24))
    vagas = gupy.GupyScraper(["analista de dados"]).buscar_vagas()
    assert len(vagas) == 48
    assert len(p.pedidos) == 2


def test_erro_de_rede_nao_derruba_o_ciclo(portal, caplog):
    class _Explode(_Portal):
        def get(self, url, timeout=None, headers=None):
            self.pedidos.append(url)
            raise OSError("conexão caiu")

    portal(_Explode(total=100))
    assert gupy.GupyScraper(["analista de dados"]).buscar_vagas() == []
    assert "Erro ao buscar" in caplog.text
