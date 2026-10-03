"""Regras de negocio da usuaria, escritas como teste executavel.

Estas regras foram definidas por escrito e sao a especificacao do que o
JobRadar deve ou nao notificar. Ate aqui elas viviam so no config.py -- e
a lista CIDADES tinha divergido em dois sentidos ao mesmo tempo (faltava
Manaus, sobravam quatro cidades fora da regra) sem que nenhum dos 76
testes existentes percebesse.

Regra, resumida:
  BRASIL   -> remoto de qualquer lugar do pais;
              hibrido/presencial SO nas cidades de CIDADES.
  EXTERIOR -> SO remoto, e so em mercado de lingua portuguesa/espanhola.
              Nunca hibrido, nunca presencial, nunca mercado de lingua
              inglesa.
"""

import pytest

from core.job import Job
from core.perfis import PERFIL_BR, PERFIL_INTL


def _vaga(titulo, local, modalidade):
    return Job(
        titulo=titulo, empresa="Empresa Teste", local=local,
        link=f"https://exemplo.com/{abs(hash((titulo, local, modalidade)))}",
        site="Teste", modalidade=modalidade,
    )


# As seis cidades obrigatorias do requisito, mais as duas mantidas por
# decisao explicita da usuaria (Maceio e Aracaju).
# Cidade com a UF DE VERDADE de cada uma.
#
# Antes era so a lista de nomes, e o teste montava o local como
# f"{cidade} - PB" pra todas — o que da "Maceio - PB", "Natal - PB",
# "Manaus - PB". Geograficamente errado, e passava porque o filtro so
# olhava o nome e ignorava a UF. Quando a checagem de UF entrou (ver
# _UF_DA_CIDADE em core/job.py), esses 12 casos falharam — corretamente.
#
# Fica registrado porque e um teste que dava verde afirmando algo falso:
# passar nao provava que a cidade era aceita, provava que a UF era
# ignorada.
CIDADES_ACEITAS = [
    ("Campina Grande", "PB"),
    ("João Pessoa", "PB"),
    ("Recife", "PE"),
    ("Natal", "RN"),
    ("Caruaru", "PE"),
    ("Manaus", "AM"),
    ("Maceió", "AL"),
    ("Aracaju", "SE"),
    ("Fortaleza", "CE"),
]


# ---------------------------------------------------------------- BRASIL

@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("cidade, uf", CIDADES_ACEITAS)
def test_br_hibrido_e_presencial_nas_cidades_aceitas(cidade, uf, modalidade):
    local = f"{cidade} - {uf}"
    assert _vaga("Analista de Dados", local, modalidade).combina_com(PERFIL_BR.regras)


# Variacoes de escrita que as fontes realmente usam -- separador, acento e
# caixa nao podem mudar o resultado.
@pytest.mark.parametrize("local", [
    "Campina Grande", "Campina Grande - PB", "Campina Grande, PB",
    "Campina Grande/PB", "CAMPINA GRANDE - PB", "campina grande, pb",
    "João Pessoa - PB", "Joao Pessoa - PB",
    "Manaus - AM", "Manaus, AM", "Manaus/AM",
    "Recife - PE", "Caruaru, PE", "Natal/RN",
])
def test_br_variacoes_de_escrita_da_cidade(local):
    assert _vaga("Analista de Dados", local, "Híbrido").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("local", [
    "São Paulo - SP", "Belo Horizonte, MG", "Salvador - BA",
    "Rio de Janeiro, RJ", "Curitiba - PR", "Brasília, DF",
    "Porto Alegre - RS",
    # Estavam em CIDADES por engano e aceitavam hibrida/presencial
    # fora da regra -- ver MEDIDO em config.py.
    "Jaboatão dos Guararapes - PE", "Teresina - PI",
    "São Luís - MA", "Petrolina - PE",
])
def test_br_hibrido_e_presencial_fora_das_cidades_e_rejeitado(local, modalidade):
    assert not _vaga("Analista de Dados", local, modalidade).combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    "Remoto", "Remoto (São Paulo, SP)", "Remoto (Manaus, AM)",
    "Remoto - Brasil", "Remote, Brazil", "Remoto (Belo Horizonte, MG)",
])
def test_br_remoto_no_brasil_e_aceito_de_qualquer_cidade(local):
    """Remoto nao tem restricao de cidade -- a regra de CIDADES vale so
    pra hibrido/presencial."""
    assert _vaga("Analista de Dados", local, "Remoto").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    "Remote - US only", "Remote, United States", "Remote (Austin, TX)",
    "Remote - India",
])
def test_br_remoto_de_mercado_nao_aceito_e_rejeitado(local):
    assert not _vaga("Analista de Dados", local, "Remoto").combina_com(PERFIL_BR.regras)


