"""Solides pela API: o mapeamento de campo, que e onde mora o risco da troca.

MEDIDO (2026-08-29): o scraper anterior abria navegador e raspava HTML, lendo
3 paginas de 10 = teto de 30 vagas por termo, em ~7 minutos de ciclo. A API
responde, pro mesmo termo "analista de dados":

    {"data": {"count": 205, "totalPages": 21}}

E pagina de verdade -- conferido comparando os ids:
    page 1 x page 2: 1 id em comum de 10   (ordenacao instavel, nao repeticao)
    page 2 x page 3: 0
    page 1 x page 3: 0
    29 ids distintos em 3 paginas          (seriam ~30 se paginasse perfeito)
    page 20 -> 10 vagas | page 21 -> 5 | page 22 -> 0   = 205, o count exato

O QUE ESTES TESTES GUARDAM: a conversao de um item da API num Job. Mapear
campo errado nao quebra nada -- so muda em silencio o que e aprovado.

O item de exemplo e a RESPOSTA REAL, copiada da sondagem.
"""

import logging
from datetime import date, timedelta

import pytest

from core.job import Job
from core.perfis import PERFIL_BR
from scrapers import solides
from scrapers.solides import (
    DIAS_PARA_PARAR,
    montar_job,
    montar_local,
    montar_modalidade,
    pagina_toda_antiga,
)

VAGA_API = {
    "id": 912529,
    "title": "Analista de Dados",
    "companyName": "SOMA SOLUTION",
    "city": {"id": 4378, "name": "Chapecó", "state_id": 22},
    "state": {"id": 22, "name": "Santa Catarina", "code": "SC"},
    "jobType": "presencial",
    "homeOffice": False,
    "createdAt": "2026-08-28",
    "redirectLink": "https://somasolution.solides.jobs/vacancies/912529?origem=portal",
    "seniority": [{"id": 4, "name": "Junior", "level": None}],
    "description": "<h2>Analista de Dados</h2>",
}


def test_converte_a_vaga_real_da_api():
    job = montar_job(VAGA_API)
    assert job.titulo == "Analista de Dados"
    assert job.empresa == "SOMA SOLUTION"
    assert job.local == "Chapecó - SC"
    assert job.modalidade == "Presencial"
    assert job.publicado_em == "2026-08-28"
    assert job.site == "Solides"


def test_usa_a_sigla_e_nao_o_nome_do_estado():
    """A Solides entrega state.code ("SC") pronto -- diferente da Gupy, que so
    da o nome por extenso. Sigla e o caminho mais curto na conferencia de UF.
    """
    assert montar_local(VAGA_API).endswith(" - SC")


def test_data_ja_vem_no_formato_certo():
    """createdAt vem como "2026-08-28", sem hora -- ao contrario da Gupy, que
    manda ISO completo e precisa de corte."""
    job = montar_job(VAGA_API)
    assert job.publicado_em_legivel == "28/08/2026"
    assert job.publicacao_antiga is False


@pytest.mark.parametrize("jobtype, home, esperado", [
    ("presencial", False, "Presencial"),
    ("hibrido", False, "Híbrido"),
    ("remoto", True, "Remoto"),
    ("PRESENCIAL", False, "Presencial"),
    ("", True, "Remoto"),        # so homeOffice preenchido
    ("", False, ""),             # nenhum dos dois: nao chuta
    ("qualquer coisa", False, ""),
])
def test_modalidade_traduzida(jobtype, home, esperado):
    assert montar_modalidade({"jobType": jobtype, "homeOffice": home}) == esperado


def test_local_com_campo_faltando():
    assert montar_local({"city": {"name": "Recife"}, "state": {}}) == "Recife"
    assert montar_local({"city": {}, "state": {"code": "CE"}}) == "CE"
    assert montar_local({}) == "Não informado"


@pytest.mark.parametrize("faltando", ["title", "redirectLink"])
def test_vaga_sem_o_essencial_e_descartada(faltando):
    assert montar_job({**VAGA_API, faltando: ""}) is None


# ------------- o mapeamento tem que respeitar as regras de negocio -------------

