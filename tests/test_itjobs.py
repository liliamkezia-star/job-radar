"""itjobs.pt: a leitura do schema.org, que e onde mora o risco desta fonte.

POR QUE ESTA FONTE EXISTE. Medicao de 03/10/2026 nos cinco sites portugueses
que a usuaria pediu pra avaliar: o itjobs rendeu 2 aprovadas de 52 (3,8%,
acima da Gupy e da Solides) e os outros quatro renderam ZERO. Os quatro falham
pelo mesmo motivo — sao boards generalistas e de BPO.

O DADO AQUI E REAL, capturado da pagina em 03/10. Isso nao e preciosismo: o
link da Solides ficou quebrado 24 dias porque a fixture do teste tinha um
redirectLink completo que EU escrevi, e o site mandava incompleto. Fixture
inventada testa a imaginacao de quem escreveu.

A ARMADILHA que mais importa aqui tambem e dado real: 'Digital Marketing
Specialist' aparece nas paginas 1, 2 e 3 da rota /emprego/remote, e o JSON-LD
dele NAO tem jobLocationType — enquanto o da vaga de verdade tem TELECOMMUTE.
Estar na rota de remoto nao prova que a vaga e remota. Tem teste pra isso.
"""
import json
from datetime import date

import pytest

from core.perfis import PERFIL_INTL
from scrapers import itjobs
from scrapers.itjobs import (
    MAX_PAGINAS,
    combina_com_algum_termo,
    e_remota,
    expirada,
    jobposting,
    local_da_vaga,
    montar_job,
    titulo_do_slug,
    ultima_pagina_declarada,
    url_da_pagina,
    vagas_da_listagem,
)

# --- dado real, capturado em 03/10/2026 --------------------------------

# A vaga de verdade: remota, com TELECOMMUTE.
JSONLD_REAL = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "C# .NET Developer (French Speaker)",
    "datePosted": "2026-10-02",
    "validThrough": "2026-11-01T12:48:13+00:00",
    "jobLocationType": "TELECOMMUTE",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {
        "@type": "Organization",
        "name": "Dellent",
        "sameAs": "http://www.dellentconsulting.com",
    },
    "jobLocation": [
        {"@type": "Place", "address": {"@type": "PostalAddress", "postalCode": "4000-008"}}
    ],
}

# O anuncio fixo: aparece nas paginas 1, 2 e 3 da rota de remoto, e NAO tem
# jobLocationType. Se a modalidade saisse da rota em vez do dado, esta vaga
# seria notificada como remota sem ser.
JSONLD_ANUNCIO_FIXO = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Digital Marketing Specialist",
    "datePosted": "2026-09-29",
    "validThrough": "2026-10-29T13:49:18+00:00",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {"@type": "Organization", "name": "CodeOne",
                           "sameAs": "http://www.codeone.pt"},
    "jobLocation": [
        {"@type": "Place", "address": {"@type": "PostalAddress", "postalCode": "4000-008"}}
    ],
}

LINK_REAL = "https://www.itjobs.pt/oferta/517636/c-net-developer-french-speaker"

# Links reais vistos na listagem, com a paginacao que a pagina declara.
HTML_LISTAGEM = """
<html><body>
  <div class="list">
    <a href="/oferta/517529/digital-marketing-specialist">Digital Marketing Specialist</a>
    <a href="/oferta/517636/c-net-developer-french-speaker">C# .NET Developer (French Speaker)</a>
    <a href="/oferta/517552/data-analyst"><h3>Data Analyst</h3></a>
    <a href="/empresa/dellent">Dellent</a>
    <a href="/curso/7540/icp-acc-agile-coach-certification">Curso</a>
  </div>
  <nav>
    <a href="?page=2">2</a><a href="?page=3">3</a>
    <a href="?page=35">35</a><a href="?page=36">36</a>
  </nav>
</body></html>
"""


def _pagina_de_vaga(jsonld: dict) -> str:
    return ('<html><head><script type="application/ld+json">'
            + json.dumps(jsonld)
            + "</script></head><body>oi</body></html>")


# --- a URL e a listagem ------------------------------------------------


def test_primeira_pagina_nao_leva_page():
    assert url_da_pagina(1) == "https://www.itjobs.pt/emprego/remote"
    assert url_da_pagina(2).endswith("?page=2")


