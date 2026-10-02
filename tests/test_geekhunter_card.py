"""Leitura do card da GeekHunter depois da mudanca de layout.

POR QUE EXISTE. Em 02/10/2026 a GeekHunter trouxe 21 vagas brutas e aprovou
ZERO. Nenhuma reprovou pelo titulo — o filtro aprovaria todas. Elas morreram
porque o scraper lia local="Nao informado" e modalidade="" em 21 de 21, e sem
cidade nem sinal de remoto a vaga nao passa na regra de localizacao.

Duas causas, as duas medidas na sonda (nao supostas):

  1. a ancora a[href*="/jobs/"] passou a envolver SO o titulo; cidade,
     modalidade e senioridade ficaram no DIV bisavo dela;
  2. a bandeira do Brasil, que marcava a linha de cidade, desapareceu — o
     formato agora e "Cidade, UF, Brasil".

O TEXTO DOS CARDS AQUI E REAL, capturado da pagina em 02/10/2026. Isso nao e
preciosismo: o link da Solides ficou quebrado 24 dias porque a fixture do
teste tinha um redirectLink completo que EU escrevi, e o site manda incompleto.
Fixture inventada testa a minha imaginacao, nao o site.
"""
from core.job import Job
from core.perfis import PERFIL_BR
from scrapers.geekhunter import (
    _MAX_NIVEIS_ACIMA,
    _SELETOR_VAGA,
    container_do_card,
    decidir_pelo_status,
    extrair_campos,
    linhas_do_texto,
)

# Capturado em 02/10/2026, termo "analista de dados", pagina 1, card 1.
_CARD_REAL = [
    "Analista de Dados - Presencial /SP",
    "PLENO",
    "PRESENCIAL",
    "São Paulo, SP, Brasil",
]

# A arvore real, de baixo pra cima: <a> e <h3> e <div> com so o titulo, e o
# <div> bisavo com as quatro linhas.
_ARVORE_REAL = [
    [_CARD_REAL[0]],
    [_CARD_REAL[0]],
    [_CARD_REAL[0]],
    _CARD_REAL,
]


class _Elemento:
    """ElementHandle de mentira: so o que container_do_card usa."""

    def __init__(self, linhas: list[str], ancoras_de_vaga: int = 1):
        self.linhas = linhas
        self.ancoras_de_vaga = ancoras_de_vaga
        self.pai: "_Elemento | None" = None

    def inner_text(self) -> str:
        return "\n".join(self.linhas)

    def query_selector(self, seletor: str):
        assert seletor == "xpath=..", seletor
        return self.pai

    def query_selector_all(self, seletor: str):
        assert seletor == _SELETOR_VAGA, seletor
        return [None] * self.ancoras_de_vaga


def _montar(niveis: list[list[str]], ancoras: list[int] | None = None) -> _Elemento:
    """Monta a arvore de baixo pra cima e devolve a ancora (nivel 0)."""
    ancoras = ancoras or [1] * len(niveis)
    elementos = [_Elemento(l, a) for l, a in zip(niveis, ancoras)]
    for filho, pai in zip(elementos, elementos[1:]):
        filho.pai = pai
    return elementos[0]


# --- subir na arvore ---------------------------------------------------


def test_acha_o_container_na_arvore_real():
    container = container_do_card(_montar(_ARVORE_REAL))
    assert container is not None
    assert linhas_do_texto(container.inner_text()) == _CARD_REAL


def test_wrapper_extra_no_meio_nao_quebra():
    """Por isso o codigo SOBE ate achar em vez de fixar o bisavo: um div a
    mais no grid, e fixar o nivel voltaria a zerar tudo em silencio."""
    arvore = [[_CARD_REAL[0]]] * 4 + [_CARD_REAL]
    container = container_do_card(_montar(arvore))
    assert container is not None
    assert linhas_do_texto(container.inner_text()) == _CARD_REAL