@pytest.mark.parametrize("cidade, sigla, jobtype, aprovada", [
    ("Fortaleza", "CE", "presencial", True),
    ("Recife", "PE", "presencial", True),
    ("Chapecó", "SC", "presencial", False),        # fora das 9 cidades
    ("São Paulo", "SP", "hibrido", False),
    ("Curitiba", "PR", "remoto", True),            # Brasil remoto de qualquer lugar
    ("Campina Grande", "PR", "presencial", False), # HOMONIMA: a do Parana
    ("Campina Grande", "PB", "presencial", True),  # a de verdade
    ("VITORIA", "ES", "presencial", False),        # a API as vezes manda em CAIXA ALTA
])
def test_o_local_montado_respeita_as_regras(cidade, sigla, jobtype, aprovada):
    job = montar_job({
        **VAGA_API,
        "title": "Analista de Dados",
        "city": {"name": cidade},
        "state": {"code": sigla},
        "jobType": jobtype,
        "redirectLink": f"https://x.solides.jobs/vacancies/{cidade}{sigla}{jobtype}",
    })
    assert job.combina_com(PERFIL_BR.regras) is aprovada


def test_o_job_montado_e_um_job_de_verdade():
    """Contrato com o resto do sistema: dedup, score e notificacao esperam Job."""
    job = montar_job(VAGA_API)
    assert isinstance(job, Job)
    assert job.id and job.chave_secundaria
    assert job.pontuar_relevancia(PERFIL_BR.regras) >= 0


# --------------------- onde parar de paginar (medido) ---------------------

HOJE = date(2026, 8, 30)


def _pagina(*idades_em_dias):
    """Uma pagina da API, com vagas das idades dadas."""
    return [{"createdAt": (HOJE - timedelta(days=d)).isoformat()} for d in idades_em_dias]


def test_pagina_com_vaga_nova_nao_para():
    """Basta UMA vaga dentro do limite pra valer a pena continuar."""
    assert pagina_toda_antiga(_pagina(90, 60, 3), DIAS_PARA_PARAR, HOJE) is False


def test_pagina_toda_velha_para():
    assert pagina_toda_antiga(_pagina(45, 60, 90), DIAS_PARA_PARAR, HOJE) is True


def test_no_limite_exato_ainda_nao_para():
    """Vaga com exatamente 30 dias ainda conta -- e o mesmo limiar que
    Job.publicacao_antiga usa pra marcar "pode ja estar preenchida"."""
    assert pagina_toda_antiga(_pagina(DIAS_PARA_PARAR), DIAS_PARA_PARAR, HOJE) is False
    assert pagina_toda_antiga(_pagina(DIAS_PARA_PARAR + 1), DIAS_PARA_PARAR, HOJE) is True


@pytest.mark.parametrize("itens", [
    [],                                    # pagina vazia
    [{"createdAt": ""}],                   # sem data
    [{"createdAt": "sei la"}],             # data invalida
    [{"outro_campo": 1}],                  # campo ausente
])
def test_sem_data_legivel_nao_para(itens):
    """Sem data nao ha o que concluir. Parar por engano custa VAGA; continuar
    por engano custa uma requisicao. Erra pro lado barato."""
    assert pagina_toda_antiga(itens, DIAS_PARA_PARAR, HOJE) is False


def test_data_com_hora_junto_e_lida():
    """A Solides manda so a data, mas nao custa aguentar ISO completo."""
    itens = [{"createdAt": "2026-01-01T10:00:00.000Z"}]
    assert pagina_toda_antiga(itens, DIAS_PARA_PARAR, HOJE) is True


def test_o_limite_bate_com_o_do_filtro():
    """MEDIDO: parar em 30 dias custa 4,8 requisicoes por termo, praticamente
    o mesmo que o teto fixo de 15 paginas (4,6) -- mas le fundo onde ha vaga
    nova e sai cedo onde o termo e parado.

    30 e tambem o limiar de Job.publicacao_antiga: alem disso, a vaga ja
    ganharia o aviso de "pode ja estar preenchida" e sairia do alerta
    imediato. Ler mais fundo seria buscar o que o filtro desprioriza.
    """
    from core.job import DIAS_PARA_PUBLICACAO_ANTIGA
    assert DIAS_PARA_PARAR == DIAS_PARA_PUBLICACAO_ANTIGA


# ============ o portal novo: RSC no HTML, sem API (08/09) ============
#
# A API foi aposentada (403 "Missing Authentication Token" de tres lugares
# diferentes, inclusive de dentro da pagina do portal). O portal novo entrega
# as vagas no HTML, dentro de blocos self.__next_f.push do Next.js, com os
# MESMOS nomes de campo -- por isso os testes de montar_job acima nao mudaram
# uma linha.
#
# O trecho abaixo e REAL, capturado do portal em 08/09 e so encurtado.