def test_le_as_vagas_e_ignora_empresa_e_curso():
    """A pagina tem link de /empresa/ e /curso/ junto. So /oferta/N/ e vaga."""
    vagas = vagas_da_listagem(HTML_LISTAGEM)
    assert len(vagas) == 3
    links = {l for _, l in vagas}
    assert "https://www.itjobs.pt/oferta/517552/data-analyst" in links
    assert not any("/empresa/" in l or "/curso/" in l for l in links)


def test_titulo_cai_pro_slug_quando_a_ancora_embrulha_outro_elemento():
    """<a href=...><h3>Data Analyst</h3></a> nao tem texto direto. O slug E o
    titulo em kebab-case, entao serve de reserva — reserva declarada, nao
    adivinhacao de marcacao.

    E vem em MINUSCULA, de proposito nao corrigido: este titulo serve so pra
    cruzar com os termos de busca, e o cruzamento normaliza caixa e acento. O
    titulo que chega no Telegram vem do JSON-LD da pagina da vaga, nunca
    daqui. Title-case automatico aqui estragaria sigla ("c net developer" ->
    "C Net Developer") pra enfeitar um texto que ninguem le."""
    vagas = dict((l, t) for t, l in vagas_da_listagem(HTML_LISTAGEM))
    assert vagas["https://www.itjobs.pt/oferta/517552/data-analyst"] == "data analyst"
    # o cruzamento com termo nao se incomoda com a caixa
    assert combina_com_algum_termo("data analyst", ["Data Analyst"])
    # e o titulo final vem do JSON-LD, nao da listagem
    job = montar_job("data analyst", LINK_REAL, JSONLD_REAL, hoje=date(2026, 10, 3))
    assert job.titulo == "C# .NET Developer (French Speaker)"


def test_titulo_do_slug():
    assert titulo_do_slug("/oferta/517552/data-analyst") == "data analyst"


def test_le_a_ultima_pagina_que_o_site_declara():
    assert ultima_pagina_declarada(HTML_LISTAGEM) == 36


def test_pagina_sem_paginacao_devolve_none():
    assert ultima_pagina_declarada("<html>nada</html>") is None


# --- o JSON-LD ---------------------------------------------------------


def test_acha_o_jobposting_na_pagina_real():
    jp = jobposting(_pagina_de_vaga(JSONLD_REAL))
    assert jp is not None
    assert jp["title"] == "C# .NET Developer (French Speaker)"


def test_acha_o_jobposting_dentro_de_lista_e_de_grafo():
    """schema.org vem de tres formas na pratica: objeto, lista e @graph.
    Suportar so uma e supor como o site escreve."""
    como_lista = [{"@type": "Organization", "name": "x"}, JSONLD_REAL]
    como_grafo = {"@context": "https://schema.org", "@graph": [JSONLD_REAL]}
    for forma in (como_lista, como_grafo):
        jp = jobposting(_pagina_de_vaga(forma))
        assert jp is not None and jp["title"] == JSONLD_REAL["title"]


def test_pagina_sem_jsonld_devolve_none():
    assert jobposting("<html><body>sem dado estruturado</body></html>") is None


def test_jsonld_quebrado_nao_estoura():
    html = '<script type="application/ld+json">{isso nao e json</script>'
    assert jobposting(html) is None


# --- remoto: a armadilha do anuncio fixo -------------------------------


def test_telecommute_e_remoto():
    assert e_remota(JSONLD_REAL) is True


def test_anuncio_fixo_da_rota_de_remoto_nao_e_remoto():
    """O dado real: ele esta na rota /emprego/remote e nao tem
    jobLocationType. Se a modalidade viesse da rota, ele entraria como
    remoto sem ser."""
    assert "jobLocationType" not in JSONLD_ANUNCIO_FIXO
    assert e_remota(JSONLD_ANUNCIO_FIXO) is False


def test_o_anuncio_fixo_reprova_no_filtro_internacional():
    """A consequencia que importa: a regra internacional e SO remoto. Sem
    modalidade confirmada, ele nao chega no Telegram."""
    job = montar_job("Digital Marketing Specialist",
                     "https://www.itjobs.pt/oferta/517529/digital-marketing-specialist",
                     JSONLD_ANUNCIO_FIXO, hoje=date(2026, 10, 3))
    assert job.modalidade == ""
    assert not job.combina_com(PERFIL_INTL.regras)


# --- local, data e validade -------------------------------------------


