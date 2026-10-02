"""Alerta quando UMA fonte morre sozinha.

POR QUE EXISTE. O alerta de saude que ja havia exige maioria ESTRITA das
fontes com problema, e isso esta certo pro que ele mede ("o ciclo inteiro
degringolou"). Mas fonte morrendo sozinha passava invisivel, e cobrou a conta
duas vezes:

  · 01/09 — a Solides caiu de ~400 vagas pra 70. Ninguem viu.
  · 02/10 — a Gupy respondendo 404 em TODO termo, zero vaga em tres ciclos
    seguidos. Descoberto por acaso, ao ler log de ciclo por outro motivo.

Nos dois casos o log DIZIA a verdade ("resposta inesperada da API, nao e busca
vazia" — correcao de 31/08). O sistema sabia e nao avisava.

POR QUE 3 CICLOS E NAO 1. Esta escrito em _deve_alertar_saude e vale igual
aqui: "alerta que dispara sem motivo e pior que alerta que nao existe — depois
de duas ou tres vezes, ele deixa de ser lido". O numero 3 nao foi escolhido no
chute: veio dos ciclos 388-390, abaixo.
"""
from main import CICLOS_ZERADOS_PRA_ALERTAR, avaliar_fonte_morta


def test_fonte_trazendo_vaga_zera_o_contador():
    assert avaliar_fonte_morta(True, "2", None) == (0, False, False)


def test_primeiro_e_segundo_zero_nao_alertam():
    """Fonte pequena tem dia fraco. Alertar no primeiro zero seria o alarme
    falso que mata a credibilidade do alerta."""
    assert avaliar_fonte_morta(False, None, None) == (1, False, False)
    assert avaliar_fonte_morta(False, "1", None) == (2, False, False)


def test_terceiro_zero_alerta():
    zeros, avisar, voltou = avaliar_fonte_morta(False, "2", None)
    assert (zeros, avisar, voltou) == (3, True, False)
    assert zeros == CICLOS_ZERADOS_PRA_ALERTAR


def test_nao_repete_o_alerta_a_cada_ciclo():
    """Fonte morta ficaria 8 mensagens por dia ate alguem consertar — e o
    alerta morre de tanto repetir. Avisa UMA vez por queda."""
    zeros, avisar, _ = avaliar_fonte_morta(False, "3", "3")
    assert zeros == 4
    assert avisar is False


def test_avisa_quando_a_fonte_volta_se_a_queda_foi_avisada():
    assert avaliar_fonte_morta(True, "7", "3") == (0, False, True)


def test_nao_avisa_recuperacao_de_queda_que_nunca_foi_avisada():
    """Mensagem sobre um problema que ela nunca soube que teve e so ruido."""
    assert avaliar_fonte_morta(True, "2", None) == (0, False, False)
    assert avaliar_fonte_morta(True, "2", "") == (0, False, False)


def test_contador_corrompido_nao_explode():
    """O valor vem da tabela metadados, que e texto. Se virar lixo, o alerta
    nao pode derrubar o ciclo inteiro."""
    assert avaliar_fonte_morta(False, "nao-e-numero", None) == (1, False, False)


# ------------------- os dois casos reais, lado a lado -------------------

def _rodar(sequencia):
    """Roda uma sequencia de ciclos e devolve quantos alertas sairiam."""
    zeros, avisou, alertas, voltas = None, None, 0, 0
    for trouxe in sequencia:
        zeros, avisar, voltou = avaliar_fonte_morta(trouxe, zeros, avisou)
        zeros = str(zeros)
        if avisar:
            alertas += 1
            avisou = zeros
        if voltou:
            voltas += 1
            avisou = ""
    return alertas, voltas


def test_weworkremotely_dia_fraco_nao_alerta():
    """MEDIDO nos ciclos 388-390: a WeWorkRemotely trouxe 0, depois 4, depois 0.
    E fonte pequena com dia fraco, nao fonte morta. Nao pode alertar."""
    assert _rodar([False, True, False]) == (0, 0)


def test_gupy_morta_alerta_uma_vez_e_avisa_quando_volta():
    """MEDIDO nos mesmos tres ciclos: a Gupy trouxe 0, 0, 0 — 404 em todo termo.
    Essa tem que alertar, e exatamente uma vez, mesmo que fique morta por
    muitos ciclos. Quando voltar, avisa a recuperacao."""
    assert _rodar([False, False, False]) == (1, 0)
    assert _rodar([False] * 10) == (1, 0)
    assert _rodar([False, False, False, False, True]) == (1, 1)


def test_queda_curta_entre_duas_quedas_longas_alerta_de_novo():
    """Voltou, caiu de novo: e um problema NOVO e merece alerta novo."""
    assert _rodar([False, False, False, True, False, False, False]) == (2, 1)