import json as _json

_VAGA_RSC = {
    "killerQuestions": [],
    "id": 917373,
    "title": "Gerente de RH (foco BP)",
    "description": "$1e",
    "currentState": "em_andamento",
    "companyName": "OPEN LABS S.A.",
    "state": {"id": 19, "name": "Rio de Janeiro", "code": "RJ"},
    "city": {"id": 5564, "name": "Rio de Janeiro"},
    "jobType": "presencial",
    "homeOffice": False,
    "createdAt": "2026-09-05",
    "redirectLink": "https://openlabs.solides.jobs/vacancies/917373",
}


def _html(vagas, count=None, lixo_antes=True):
    """Monta um HTML como o do portal: as vagas escapadas dentro de um bloco
    RSC. O 'lixo antes' existe porque no portal real o bloco vem no meio de
    muito outro conteudo."""
    corpo = _json.dumps(vagas, ensure_ascii=False, separators=(",", ":"))
    if count is not None:
        corpo = '{"data":{"data":' + corpo + ',"count":' + str(count) + "}}"
    literal = _json.dumps("2:" + corpo, ensure_ascii=False)
    inicio = "<html><body><div>Vagas | Sólides</div>" if lixo_antes else ""
    return f'{inicio}<script>self.__next_f.push([1,{literal}])</script></body></html>'


def _vagas(n, idade_em_dias=1):
    dia = (HOJE - timedelta(days=idade_em_dias)).isoformat()
    return [dict(_VAGA_RSC, id=900000 + i, createdAt=dia,
                 redirectLink=f"https://x.solides.jobs/vacancies/{900000 + i}")
            for i in range(n)]


# ---------------------------- slug e rota ----------------------------

@pytest.mark.parametrize("termo, esperado", [
    ("analista de dados", "analista-de-dados"),
    ("Power BI", "power-bi"),
    ("inteligência de mercado", "inteligencia-de-mercado"),
    ("BI & Analytics Analyst", "bi-analytics-analyst"),
    ("  sql  ", "sql"),
])
def test_slug_do_termo(termo, esperado):
    """A rota do portal é /vagas/<slug>/todas. Acento ou espaço que escape aqui
    vira 404 silencioso, que o scraper leria como fonte fora do ar."""
    assert solides.slug_do_termo(termo) == esperado


def test_url_da_busca_pagina_1_nao_leva_query():
    assert solides.url_da_busca("analista de dados", 1).endswith(
        "/vagas/analista-de-dados/todas")
    assert solides.url_da_busca("analista de dados", 3).endswith(
        "/vagas/analista-de-dados/todas?page=3")


# -------------------------- extrair do HTML --------------------------

def test_extrai_as_vagas_do_bloco_rsc():
    achadas = solides.extrair_vagas(_html([_VAGA_RSC]))
    assert len(achadas) == 1
    assert achadas[0]["title"] == "Gerente de RH (foco BP)"
    assert achadas[0]["state"]["code"] == "RJ"


def test_a_vaga_extraida_vira_um_job_pelo_mesmo_montar_job():
    """O ponto da reconstrução: os nomes de campo não mudaram, então montar_job
    e seus testes continuam valendo sem tocar em nada."""
    job = montar_job(solides.extrair_vagas(_html([_VAGA_RSC]))[0])
    assert job.titulo == "Gerente de RH (foco BP)"
    assert job.local == "Rio de Janeiro - RJ"
    assert job.modalidade == "Presencial"
    assert job.publicado_em == "2026-09-05"
    assert job.site == "Solides"


def test_html_sem_bloco_rsc_GRITA_no_log(caplog):
    """A diferença entre 'não tem vaga' e 'não sei mais ler' é a coisa mais
    importante deste arquivo. Confundir as duas fez a fonte cair de 400 para 70
    vagas sem ninguém perceber, em 01/09."""
    with caplog.at_level(logging.ERROR, logger=solides.logger.name):
        assert solides.extrair_vagas("<html><body>oi</body></html>", "x") == []
    assert any("portal mudou" in r.message for r in caplog.records)


def test_bloco_rsc_com_formato_desconhecido_tambem_GRITA(caplog):
    """Há dado de vaga no payload, mas a lista não sai: formato mudou."""
    quebrado = '<script>self.__next_f.push([1,"2:{\\"companyName\\":\\"X\\"}"])</script>'
    with caplog.at_level(logging.ERROR, logger=solides.logger.name):
        assert solides.extrair_vagas(quebrado, "x") == []
    assert any("formato do payload mudou" in r.message for r in caplog.records)


