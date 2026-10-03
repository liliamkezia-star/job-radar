"""Engenharia de dados no radar — a reversao de 03/10/2026 e o seu limite.

O QUE MUDOU. Ate 03/10/2026 o projeto excluia engenharia de proposito, e a
exclusao estava escrita em tres lugares: a lista "o que ficou DE FORA" em
tests/test_keyword_analyst.py, a linha ("Engenheiro de Dados", False) em
tests/test_regras_de_negocio.py, e o comentario dos qualificadores em
core/config.py. A usuaria pediu a reversao e entraram tres cargos em
KEYWORDS_CARGO_FORTE e em KEYWORDS_INTL: Engenheiro de Dados, Data Engineer e
Analytics Engineer.

POR QUE ESTE ARQUIVO EXISTE. A reversao e ESTREITA: tres frases de cargo, nao
a palavra "engenheiro". Alguem (eu inclusive) pode achar daqui a seis meses
que da no mesmo encurtar isso pra "engineer" e cobrir mais vaga de uma vez.
Nao da: a lista abaixo foi medida ANTES de escrever a mudanca, e sao dez
titulos que a palavra curta arrastaria junto.

O TERMO DE BUSCA NAO E A KEYWORDS. Medido no mesmo dia, e e o motivo de a
mudanca ter mexido nas duas listas: os tres titulos reprovavam SO PELO CARGO.
Acrescentar o termo de busca sem a keyword traria a vaga e o filtro jogaria
fora — custo de ciclo com ganho zero. No perfil BR isso se resolve sozinho
(TERMOS_CARGO e derivado de KEYWORDS); no internacional nao, porque a lista
de busca de la exige sinal de idioma.
"""
import pytest

from core.config import KEYWORDS_CARGO_FORTE, QUALIFICADORES_CARGO, TERMOS_BUSCA
from core.config_intl import KEYWORDS_INTL, TERMOS_BUSCA_INTL
from core.job import Job
from core.perfis import PERFIL_BR, PERFIL_INTL

NOVOS = ["Engenheiro de Dados", "Data Engineer", "Analytics Engineer"]

# Medidos por simulacao contra os dois perfis, antes de a mudanca ser escrita.
# Cada um e um jeito diferente de a palavra curta vazar: gestao, outra
# engenharia, plataforma, infraestrutura.
NAO_DEVEM_ENTRAR = [
    "Data Engineering Manager",
    "Gerente de Engenharia de Dados",
    "Head of Data Engineering",
    "Analytics Engineering Lead",
    "Engenheiro de Software",
    "Engenheiro Civil",
    "Engenheiro de Produção",
    "Engenheiro de Machine Learning",
    "Data Platform Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
    # este ultimo e o mais importante: passa pelo caminho ferramenta+cargo se
    # "engenheiro" virar qualificador, e e vaga de desenvolvimento.
    "Engenheiro de Power BI",
]


def _br(titulo: str) -> Job:
    return Job(titulo=titulo, empresa="x", local="Recife, PE", link="https://x/y",
               site="teste", publicado_em="", modalidade="Presencial")


def _intl(titulo: str) -> Job:
    return Job(titulo=titulo, empresa="x", local="Portugal", link="https://x/y",
               site="teste", publicado_em="", modalidade="Remoto")


@pytest.mark.parametrize("titulo", NOVOS)
def test_entra_nos_dois_perfis(titulo):
    """Nos DOIS. Deixar os perfis diferentes aqui recriaria a divergencia
    silenciosa que fez o internacional ficar sem mecanismo por semanas."""
    assert _br(titulo).combina_com(PERFIL_BR.regras)
    assert _intl(titulo).combina_com(PERFIL_INTL.regras)


@pytest.mark.parametrize("titulo", NAO_DEVEM_ENTRAR)
def test_a_reversao_e_estreita_e_nao_arrasta_estes(titulo):
    assert not _br(titulo).combina_com(PERFIL_BR.regras)
    assert not _intl(titulo).combina_com(PERFIL_INTL.regras)


def test_engenheiro_nao_virou_qualificador_de_ferramenta():
    """O caminho ferramenta+cargo e outro: se "engenheiro" entrasse em
    QUALIFICADORES_CARGO, "Engenheiro de Power BI" passaria. Abrir engenharia
    de DADOS nao e abrir engenharia."""
    curtos = [q.lower() for q in QUALIFICADORES_CARGO]
    assert "engenheiro" not in curtos
    assert "engineer" not in curtos
    assert not _br("Engenheiro de Power BI").combina_com(PERFIL_BR.regras)


def test_a_keyword_e_a_frase_inteira_e_nao_a_palavra_curta():
    """A guarda contra o encurtamento. Se alguem trocar as tres frases por
    "engineer" ou "engenheiro", este teste cai junto com os doze de cima."""
    for curta in ("engineer", "engenheiro", "engenharia", "engineering"):
        assert curta not in [k.lower() for k in KEYWORDS_CARGO_FORTE]
        assert curta not in [k.lower() for k in KEYWORDS_INTL]


def test_o_termo_entrou_na_busca_do_perfil_br_por_derivacao():
    """TERMOS_CARGO sai de KEYWORDS automaticamente (ver core/config.py), e e
    por isso que no BR bastou uma edicao. Se a derivacao for desfeita um dia,
    este teste acusa — foi a divergencia entre as duas listas que fez metade
    das keywords nunca ser buscada de verdade."""
    for titulo in NOVOS:
        assert titulo.lower() in TERMOS_BUSCA


def test_a_busca_internacional_leva_sinal_de_idioma():
    """No internacional a lista de busca e escrita a mao e exige sinal de
    idioma ou mercado — cargo sozinho ali e "o mundo inteiro sem filtro de
    idioma", nas palavras do proprio arquivo. Entao "data engineer" puro NAO
    deve estar la: traria vaga global que o filtro de mercado reprova depois,
    gastando requisicao por nada."""
    com_engenharia = [t for t in TERMOS_BUSCA_INTL if "engineer" in t]
    assert len(com_engenharia) == 3
    assert "data engineer" not in TERMOS_BUSCA_INTL
    for termo in com_engenharia:
        tem_sinal = any(p in termo for p in
                        ("portuguese", "spanish", "latam", "latin america", "remote"))
        assert tem_sinal, termo


def test_senior_de_engenharia_passa_mas_com_nota_baixa():
    """Consequencia que vale saber: senioridade acima do alvo tira 2 pontos,
    e com o digest valendo pra nota menor que 4 essas vagas vao pro resumo
    diario em vez de chegarem na hora. Nao e defeito — e a regra de
    senioridade funcionando. Esta aqui pra nao virar surpresa."""
    job = _br("Senior Data Engineer")
    assert job.combina_com(PERFIL_BR.regras)
    assert job.pontuar_relevancia(PERFIL_BR.regras) < 4
