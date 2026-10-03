"""A guarda que falta pra tirar o banco do git sem enxurrada de notificacao.

MEDIDO em 03/10/2026, lendo o codigo antes de mexer no workflow:
BancoVazioSuspeito so dispara quando o arquivo EXISTIA com conteudo e a
tabela veio vazia. Arquivo AUSENTE ela entende como primeiro uso e deixa o
ciclo seguir.

Isso nunca doeu porque o git clone sempre trouxe data/jobs.db. Tirar o banco
do repositorio remove essa garantia junto: um cache vazio na primeira
execucao depois da troca faria as 3.559 vagas do banco baterem "nao vista" e
serem notificadas de uma vez.

Por isso a guarda nova e por variavel de ambiente, e nao sempre ligada:
primeiro uso de verdade existe (maquina nova, banco descartavel de teste) e
nao pode abortar. Quem liga e o workflow, que sabe que ali banco ausente e
defeito e nao estreia.
"""
import os
import sqlite3

import pytest

from database import database

# Tudo pelo MODULO (database.iniciar_db) e nao por valor
# (from ... import iniciar_db). Motivo medido: tests/test_db_path.py faz
# importlib.reload(database.database), e o reload cria uma classe
# BancoVazioSuspeito NOVA. Importada por valor, a classe que este arquivo
# guarda deixa de ser a que iniciar_db levanta, e o pytest.raises nao pega —
# o teste passava sozinho e falhava na suite inteira, que e o pior jeito de
# falhar. Pelo modulo, a referencia e resolvida na hora da chamada.


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Aponta o modulo pra um banco descartavel e devolve o caminho."""
    caminho = tmp_path / "data" / "jobs.db"
    monkeypatch.setattr(database, "DB_PATH", str(caminho))
    monkeypatch.delenv(database.EXIGIR_BANCO_EXISTENTE, raising=False)
    return caminho


def _popular(caminho, quantas: int):
    database.iniciar_db()
    with sqlite3.connect(caminho) as conexao:
        for i in range(quantas):
            conexao.execute(
                "INSERT INTO vagas_vistas (id, titulo, site) VALUES (?, ?, ?)",
                (f"id-{i}", f"Analista {i}", "LinkedIn"),
            )


# --- sem a variavel: comportamento de hoje, intacto -------------------


def test_primeiro_uso_de_verdade_continua_passando(banco):
    """Maquina nova, banco que nunca existiu: tem que criar e seguir."""
    database.iniciar_db()
    assert banco.exists()


def test_banco_que_existia_e_veio_vazio_continua_abortando(banco):
    """A guarda que ja existia. O cenario dela: arquivo em disco com
    conteudo, tabela vazia — banco perdido, corrompido ou resetado."""
    database.iniciar_db()
    assert banco.stat().st_size > 0
    with sqlite3.connect(banco) as conexao:
        conexao.execute("DROP TABLE vagas_vistas")
    with pytest.raises(database.BancoVazioSuspeito):
        database.iniciar_db()


def test_banco_com_vagas_segue_normal(banco):
    _popular(banco, 3)
    database.iniciar_db()
    with sqlite3.connect(banco) as conexao:
        assert conexao.execute("SELECT COUNT(*) FROM vagas_vistas").fetchone()[0] == 3


# --- com a variavel ligada: o que o workflow vai usar -----------------


def test_banco_ausente_aborta_quando_a_variavel_esta_ligada(banco, monkeypatch):
    """O cenario exato que a saida do git cria: cache vazio, arquivo nenhum.
    Sem isto, o ciclo rodaria e notificaria o banco inteiro."""
    monkeypatch.setenv(database.EXIGIR_BANCO_EXISTENTE, "1")
    assert not banco.exists()
    with pytest.raises(database.BancoVazioSuspeito) as erro:
        database.iniciar_db()
    # A mensagem tem que dizer COMO recuperar, nao so que deu errado: quem a
    # le e a usuaria, no Telegram, sem o repositorio na frente. Entao exige os
    # dois pedacos da receita — o nome do artifact e onde restaurar. So
    # procurar "artifact" nao servia: a palavra sobrevive a uma mensagem
    # mutilada (medido mutando a mensagem e vendo o teste passar).
    recado = str(erro.value)
    assert "jobradar-banco" in recado   # de onde tirar o banco
    assert "restaure" in recado          # e o que fazer com ele
    # Nao vale procurar "data/jobs.db": o caminho do banco ja aparece no
    # comeco da mensagem, entao esse assert passava mesmo com a receita de
    # recuperacao apagada. Medido mutando a mensagem.


def test_arquivo_de_zero_byte_tambem_aborta(banco, monkeypatch):
    """sqlite3.connect cria arquivo de 0 byte sozinho. Se "existe" bastasse,
    um arquivo vazio deixado por uma execucao morta passaria pela guarda."""
    banco.parent.mkdir(parents=True, exist_ok=True)
    banco.touch()
    monkeypatch.setenv(database.EXIGIR_BANCO_EXISTENTE, "1")
    with pytest.raises(database.BancoVazioSuspeito):
        database.iniciar_db()


def test_com_a_variavel_ligada_e_banco_cheio_nao_atrapalha(banco, monkeypatch):
    """A guarda nao pode ficar no caminho do ciclo normal — e ciclo normal e
    99,9% das execucoes."""
    _popular(banco, 5)
    monkeypatch.setenv(database.EXIGIR_BANCO_EXISTENTE, "1")
    database.iniciar_db()
    with sqlite3.connect(banco) as conexao:
        assert conexao.execute("SELECT COUNT(*) FROM vagas_vistas").fetchone()[0] == 5


def test_valor_diferente_de_1_nao_liga_a_guarda(banco, monkeypatch):
    """Variavel existindo com qualquer coisa dentro nao vale: "0", "false" e
    "" sao jeitos comuns de DESLIGAR, e aborto acidental aqui para o robo."""
    for valor in ("0", "false", "", "sim"):
        monkeypatch.setenv(database.EXIGIR_BANCO_EXISTENTE, valor)
        if banco.exists():
            os.remove(banco)
        database.iniciar_db()
        assert banco.exists(), f"abortou com {valor!r}"