# --------------------------------------------------------- INTERNACIONAL

@pytest.mark.parametrize("local", [
    "Remote - Spain", "Madrid, Spain", "España (En remoto)",
    "Remote - Mexico", "Ciudad de México, México", "Remote - Portugal",
    "Remote - Latin America", "Remote - Colombia", "Buenos Aires, Argentina",
])
def test_intl_remoto_em_mercado_aceito_e_aceito(local):
    assert _vaga("Data Analyst", local, "Remoto").combina_com(PERFIL_INTL.regras)


@pytest.mark.parametrize("modalidade", ["Híbrido", "Presencial"])
@pytest.mark.parametrize("local", [
    "Madrid, Spain", "Barcelona, España", "Lisboa, Portugal",
    "Ciudad de México, México", "Buenos Aires, Argentina",
])
def test_intl_hibrido_e_presencial_sempre_rejeitado(local, modalidade):
    """Do exterior so interessa vaga remota -- nem mesmo em Portugal ou
    Espanha vale presencial/hibrida."""
    assert not _vaga("Data Analyst", local, modalidade).combina_com(PERFIL_INTL.regras)


@pytest.mark.parametrize("local", [
    "Remote - US only", "Remote, United States", "Remote (Seattle, WA)",
    "Remote, but candidates must be located in the United States",
    "Remote - India", "Remote - United Kingdom",
])
def test_intl_remoto_de_mercado_de_lingua_inglesa_e_rejeitado(local):
    assert not _vaga("Data Analyst", local, "Remoto").combina_com(PERFIL_INTL.regras)


def test_intl_titulo_hibrido_vence_a_classificacao_da_fonte():
    """O filtro nativo do LinkedIn as vezes marca como remota uma vaga que
    o proprio anuncio chama de hibrida -- o titulo vence."""
    vaga = _vaga("Data Analyst (Analista de Datos) - Hybrid", "Madrid, Spain", "Remoto")
    assert vaga.modalidade == "Híbrido"
    assert not vaga.combina_com(PERFIL_INTL.regras)


def test_intl_remoto_sem_mercado_declarado_exige_idioma_no_titulo():
    """Sem pais declarado nao da pra saber o mercado -- ai o titulo precisa
    dizer o idioma. Sem nenhum dos dois sinais, a vaga nao entra."""
    assert _vaga("Data Analyst (Spanish speaker)", "Remote - Worldwide", "Remoto").combina_com(PERFIL_INTL.regras)
    assert not _vaga("Data Analyst", "Remote - Worldwide", "Remoto").combina_com(PERFIL_INTL.regras)


# ------------------------------------------------------------------ CARGO

@pytest.mark.parametrize("titulo, esperado", [
    ("Analista de Dados Pleno", True),
    ("Analista de BI", True),
    ("Business Intelligence Analyst", True),
    ("Business Analyst", False),               # ambiguo, sem qualificador
    ("Business Analyst com SQL", True),        # ambiguo + qualificador
    ("Analista de Power BI", True),            # ferramenta + cargo
    ("Desenvolvedor Power BI", False),         # ferramenta sem cargo de analise
    ("Vendedor Externo", False),
    # 03/10/2026: era False. A usuária pediu engenharia de dados no radar,
    # e três cargos entraram em KEYWORDS_CARGO_FORTE. A reversão é estreita:
    # ver as duas linhas seguintes, que continuam False.
    ("Engenheiro de Dados", True),
    ("Data Engineer", True),
    ("Analytics Engineer", True),
    ("Engenheiro de Software", False),       # abrir engenharia de dados
    ("Data Engineering Manager", False),    # não é abrir engenharia
])
def test_cargo_no_titulo(titulo, esperado):
    assert _vaga(titulo, "Recife - PE", "Presencial").combina_com(PERFIL_BR.regras) is esperado


