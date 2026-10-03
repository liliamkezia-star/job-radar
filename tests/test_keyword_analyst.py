"""A keyword "Analyst" e o que ela deixa entrar — e o que não deixa.

MEDIDO (2026-08-22) contra 293 vagas reais do LinkedIn (4 termos, 4 mercados,
199 já aprovadas): "Analyst" como cargo AMBÍGUO trouxe 2 vagas a mais, as
duas certas, e zero ruído.

Por que faltava: a lista tem os cargos COMPOSTOS ("Data Analyst", "BI
Analyst", "Reporting Analyst") e não o substantivo sozinho. Título como
"Data & Analytics Analyst" não bate em nenhum dos compostos — o "&" no meio
quebra a sequência exata.

Cargo ambíguo só aprova quando o título TAMBÉM traz um qualificador de dados.
É essa proteção que faz "Analyst" caber aqui sem virar porta aberta, e é ela
que estes testes guardam.
"""

import pytest

from core.perfis import PERFIL_BR
from core.job import Job

REGRAS = PERFIL_BR.regras


def _vaga(titulo: str, local: str = "Remoto (Lisboa)") -> Job:
    return Job(
        titulo=titulo,
        empresa="Empresa",
        local=local,
        link="https://www.linkedin.com/jobs/view/" + titulo,
        site="LinkedIn",
        modalidade="Remoto",
    )


# ------------------- o que "Analyst" passou a pegar -------------------

@pytest.mark.parametrize("titulo", [
    # As duas medidas ao vivo na amostra de 293.
    "Data & Analytics Analyst",
    "Analytics Analyst - Remote Work | REF#301318",
    # Do log de 21/08, barradas só pelo título.
    "Data & Analytics Analyst - Lisbon",
    "Business & Data Integration Analyst (m/f)- HR Analytics",
])
def test_analyst_com_qualificador_de_dados_passa(titulo):
    assert _vaga(titulo).combina_com(REGRAS)


# ----------- a proteção: sem qualificador de dados, não passa -----------

@pytest.mark.parametrize("titulo", [
    "Financial Analyst",
    "Analyst, Investment Banking",
    "Credit Risk Analyst",
    "HR Analyst",
    "Compensation & Benefits Analyst",
    "Procurement Analyst",
])
def test_analyst_sem_qualificador_de_dados_nao_passa(titulo):
    """É isto que permite "Analyst" existir na lista sem virar porta aberta."""
    assert not _vaga(titulo).combina_com(REGRAS)


# ------------------ o ruído previsto, medido e vigiado ------------------

def test_data_center_analyst_e_o_ruido_conhecido():
    """RISCO ACEITO CONSCIENTEMENTE, não bug.

    "data center" casa o qualificador "data" sem ter nada a ver com análise
    de dados. Medido: não apareceu nenhuma vez nas 293 vagas da amostra, por
    isso "Analyst" entrou mesmo assim.

    Este teste FIXA o comportamento atual (passa) em vez de fingir que o
    problema não existe. Se um dia esse ruído incomodar de verdade, é aqui
    que se vê que ele sempre esteve previsto — e aí o teste inverte junto
    com a correção.
    """
    assert _vaga("Data Center Operations Analyst").combina_com(REGRAS)


# --------------- o que ficou DE FORA, e tem que continuar ---------------

@pytest.mark.parametrize("titulo", [
    "Analista de Banco de Dados",          # DBA: decisão da usuária, 22/08
    "SAP BW/HANA Datasphere Developer",    # dev: exclusão de projeto
    "Oracle Fusion Reporting Lead",        # liderança
])
def test_o_que_foi_deixado_de_fora_continua_fora(titulo):
    assert not _vaga(titulo).combina_com(REGRAS)


def test_engenharia_de_dados_SAIU_desta_lista_em_03_10_2026():
    """"Analytics Engineer" estava acima, com o comentário "engenharia: mesma
    exclusão". A usuária pediu a reversão em 03/10/2026 e entraram três
    cargos em KEYWORDS_CARGO_FORTE: Engenheiro de Dados, Data Engineer e
    Analytics Engineer.

    Este teste existe no lugar do assert que saiu, e não em vez dele: a
    decisão antiga era da usuária, a nova também, e apagar o assert
    transformaria a troca num acidente. O que ele guarda é que a reversão foi
    ESTREITA — três frases de cargo, não a palavra "engenheiro"."""
    assert _vaga("Analytics Engineer").combina_com(REGRAS)
    assert _vaga("Engenheiro de Dados").combina_com(REGRAS)
    assert _vaga("Data Engineer").combina_com(REGRAS)
    # e a vizinhança da lista acima continua intacta
    assert not _vaga("Engenheiro de Software").combina_com(REGRAS)
    assert not _vaga("Engenheiro de Power BI").combina_com(REGRAS)
    assert not _vaga("Data Engineering Manager").combina_com(REGRAS)


def test_especialista_nao_entrou_na_lista():
    """0 vagas a mais na amostra — não entrou por falta de evidência.

    Se "Especialista de Inteligencia de Negocio (BI)" voltar a aparecer no
    log como barrada só pelo título, é sinal de revisitar esta decisão.
    """
    assert not _vaga("Especialista de Inteligencia de Negocio (BI)").combina_com(REGRAS)