def test_nao_aceita_a_lista_inteira_como_container():
    """Se o nivel achado tem mais de uma vaga dentro, ele e a LISTA. Usar o
    texto dele colaria a cidade de uma vaga no titulo da outra — erro pior
    que ficar sem cidade, porque passaria desapercebido no filtro."""
    duas_vagas = _CARD_REAL + ["Analista de BI", "SENIOR", "REMOTO", "Recife, PE, Brasil"]
    ancora = _montar([[_CARD_REAL[0]], duas_vagas], ancoras=[1, 2])
    assert container_do_card(ancora) is None


def test_o_limite_de_niveis_impede_subir_ate_a_pagina_toda():
    """Sem o limite, uma arvore mais funda que o esperado faz a subida chegar
    no <body>. Numa busca com UMA vaga so, a guarda de lista nao salva (o body
    tem uma ancora, nao duas) e o "card" viraria a pagina inteira: titulo
    "GeekHunter", menu de navegacao no meio e cidade do rodape."""
    pagina_toda = [
        "GeekHunter",
        "Entrar",
        "Vagas",
        _CARD_REAL[0],
        "PLENO",
        "PRESENCIAL",
        "São Paulo, SP, Brasil",
        "Belo Horizonte, MG, Brasil",
    ]
    niveis = [[_CARD_REAL[0]]] * (_MAX_NIVEIS_ACIMA + 1) + [pagina_toda]
    ancoras = [1] * len(niveis)
    assert container_do_card(_montar(niveis, ancoras)) is None


def test_desiste_quando_a_ancora_nao_tem_pai():
    assert container_do_card(_Elemento([_CARD_REAL[0]])) is None


# --- ler os campos -----------------------------------------------------


def test_le_titulo_cidade_e_modalidade_do_card_real():
    titulo, local, modalidade = extrair_campos(_CARD_REAL)
    assert titulo == "Analista de Dados - Presencial /SP"
    assert local == "São Paulo, SP, Brasil"
    assert modalidade == "Presencial"


def test_modalidade_em_maiuscula_vira_capitalizada():
    """O site mudou pra maiuscula ("PRESENCIAL"); .lower() no teste de
    pertinencia e .capitalize() na saida continuam dando conta."""
    _, _, modalidade = extrair_campos(["Analista de Dados", "HÍBRIDO"])
    assert modalidade == "Híbrido"


def test_vaga_remota_nao_tem_linha_de_cidade_e_isso_nao_e_falha():
    """Card real (02/10, card 2 da pagina 1): vaga remota vem com TRES linhas,
    sem cidade nenhuma. local="" aqui vira "Nao informado" no Job, e ela passa
    no filtro pela modalidade. Nao e o bug que este arquivo conserta — e por
    isso que a sonda acusou 2 de 10 sem local e nao 0 de 10."""
    titulo, local, modalidade = extrair_campos(["Analista de Dados", "SÊNIOR", "REMOTO"])
    assert (titulo, local, modalidade) == ("Analista de Dados", "", "Remoto")


def test_le_cidade_no_formato_com_hifen():
    """Card real (02/10, card 9): "Santa Cruz do Sul - RS, Brasil". A mesma
    fonte usa DOIS formatos de UF, virgula e hifen. A regra se ancora no pais
    no fim justamente pra nao depender de qual deles veio."""
    _, local, _ = extrair_campos(["Analista de Dados (PowerBI)", "PLENO", "HÍBRIDO",
                                  "Santa Cruz do Sul - RS, Brasil"])
    assert local == "Santa Cruz do Sul - RS, Brasil"


def test_brasil_sozinho_conta_como_local():
    _, local, _ = extrair_campos(["Analista de Dados", "REMOTO", "Brasil"])
    assert local == "Brasil"


def test_linha_com_virgula_sem_o_pais_nao_e_lida_como_local():
    """A linha de local se identifica pelo pais no fim. Sem essa exigencia,
    qualquer linha com virgula ("Dados, BI e Analytics") viraria cidade."""
    _, local, _ = extrair_campos(["Analista de Dados", "Dados, BI e Analytics"])
    assert local == ""