# ------------------------- CIDADE DE NOME PARECIDO, ESTADO DIFERENTE

@pytest.mark.parametrize("local", [
    # MEDIDO numa fonte real: "CAMPINA GRANDE DO SUL - PR" era aceita como
    # se fosse Campina Grande/PB. Sao cidades diferentes, a 2.500 km.
    "Campina Grande do Sul - PR",
    "CAMPINA GRANDE DO SUL - PR",
    "Campina Grande do Sul, PR",
    "Campina Grande do Sul/PR",
    # Mesmo caso, outra cidade da lista.
    "Natal da Serra - MG",
    # E o inverso: cidade certa, UF errada, ainda e outro lugar.
    "Recife - SP",
    "Manaus - PR",
])
def test_cidade_de_nome_parecido_em_outro_estado_e_rejeitada(local):
    assert not _vaga("Analista de Dados", local, "Presencial").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    "Campina Grande - PB", "CAMPINA GRANDE - PB", "Campina Grande, PB",
    "Campina Grande/PB", "Natal - RN", "Recife - PE", "Recife, PE",
    "Manaus - AM", "Caruaru - PE", "Joao Pessoa - PB", "Maceio - AL",
    "Aracaju - SE",
])
def test_cidade_certa_com_a_uf_certa_continua_passando(local):
    assert _vaga("Analista de Dados", local, "Presencial").combina_com(PERFIL_BR.regras)


@pytest.mark.parametrize("local", [
    # Sem UF nenhuma nao ha o que comparar: continua passando, de proposito.
    # Barrar aqui exigiria adivinhar por contagem de palavras, e isso
    # derrubaria "vaga em Recife" e "Natal" sozinhos, que sao validos.
    "Recife", "Natal", "Manaus", "Campina Grande",
    "Vaga em Recife", "Recife, Pernambuco, Brasil",
])
def test_sem_uf_declarada_a_cidade_continua_valendo(local):
    assert _vaga("Analista de Dados", local, "Presencial").combina_com(PERFIL_BR.regras)


# ------------- DIAGNOSTICO: barrada so pelo titulo, em cidade aceita

def test_vaga_de_bi_com_nome_comercial_e_contada(): 
    """Caso real da Lactalis: "Analista Comercial JR" em Recife, presencial.
    O local passa, o titulo nao bate keyword nenhuma, e a descricao (que o
    filtro nao le) tem KPIs, dashboards, Power BI e Qlik Sense."""
    vaga = _vaga("Analista Comercial JR", "Recife, Pernambuco, Brasil", "Presencial")
    assert not vaga.combina_com(PERFIL_BR.regras)
    assert vaga.rejeitada_so_pelo_cargo(PERFIL_BR.regras)


def test_vaga_aprovada_nao_e_contada():
    vaga = _vaga("Analista de Dados", "Recife - PE", "Presencial")
    assert vaga.combina_com(PERFIL_BR.regras)
    assert not vaga.rejeitada_so_pelo_cargo(PERFIL_BR.regras)


@pytest.mark.parametrize("titulo, local, modalidade", [
    # Barrada pelo LOCAL, nao pelo titulo -- nao interessa pra essa medicao.
    ("Analista Comercial JR", "São Paulo - SP", "Presencial"),
    ("Vendedor Externo", "Belo Horizonte, MG", "Presencial"),
    # Barrada pelos DOIS.
    ("Motorista", "Curitiba - PR", "Presencial"),
])
def test_vaga_barrada_pelo_local_nao_e_contada(titulo, local, modalidade):
    assert not _vaga(titulo, local, modalidade).rejeitada_so_pelo_cargo(PERFIL_BR.regras)


def test_conta_vaga_remota_com_titulo_fora(): 
    """Remoto tambem e "local aceito" -- vaga remota de titulo generico entra
    na contagem pelo mesmo motivo."""
    vaga = _vaga("Analista Comercial JR", "Remoto", "Remoto")
    assert vaga.rejeitada_so_pelo_cargo(PERFIL_BR.regras)