def test_local_cai_pra_portugal_quando_o_endereco_nao_diz_a_cidade():
    """Formato REAL capturado: o endereco so trazia postalCode. "Portugal"
    sozinho e o que o filtro internacional precisa (mercado lusofono), entao
    a reserva nunca sai errada."""
    assert local_da_vaga(JSONLD_REAL) == "Portugal"


def test_local_usa_a_cidade_quando_ela_vem():
    jp = dict(JSONLD_REAL)
    jp["jobLocation"] = [{"@type": "Place", "address": {
        "@type": "PostalAddress", "addressLocality": "Lisboa", "postalCode": "1000-001"}}]
    assert local_da_vaga(jp) == "Lisboa, Portugal"


def test_vaga_expirada_nao_e_devolvida():
    """validThrough real: 2026-11-01. Em 02/11 o anuncio encerrou, e o
    proprio site diz isso — nenhuma outra fonte do projeto tem esse campo."""
    assert expirada(JSONLD_REAL, hoje=date(2026, 11, 2)) is True
    assert montar_job("x", LINK_REAL, JSONLD_REAL, hoje=date(2026, 11, 2)) is None


def test_vaga_dentro_da_validade_e_devolvida():
    assert expirada(JSONLD_REAL, hoje=date(2026, 10, 3)) is False
    assert montar_job("x", LINK_REAL, JSONLD_REAL, hoje=date(2026, 10, 3)) is not None


def test_data_ilegivel_nao_conta_como_expirada():
    """Na duvida, mostra — mesma regra do scrapers/senior.py. Tratar data
    ilegivel como expirada esconderia vaga boa em silencio."""
    jp = dict(JSONLD_REAL, validThrough="qualquer coisa")
    assert expirada(jp, hoje=date(2026, 12, 31)) is False


def test_sem_validthrough_nao_conta_como_expirada():
    jp = {k: v for k, v in JSONLD_REAL.items() if k != "validThrough"}
    assert expirada(jp, hoje=date(2030, 1, 1)) is False


# --- o Job montado -----------------------------------------------------


def test_monta_o_job_com_o_dado_real():
    job = montar_job("C# .NET Developer", LINK_REAL, JSONLD_REAL, hoje=date(2026, 10, 3))
    assert job.titulo == "C# .NET Developer (French Speaker)"
    assert job.empresa == "Dellent"
    assert job.local == "Portugal"
    assert job.modalidade == "Remoto"
    assert job.publicado_em == "2026-10-02"
    assert job.site == "ITJobs"


def test_o_link_chega_inteiro():
    """O link da Solides ficou quebrado 24 dias e nenhum teste viu, porque a
    sonda imprimia tudo menos o link e a fixture era minha."""
    job = montar_job("x", LINK_REAL, JSONLD_REAL, hoje=date(2026, 10, 3))
    assert job.link == LINK_REAL


def test_datePosted_vem_sempre_e_cortado_em_dez_caracteres():
    """A base inteira tem data em 57,9% das vagas e a GeekHunter em 0%. Aqui o
    campo e do schema.org, entao vem sempre — mas pode vir com hora."""
    jp = dict(JSONLD_REAL, datePosted="2026-10-02T09:15:00+00:00")
    assert montar_job("x", LINK_REAL, jp, hoje=date(2026, 10, 3)).publicado_em == "2026-10-02"


def test_sem_empresa_nao_inventa_nome():
    jp = {k: v for k, v in JSONLD_REAL.items() if k != "hiringOrganization"}
    assert montar_job("x", LINK_REAL, jp, hoje=date(2026, 10, 3)).empresa == "Não informada"


# --- o cruzamento com os termos ---------------------------------------


def test_cruza_termo_sem_acento_e_sem_caixa():
    assert combina_com_algum_termo("ANALISTA DE DADOS Sênior", ["analista de dados"])
    assert combina_com_algum_termo("Data Analyst", ["data analyst"])


def test_titulo_fora_dos_termos_nao_abre_detalhe():
    """O cruzamento existe pra nao abrir 630 paginas de detalhe por ciclo.
    O site NAO combina termo com remoto: /emprego/remote?q=data devolveu a
    lista sem o q (medido)."""
    assert not combina_com_algum_termo("AI Tech Lead", ["analista de dados", "power bi"])


def test_sem_termo_nenhum_nao_casa_nada():
    assert not combina_com_algum_termo("Data Analyst", [])


# --- a vaga que a medicao aprovou, de ponta a ponta -------------------


