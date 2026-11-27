# -*- coding: utf-8 -*-
"""Estado brasileiro escrito por extenso tem que resolver pro mercado "Brasil".

POR QUE EXISTE. Nome de estado por extenso nao estava mapeado em
_MERCADOS_REMOTO: so a sigla resolvia ("- PB") e alguns nomes de cidade. Com
modalidade=Remoto, "Campina Grande, Paraiba" virava escopo
{"campina grande paraiba"}.

Isso nao e inofensivo: escopo nao mapeado NAO e "sem restricao" (isso seria
conjunto vazio) e sim "declarou mercado fora da lista aceita" -- ver o MEDIDO
em _mercados_correspondentes. A vaga remota brasileira, com o cargo certo,
era descartada por localizacao dependendo apenas de a fonte escrever "PB" ou
"Paraiba".

ALCANCE: a API da Gupy manda o estado por extenso -- test_gupy_api.py
parametriza com ("Curitiba", "Parana", "remote"). Em sonda ao vivo (1.079
vagas brutas de Gupy+Solides) o caminho nao disparou, porque a Gupy deixa
`local` vazio em vaga remota e a Solides manda sigla: e falha latente, nao
perda medida em producao.
"""
import pytest

from core.job import Job, extrair_escopo_remoto
from core.perfis import PERFIL_BR

# Os quatro primeiros falhavam antes do mapa; os demais ja passavam (por
# cidade conhecida ou capital) e precisam continuar passando.
LOCAIS_BRASILEIROS = [
    "Campina Grande, Paraiba",
    "Campina Grande, Paraíba",
    "Joinville, Santa Catarina",
    "Uberlandia, Minas Gerais",
    "Belo Horizonte, Minas Gerais",
    "Curitiba, Paraná",
    "Sorocaba, São Paulo",
    "Caxias do Sul, Rio Grande do Sul",
    "Paraíba",
]


@pytest.mark.parametrize("local", LOCAIS_BRASILEIROS)
def test_estado_por_extenso_resolve_para_brasil(local):
    assert extrair_escopo_remoto(local, "Remoto") == {"Brasil"}


@pytest.mark.parametrize("local", LOCAIS_BRASILEIROS)
def test_vaga_remota_com_estado_por_extenso_e_aprovada(local):
    """Brasil remoto de qualquer lugar do pais -- e a regra de negocio; o
    texto do estado nao pode mudar o resultado."""
    vaga = Job(
        titulo="Analista de Dados Pleno",
        empresa="Empresa Teste",
        local=local,
        link="https://exemplo.test/" + str(abs(hash(local))),
        site="Teste",
        modalidade="Remoto",
    )
    assert vaga.combina_com(PERFIL_BR.regras) is True


@pytest.mark.parametrize("local, mercado", [
    ("Remote - US only", "Estados Unidos"),
    ("Remote - India", "Índia"),
    ("Lisboa, Portugal", "Portugal"),
    ("Remote - LATAM", "LATAM"),
])
def test_mercado_estrangeiro_continua_resolvendo_igual(local, mercado):
    """O mapa novo nao pode atropelar o que ja funcionava: mercado de fora
    continua sendo reconhecido como ele mesmo, nao como Brasil."""
    assert extrair_escopo_remoto(local, "Remoto") == {mercado}


def test_mercado_nao_aceito_continua_barrando():
    """A allowlist continua allowlist."""
    vaga = Job(
        titulo="Analista de Dados",
        empresa="Empresa Teste",
        local="Remote - US only",
        link="https://exemplo.test/us-only",
        site="Teste",
        modalidade="Remoto",
    )
    assert vaga.combina_com(PERFIL_BR.regras) is False


@pytest.mark.parametrize("local, esperado", [
    # Capital vence a sigla ambigua (regra existente, _SIGLAS_UF_AMBIGUAS).
    ("Maceió - AL", {"Brasil"}),
    ("Florianópolis - SC", {"Brasil"}),
    # Cidade nao-capital em UF ambigua continua resolvendo pros EUA. NAO e
    # o que este commit mexe: a ambiguidade vive na sigla de duas letras, e
    # a decisao conservadora de "so capital vence" e anterior e deliberada.
    # Fica fixado aqui so pra deixar explicito que o mapa por extenso nao
    # alterou este caminho.
    ("Joinville - SC", {"Estados Unidos"}),
    ("Altamira - PA", {"Estados Unidos"}),
])
def test_caminho_da_sigla_ambigua_fica_como_estava(local, esperado):
    assert extrair_escopo_remoto(local, "Remoto") == esperado
