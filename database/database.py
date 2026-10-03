
import sqlite3
import os
from contextlib import contextmanager

from core.config import DB_PATH
from core.job import _normalizar


def _garantir_pasta():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def _conectar():
    _garantir_pasta()
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _garantir_coluna_chave_secundaria(conn):
    """Migração leve: bancos criados antes da dedup por empresa+título não
    têm essa coluna. ALTER TABLE ADD COLUMN é seguro rodar preservando dado
    existente.

    MEDIDO: a migração adicionava a coluna mas não preenchia o histórico —
    linha antiga ficava com chave_secundaria NULL pra sempre, já que
    salvar_vaga só grava esse valor em INSERT novo, nunca em UPDATE
    retroativo. Resultado real: 373 linhas NULL, 52 delas duplicata de
    outra linha (mesma empresa+título achada de novo por outra fonte) que
    ja_vista() não pegava — `WHERE chave_secundaria = ?` nunca bate contra
    NULL em SQL, então a vaga reaparecia como "nova" e notificava de novo.
    Backfill roda toda vez que iniciar_db() é chamado (idempotente — só
    tem linha NULL pra processar na primeira vez depois desse fix; depois
    disso salvar_vaga já preenche em toda inserção nova, então o SELECT
    abaixo volta vazio e o loop não faz nada).
    """
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "chave_secundaria" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN chave_secundaria TEXT")

    linhas_nulas = conn.execute(
        "SELECT id, titulo, empresa FROM vagas_vistas WHERE chave_secundaria IS NULL"
    ).fetchall()
    for id_, titulo, empresa in linhas_nulas:
        chave = f"{_normalizar(empresa or '')}|{_normalizar(titulo or '')}"
        conn.execute(
            "UPDATE vagas_vistas SET chave_secundaria = ? WHERE id = ?",
            (chave, id_),
        )


def _garantir_coluna_publicado_em(conn):
    """Mesma lógica de migração leve acima, pra Job.publicado_em (data
    anunciada pela fonte). Precisa estar salva no banco, não só na
    notificação — é o que permite medir latência de verdade depois (tempo
    entre a fonte publicar e o JobRadar notificar), não só mostrar a data
    uma vez e esquecer."""
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "publicado_em" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN publicado_em TEXT")


def _garantir_coluna_modalidade(conn):
    """Mesma lógica de migração leve, pra Job.modalidade (Remoto/Híbrido/
    Presencial como campo próprio, em vez de embutido no texto de local)."""
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "modalidade" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN modalidade TEXT")


def _garantir_colunas_digest(conn):
    """Migração leve pro digest ranqueado (ver main.py/_enviar_digest_diario
    e notifier/telegram.py/montar_digest): vaga com relevancia abaixo do
    limiar não notifica na hora, fica marcada digest_pendente=1 até entrar
    num digest enviado com sucesso — linha antiga (antes desta coluna
    existir) fica com digest_pendente NULL, que o WHERE digest_pendente = 1
    do digest simplesmente ignora (comportamento correto: vaga antiga já
    foi tratada de um jeito ou de outro antes desse recurso existir).

    `perfil`: sem isso não dá pra saber de qual perfil (brasil/
    internacional) veio cada linha pendente — o digest é por perfil, igual
    heartbeat e alerta de saúde já são. `exploratoria`: só pra render (ícone
    diferente na lista), não afeta a lógica de fila.
    """
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "relevancia" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN relevancia INTEGER")
    if "perfil" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN perfil TEXT")
    if "digest_pendente" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN digest_pendente INTEGER")
    if "exploratoria" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN exploratoria INTEGER")


def _garantir_coluna_situacao(conn):
    """Migração leve: a tabela tinha 10 colunas e nenhuma dizia o que
    aconteceu DEPOIS de notificada — candidatou, descartou, chamou pra
    entrevista. O sistema encontra e notifica; o resto do funil (metade do
    trabalho de procurar vaga) ficava sem registro nenhum, só na cabeça de
    quem lê o Telegram.

    Valor livre (não é ENUM/CHECK) de propósito — 'nova' é só o ponto de
    partida, o vocabulário real (candidatei/descartei/entrevista/proposta...)
    é decidido por quem usa, não travado no schema. Toda vaga nova entra
    como 'nova' (ver salvar_vaga); linha existente antes desta coluna
    também vira 'nova' no backfill abaixo — sem isso ficaria NULL pra
    sempre, e um resumo tipo "o que ainda não teve retorno" (WHERE
    situacao = 'nova') simplesmente não encontraria as vagas antigas."""
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "situacao" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN situacao TEXT")

    conn.execute("UPDATE vagas_vistas SET situacao = 'nova' WHERE situacao IS NULL")