def test_pagina_de_verdade_sem_vaga_nao_grita(caplog):
    """Bloco RSC existe e é legível, só não tem vaga: é busca vazia mesmo,
    e não pode virar erro no log."""
    with caplog.at_level(logging.ERROR, logger=solides.logger.name):
        assert solides.extrair_vagas(_html([]), "x") == []
    assert not caplog.records


def test_nao_confunde_outra_lista_da_pagina_com_a_de_vagas():
    """A página traz várias listas (filtros, cidades, empresas). O extrator pega
    a MAIOR — então uma lista maior que a de vagas tem que ser descartada por
    não ter id+title, senão o scraper monta Job de lixo.

    Este teste existe porque a MUTAÇÃO encontrou o buraco: apagar a validação
    de title não derrubava nenhum teste."""
    iscas = [{"id": i, "nome": f"Cidade {i}"} for i in range(50)]   # sem title
    import json as _j
    corpo = ("2:" + _j.dumps({"cidades": iscas, "vagas": [_VAGA_RSC]},
                             ensure_ascii=False, separators=(",", ":")))
    html = ("<script>self.__next_f.push([1,"
            + _j.dumps(corpo, ensure_ascii=False) + "])</script>")

    achadas = solides.extrair_vagas(html, "x")
    assert len(achadas) == 1
    assert achadas[0]["title"] == "Gerente de RH (foco BP)"


def test_le_o_total_declarado_pelo_portal():
    assert solides.total_de_vagas(_html(_vagas(3), count=204)) == 204
    assert solides.total_de_vagas(_html(_vagas(3))) is None


# ---------------- o laço de páginas contra o portal novo ----------------

class _RespostaHtml:
    def __init__(self, texto, status=200):
        self.status_code = status
        self.text = texto


def _portal_falso(monkeypatch, respostas):
    """Finge o portal: uma resposta por página, na ordem."""
    fila = list(respostas)
    vistas = []

    def get(url, timeout=None, headers=None):
        vistas.append(url)
        if not fila:
            return _RespostaHtml(_html([]))
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(solides.requests, "get", get)
    monkeypatch.setattr(solides.time, "sleep", lambda _: None)
    return vistas


def _rodar(monkeypatch, respostas):
    vistas = _portal_falso(monkeypatch, respostas)
    s = solides.SolidesScraper(["analista de dados"])
    s._incompletos = []
    s._registrar_incompletos = True
    achadas = s._buscar_termo("analista de dados")
    return achadas, s._incompletos, vistas


def test_pagina_por_pagina_ate_o_total_declarado(monkeypatch):
    """28 vagas em páginas de 14 = 2 páginas. Não pode pedir a terceira."""
    cheia = _RespostaHtml(_html(_vagas(14), count=28))
    achadas, _, vistas = _rodar(monkeypatch, [cheia, cheia])
    assert len(achadas) == 28
    assert len(vistas) == 2
    assert vistas[1].endswith("?page=2")


def test_para_por_idade_antes_de_esgotar_as_paginas(monkeypatch):
    """Mesmo critério da versão anterior: a lista vem da mais nova pra mais
    velha, então página toda velha significa que daqui pra frente só piora."""
    nova = _RespostaHtml(_html(_vagas(14, idade_em_dias=1), count=999))
    velha = _RespostaHtml(_html(_vagas(14, idade_em_dias=90), count=999))
    achadas, _, vistas = _rodar(monkeypatch, [nova, velha, nova])
    assert len(vistas) == 2
    assert len(achadas) == 28


def test_status_nao_200_marca_o_termo_como_incompleto(monkeypatch):
    _, incompletos, _ = _rodar(monkeypatch, [_RespostaHtml("", status=403)])
    assert incompletos == ["analista de dados"]


def test_403_no_meio_da_paginacao_tambem_marca(monkeypatch):
    """Foi assim que a API velha morreu: 403 a partir de certa página."""
    cheia = _RespostaHtml(_html(_vagas(14), count=999))
    achadas, incompletos, _ = _rodar(monkeypatch, [cheia, _RespostaHtml("", status=403)])
    assert len(achadas) == 14
    assert incompletos == ["analista de dados"]


def test_erro_de_rede_marca_o_termo(monkeypatch):
    import requests as _req
    _, incompletos, _ = _rodar(monkeypatch, [_req.exceptions.ConnectionError("caiu")])
    assert incompletos == ["analista de dados"]