def test_formato_antigo_com_bandeira_continua_funcionando():
    _, local, _ = extrair_campos(["Analista de Dados", "\U0001F1E7\U0001F1F7 Recife, PE"])
    assert local == "Recife, PE"


def test_card_vazio_nao_explode():
    assert extrair_campos([]) == ("", "", "")


# --- o que isso muda no filtro (o motivo de tudo) ----------------------


def _job(local: str, modalidade: str) -> Job:
    return Job(
        titulo="Analista de Dados",
        empresa="Empresa",
        local=local,
        link="https://www.geekhunter.com/pt/empresa/jobs/1",
        site="GeekHunter",
        publicado_em="",
        modalidade=modalidade,
    )


def test_vaga_de_cidade_aceita_agora_passa():
    """Antes do conserto esta mesma vaga chegava ao filtro com
    local="Nao informado" e modalidade="" — e reprovava."""
    assert _job("Recife, PE, Brasil", "Presencial").combina_com(PERFIL_BR.regras)
    assert not _job("Não informado", "").combina_com(PERFIL_BR.regras)


def test_vaga_de_cidade_fora_da_regra_continua_reprovando():
    """O conserto nao pode virar peneira: Sao Paulo presencial esta fora."""
    assert not _job("São Paulo, SP, Brasil", "Presencial").combina_com(PERFIL_BR.regras)


def test_uf_que_contradiz_a_cidade_continua_barrada():
    """"Campina Grande do Sul, PR, Brasil" nao e Campina Grande/PB. O formato
    novo traz a UF, entao a guarda _UF_DA_CIDADE tem com o que trabalhar."""
    assert not _job("Campina Grande do Sul, PR, Brasil", "Presencial").combina_com(
        PERFIL_BR.regras
    )
    # e no formato com hifen, que a mesma fonte tambem usa
    assert not _job("Campina Grande - PR, Brasil", "Presencial").combina_com(
        PERFIL_BR.regras
    )
    # controle: a de verdade continua passando
    assert _job("Campina Grande - PB, Brasil", "Presencial").combina_com(PERFIL_BR.regras)
# --- fim da paginacao x rota morta x falha de verdade ------------------
#
# MEDIDO em 02/10/2026: "analista de dados" declara 10 vagas e &page=2
# responde 404; "desenvolvedor" declara 273, mostra 25 por pagina e tem link
# numerado ate &page=11, com vagas diferentes na 2. Os dois casos passavam
# pelo MESMO caminho (timeout de 15s esperando o seletor) e saiam com o mesmo
# aviso de "pode ter ficado vaga de fora".


def test_404_depois_da_primeira_pagina_e_fim_de_resultado():
    """Termo com uma pagina so. Nao e perda, nao merece aviso."""
    assert decidir_pelo_status(404, 2) == "fim"
    assert decidir_pelo_status(404, 3) == "fim"


def test_404_na_primeira_pagina_e_rota_morta():
    """Aqui nao acabou nada: a busca em si parou de existir. Tem que gritar,
    senao a fonte inteira morre em silencio — foi o que aconteceu com a
    Solides em 01/09 e com a Gupy em 02/10."""
    assert decidir_pelo_status(404, 1) == "rota_mudou"


def test_erro_de_servidor_nao_e_fim_de_resultado():
    """500 e 503 NAO sao fim de pagina. Tratar erro como fim esconderia perda
    exatamente como o aviso falso cansava quem o lia — os dois erros sao a
    mesma doenca, confundir falha com normalidade."""
    for status in (500, 502, 503, 403):
        assert decidir_pelo_status(status, 2) == "seguir"


def test_resposta_ausente_nao_inventa_fim():
    assert decidir_pelo_status(None, 2) == "seguir"


def test_pagina_que_carrega_normal_segue():
    assert decidir_pelo_status(200, 1) == "seguir"
    assert decidir_pelo_status(200, 2) == "seguir"