def test_a_vaga_real_aprovada_na_medicao_continua_aprovando():
    """Das 52 vagas medidas em 03/10, esta foi a melhor: nota 6."""
    jp = dict(JSONLD_REAL, title="Data Analyst")
    job = montar_job("Data Analyst", "https://www.itjobs.pt/oferta/517552/data-analyst",
                     jp, hoje=date(2026, 10, 3))
    assert job.combina_com(PERFIL_INTL.regras)
    assert job.pontuar_relevancia(PERFIL_INTL.regras) >= 5


# --- o scraper inteiro, com a rede dublada ----------------------------


class _Resposta:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _Site:
    def __init__(self, paginas: dict[str, str]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def get(self, url, timeout=None, headers=None):
        self.pedidos.append(url)
        if url in self.paginas:
            return _Resposta(200, self.paginas[url])
        return _Resposta(404, "")


@pytest.fixture
def site(monkeypatch):
    def instalar(paginas: dict[str, str]) -> _Site:
        s = _Site(paginas)
        import types
        monkeypatch.setattr(itjobs, "requests", types.SimpleNamespace(get=s.get))
        monkeypatch.setattr(itjobs.time, "sleep", lambda _: None)
        return s
    return instalar


def _listagem(links: list[tuple[str, str]], ultima: int) -> str:
    corpo = "".join(f'<a href="{l}">{t}</a>' for t, l in links)
    nav = "".join(f'<a href="?page={n}">{n}</a>' for n in range(2, ultima + 1))
    return f"<html><body>{corpo}<nav>{nav}</nav></body></html>"


def test_para_na_ultima_pagina_declarada(site):
    pagina = _listagem([("Data Analyst", "/oferta/1/data-analyst")], ultima=2)
    s = site({
        "https://www.itjobs.pt/emprego/remote": pagina,
        "https://www.itjobs.pt/emprego/remote?page=2": pagina,
        "https://www.itjobs.pt/oferta/1/data-analyst": _pagina_de_vaga(
            dict(JSONLD_REAL, title="Data Analyst", validThrough="2099-01-01")),
    })
    vagas = itjobs.ITJobsScraper(["data analyst"]).buscar_vagas()
    assert len(vagas) == 1
    listagens = [u for u in s.pedidos if "/emprego/remote" in u]
    assert len(listagens) == 2, listagens


def test_abre_detalhe_so_do_que_casou_com_termo(site):
    pagina = _listagem([("Data Analyst", "/oferta/1/data-analyst"),
                        ("AI Tech Lead", "/oferta/2/ai-tech-lead")], ultima=1)
    s = site({
        "https://www.itjobs.pt/emprego/remote": pagina,
        "https://www.itjobs.pt/oferta/1/data-analyst": _pagina_de_vaga(
            dict(JSONLD_REAL, title="Data Analyst", validThrough="2099-01-01")),
        "https://www.itjobs.pt/oferta/2/ai-tech-lead": _pagina_de_vaga(
            dict(JSONLD_REAL, title="AI Tech Lead", validThrough="2099-01-01")),
    })
    itjobs.ITJobsScraper(["data analyst"]).buscar_vagas()
    assert "https://www.itjobs.pt/oferta/1/data-analyst" in s.pedidos
    assert "https://www.itjobs.pt/oferta/2/ai-tech-lead" not in s.pedidos


def test_grita_quando_a_vaga_perde_o_jsonld(site, caplog):
    """A fonte inteira depende do schema.org. Sem ele sobra titulo e link —
    sem data, sem empresa, sem confirmacao de remoto — e a vaga morreria no
    filtro sem ninguem saber por que. Foi assim que a Solides, a Gupy e a
    GeekHunter morreram neste projeto."""
    pagina = _listagem([("Data Analyst", "/oferta/1/data-analyst")], ultima=1)
    site({
        "https://www.itjobs.pt/emprego/remote": pagina,
        "https://www.itjobs.pt/oferta/1/data-analyst": "<html>sem dado estruturado</html>",
    })
    assert itjobs.ITJobsScraper(["data analyst"]).buscar_vagas() == []
    assert "SEM schema.org/JobPosting" in caplog.text


def test_listagem_fora_do_ar_nao_derruba_o_ciclo(site, caplog):
    site({})
    assert itjobs.ITJobsScraper(["data analyst"]).buscar_vagas() == []
    assert "não é busca vazia" in caplog.text