def test_pagina_1_sem_vaga_marca_o_termo(monkeypatch):
    """Zero na primeira página não prova ausência de vaga — medido na API velha
    em 01/09, e vale igual aqui. Vai pra segunda passada."""
    _, incompletos, _ = _rodar(monkeypatch, [_RespostaHtml(_html([]))])
    assert incompletos == ["analista de dados"]


def test_termo_que_terminou_bem_nao_e_marcado(monkeypatch):
    """Leu tudo que existia: não há o que repetir."""
    _, incompletos, _ = _rodar(monkeypatch, [_RespostaHtml(_html(_vagas(5), count=5))])
    assert incompletos == []


def test_a_trava_de_paginas_nao_deixa_lacar_infinito(monkeypatch):
    """Se o portal mentir o total e nunca envelhecer, MAX_PAGINAS segura."""
    cheia = _RespostaHtml(_html(_vagas(14), count=99999))
    _, _, vistas = _rodar(monkeypatch, [cheia] * (solides.MAX_PAGINAS + 5))
    assert len(vistas) == solides.MAX_PAGINAS


def test_nao_marca_o_mesmo_termo_duas_vezes():
    s = solides.SolidesScraper(["x"])
    s._incompletos = []
    s._registrar_incompletos = True
    s._anotar_incompleto("x")
    s._anotar_incompleto("x")
    assert s._incompletos == ["x"]


# ------------- segunda passada: o zero que era mentira -------------


class SolidesFalso(solides.SolidesScraper):
    """Troca so a ida na rede; o resto do fluxo e o de producao."""

    def __init__(self, respostas):
        super().__init__(termos_busca=list(respostas))
        self.respostas = respostas      # {termo: [ [1a vez], [2a vez] ]}
        self.chamadas = []

    def _buscar_termo(self, termo):
        self.chamadas.append(termo)
        assert len(self.chamadas) <= 50, (
            "laço infinito: a segunda passada está se re-agendando"
        )
        fila = self.respostas.get(termo, [[]])
        achadas = fila.pop(0) if fila else []
        if not achadas and getattr(self, "_registrar_incompletos", False):
            self._incompletos.append(termo)
        return achadas


def _job(n):
    return Job(titulo=f"Analista de Dados {n}", empresa="Empresa",
               local="Recife - PE", link=f"https://solides.jobs/{n}", site="Solides")


def test_sem_termo_zerado_nao_ha_segunda_passada():
    s = SolidesFalso({"analista de dados": [[_job(1)]]})
    s.buscar_vagas()
    assert s.chamadas == ["analista de dados"]


def test_repete_so_o_termo_que_voltou_zero():
    """MEDIDO 01/09: a API devolveu count=0 pra 'analista de dados' num ciclo e
    209 vagas minutos depois. Como count=0 para a paginação no primeiro
    request, um zero falso custa o TERMO INTEIRO -- foi assim que a fonte caiu
    de ~400 para 70 vagas sem disparar alerta nenhum."""
    s = SolidesFalso({
        "analista de dados": [[], [_job(1), _job(2)]],
        "power bi": [[_job(3)]],
    })
    vagas = s.buscar_vagas()

    assert s.chamadas == ["analista de dados", "power bi", "analista de dados"]
    assert {v.id for v in vagas} == {_job(1).id, _job(2).id, _job(3).id}


def test_a_segunda_passada_nao_repete_a_si_mesma():
    s = SolidesFalso({"analista de dados": [[], []], "power bi": [[], []]})
    s.buscar_vagas()
    assert len(s.chamadas) == 4      # 2 da primeira + 2 repeticoes, e para


def test_so_devolve_vaga_inedita_no_ciclo():
    """Sem isto, o contador que decide se a passada se paga contaria vaga que o
    ciclo ja tinha por outro termo."""
    s = SolidesFalso({
        "analista de dados": [[], [_job(1), _job(9)]],
        "power bi": [[_job(1)]],
    })
    ids = [v.id for v in s.buscar_vagas()]
    assert ids.count(_job(1).id) == 1
    assert _job(9).id in ids


def test_cada_ciclo_recomeca_a_lista():
    s = SolidesFalso({"analista de dados": [[], []]})
    s.buscar_vagas()
    assert s._incompletos == ["analista de dados"]
    s.respostas = {"analista de dados": [[_job(1)]]}
    s.buscar_vagas()
    assert s._incompletos == []