def _garantir_coluna_feedback(conn):
    """Migração leve: reação 👍/👎 no Telegram (botão inline, ver
    notifier/telegram.py) grava aqui se a vaga notificada era boa ou era
    ruído — sinal que hoje não existe em lugar nenhum. Sem isso, ajustar
    KEYWORDS_CARGO_AMBIGUO/FERRAMENTAS_TITULO/TERMOS_BUSCA continua sendo
    intuição de quem lê o log, do mesmo jeito que os bugs de precisão desta
    base sempre nasceram.

    Diferente de situacao (que sempre tem valor, default 'nova'), feedback
    fica NULL até alguém de fato reagir — NULL aqui significa "sem reação
    ainda", um estado real e distinto de "positivo"/"negativo", não um
    buraco de migração pra preencher. Por isso não tem backfill: as 780
    linhas antigas continuam NULL até o usuário reagir (ou não) de agora
    em diante — não dá pra inferir reação passada que nunca aconteceu."""
    colunas = [linha[1] for linha in conn.execute("PRAGMA table_info(vagas_vistas)")]
    if "feedback" not in colunas:
        conn.execute("ALTER TABLE vagas_vistas ADD COLUMN feedback TEXT")


class BancoVazioSuspeito(RuntimeError):
    """jobs.db já existia em disco (tinha conteúdo) mas a tabela veio vazia
    depois de iniciar_db() — não é primeiro uso, é banco perdido/corrompido/
    resetado. Ver iniciar_db()."""


# Quando o banco NAO vem mais do repositorio (ver a saida do git em
# .github/workflows/jobradar.yml), "arquivo ausente" deixa de significar
# primeiro uso e passa a significar estado perdido — cache vazio, artifact
# nao recuperado, caminho errado. A diferenca e grave: a guarda de banco
# vazio abaixo so pega arquivo que EXISTIA com conteudo, entao arquivo
# ausente passaria batido e as vagas todas seriam notificadas de novo, de
# uma vez.
#
# Fica como variavel de ambiente, desligada por padrao, porque primeiro uso
# de verdade existe (maquina nova, banco descartavel de teste) e nao pode
# abortar. Quem liga e o workflow, que sabe que ali banco ausente e defeito.
EXIGIR_BANCO_EXISTENTE = "JOBRADAR_EXIGIR_BANCO_EXISTENTE"


def _exigindo_banco_existente() -> bool:
    return os.getenv(EXIGIR_BANCO_EXISTENTE) == "1"


def iniciar_db():
    # Precisa checar ANTES de conectar: sqlite3.connect() já cria um arquivo
    # vazio de 0 byte se o caminho não existir, o que destruiria o sinal que
    # queremos capturar (arquivo existia com conteúdo real vs. nunca existiu).
    arquivo_ja_existia = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0

    if _exigindo_banco_existente() and not arquivo_ja_existia:
        raise BancoVazioSuspeito(
            f"{DB_PATH} nao existe (ou esta vazio) e {EXIGIR_BANCO_EXISTENTE}=1 — "
            "neste ambiente o banco vem do cache/artifact, nao do repositorio, "
            "entao arquivo ausente e estado perdido e nao primeiro uso. Abortando "
            "antes de rodar qualquer busca, pra nao notificar o banco inteiro como "
            "se fosse novo. Pra recuperar: baixe o artifact jobradar-banco-* da "
            "ultima execucao boa e restaure em data/jobs.db."
        )

    with _conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vagas_vistas (
                id TEXT PRIMARY KEY,
                titulo TEXT,
                empresa TEXT,
                local TEXT,
                link TEXT,
                site TEXT,
                encontrada_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _garantir_coluna_chave_secundaria(conn)
        _garantir_coluna_publicado_em(conn)
        _garantir_coluna_modalidade(conn)
        _garantir_colunas_digest(conn)
        _garantir_coluna_situacao(conn)
        _garantir_coluna_feedback(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vagas_digest_pendente "
            "ON vagas_vistas (perfil, digest_pendente)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vagas_chave_secundaria "
            "ON vagas_vistas (chave_secundaria)"
        )
        # Tabela chave/valor genérica — usada hoje só pra guardar a data do
        # último heartbeat diário (ver notifier/telegram.py e main.py), mas
        # serve pra qualquer estado simples que precise sobreviver entre
        # ciclos sem virar coluna nova em vagas_vistas.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadados (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        total_vagas = conn.execute("SELECT COUNT(*) FROM vagas_vistas").fetchone()[0]

    # Se o arquivo já existia com conteúdo mas a tabela veio vazia, não é
    # primeiro uso — é banco sumido/corrompido/resetado (checkout falhou,
    # commit ruim, etc.). Se o ciclo seguisse normal, TODA vaga encontrada
    # bateria "não vista" e o sistema notificaria centenas de vagas antigas
    # de uma vez, de repente. Primeiro uso de verdade (arquivo nunca
    # existiu) não cai aqui — tabela vazia nesse caso é esperada.
    if arquivo_ja_existia and total_vagas == 0:
        raise BancoVazioSuspeito(
            f"{DB_PATH} já existia em disco (tinha conteúdo) mas a tabela "
            "vagas_vistas veio vazia — sinal de banco perdido, corrompido ou "
            "resetado, não de primeiro uso. Abortando antes de rodar "
            "qualquer busca, pra não notificar em massa vagas antigas como "
            "se fossem novas."
        )


def ja_vista(job) -> bool:
    """Recebe o Job inteiro (não só o id): precisa checar duas chaves.

    id = hash da URL (pega repost exato na mesma fonte). chave_secundaria =
    empresa+título normalizados (pega a MESMA vaga publicada em fontes
    diferentes, com URL diferente em cada uma — ver Job.chave_secundaria).
    """
    with _conectar() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM vagas_vistas WHERE id = ? OR chave_secundaria = ? LIMIT 1",
            (job.id, job.chave_secundaria),
        )
        return cursor.fetchone() is not None


def obter_metadado(chave: str) -> str | None:
    with _conectar() as conn:
        cursor = conn.execute("SELECT valor FROM metadados WHERE chave = ?", (chave,))
        linha = cursor.fetchone()
        return linha[0] if linha else None


def definir_metadado(chave: str, valor: str):
    with _conectar() as conn:
        conn.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )


def salvar_vaga(job, perfil_chave: str = "", digest_pendente: bool = False, exploratoria: bool = False):
    """`digest_pendente=True` marca a vaga como ainda não notificada —
    entrou na fila do digest diário (ver _enviar_digest_diario em main.py)
    em vez de mandar mensagem individual na hora, porque a relevância ficou
    abaixo do limiar. `perfil_chave` é o que permite o digest buscar só as
    pendentes DESSE perfil (ver obter_vagas_pendentes_digest) — sem isso,
    rodar brasil+internacional na mesma execução misturaria a fila dos
    dois."""
    with _conectar() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO vagas_vistas
                (id, titulo, empresa, local, link, site, chave_secundaria, publicado_em,
                 modalidade, relevancia, perfil, digest_pendente, exploratoria, situacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id, job.titulo, job.empresa, job.local, job.link, job.site,
                job.chave_secundaria, job.publicado_em, job.modalidade,
                job.relevancia, perfil_chave, int(digest_pendente), int(exploratoria), "nova",
            ),
        )


def definir_situacao(id_ou_link: str, situacao: str):
    """Atualiza a situação de UMA vaga (nova/candidatei/descartei/
    entrevista/o que quiser — valor livre, ver _garantir_coluna_situacao).
    Aceita id (hash usado como chave primária) ou link exato — o link é o
    que sobra de mais fácil de copiar da notificação do Telegram, então
    aceitar os dois evita ter que ir atrás do id manualmente."""
    with _conectar() as conn:
        conn.execute(
            "UPDATE vagas_vistas SET situacao = ? WHERE id = ? OR link = ?",
            (situacao, id_ou_link, id_ou_link),
        )


def definir_feedback(job_id: str, feedback: str):
    """Grava a reação 👍/👎 do botão inline (ver processar_feedback_pendente
    em notifier/telegram.py) — 'positivo'/'negativo'. Só por id (não por
    link, diferente de definir_situacao): o callback_data do botão sempre
    carrega o id, nunca o link inteiro (custaria mais dos 64 bytes que o
    Telegram permite em callback_data)."""
    with _conectar() as conn:
        conn.execute(
            "UPDATE vagas_vistas SET feedback = ? WHERE id = ?",
            (feedback, job_id),
        )


def obter_vagas_pendentes_digest(perfil_chave: str) -> list[tuple]:
    """Vagas salvas com digest_pendente=1 pra esse perfil, da mais
    relevante pra menos — ver _enviar_digest_diario em main.py. Pode
    acumular de mais de um ciclo (a cada 3h) até bater o horário do envio,
    e também sobrevive se o envio de um dia falhar (Telegram fora do ar):
    fica pendente e entra no digest seguinte, nunca é descartada."""
    with _conectar() as conn:
        cursor = conn.execute(
            """
            SELECT titulo, empresa, link, relevancia, exploratoria
            FROM vagas_vistas
            WHERE perfil = ? AND digest_pendente = 1
            ORDER BY relevancia DESC, encontrada_em ASC
            """,
            (perfil_chave,),
        )
        return cursor.fetchall()


def marcar_digest_enviado(perfil_chave: str):
    """Só chamar depois que TODAS as partes do digest confirmarem envio
    (ver enviar_digest em notifier/telegram.py) — se qualquer parte falhar,
    não limpa nada, pra não perder vaga: fica tudo pendente e tenta nas
    partes de novo no próximo envio, mesmo que isso duplique alguma que já
    tinha saído com sucesso numa parte anterior. Duplicar é aceitável;
    perder não."""
    with _conectar() as conn:
        conn.execute(
            "UPDATE vagas_vistas SET digest_pendente = 0 WHERE perfil = ? AND digest_pendente = 1",
            (perfil_chave,),
        )