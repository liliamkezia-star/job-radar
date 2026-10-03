
import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from core.config import DIGEST_HORA_UTC, INTERVALO_MINUTOS, LIMIAR_DIGEST_IMEDIATO
from database.database import (
    BancoVazioSuspeito,
    definir_metadado,
    iniciar_db,
    ja_vista,
    marcar_digest_enviado,
    obter_metadado,
    obter_vagas_pendentes_digest,
    salvar_vaga,
)
from notifier.telegram import (
    enviar_digest,
    enviar_mensagem,
    notificar_vaga,
    notificar_vaga_exploratoria,
    processar_feedback_pendente,
)
from core.perfis import FREQUENCIA_ALTA, PERFIS, Perfil
from utils.filtro import filtrar_vagas
from core.logger import get_logger

logger = get_logger()


def _fontes_baixa_frequencia_ja_rodaram_hoje(perfil: Perfil) -> bool:
    chave = f"baixa_frequencia_ultimo_dia_{perfil.chave}"
    return obter_metadado(chave) == date.today().isoformat()


# Não é mais uma lista fixa construída uma vez: os scrapers recebem só o
# BLOCO de termos do ciclo atual (ver _proximo_bloco_termos), e a lista de
# QUAIS fontes entram também varia por ciclo (fonte de baixa frequência só
# entra na primeira execução do dia) — então precisam ser (re)criados a
# cada ciclo, não guardados numa constante de módulo. Cada perfil tem sua
# própria chave de metadados (sufixo perfil.chave), pra rodar dois perfis
# na mesma execução sem um pisar na cadência do outro.
def _construir_scrapers(perfil: Perfil, termos_busca: list[str]):
    rodar_baixa_frequencia = not _fontes_baixa_frequencia_ja_rodaram_hoje(perfil)

    scrapers = [
        definicao.classe(termos_busca=termos_busca, **definicao.kwargs_extras)
        for definicao in perfil.definicao_scrapers
        if definicao.frequencia == FREQUENCIA_ALTA or rodar_baixa_frequencia
    ]

    if rodar_baixa_frequencia:
        # Marca ANTES de rodar (não depois): mesmo que uma fonte de baixa
        # frequência falhe nesse ciclo, ela "rodou" no sentido de já ter
        # sido tentada hoje — não deve ser tentada de novo no ciclo
        # seguinte só porque deu erro. Falha individual já é tratada e
        # logada normalmente em ciclo_de_busca(), como qualquer scraper.
        definir_metadado(f"baixa_frequencia_ultimo_dia_{perfil.chave}", date.today().isoformat())

    return scrapers


def _proximo_bloco_termos(perfil: Perfil) -> list[str]:
    """Termos deste ciclo: os PRIORITÁRIOS (todo ciclo, fora do rodízio) mais
    um BLOCO fixo (perfil.termos_por_ciclo) do resto, começando de onde o
    ciclo anterior parou e avançando
    — volta pro início quando chega no fim da lista. A posição fica salva
    no jobs.db (tabela metadados, chave com sufixo do perfil — dois perfis
    rotacionam de forma independente), então sobrevive entre execuções do
    GitHub Actions (cada run é uma máquina nova).

    Isso é o que desacopla custo por ciclo do tamanho da lista de termos:
    lista grande leva mais ciclos pra cobrir tudo, mas cada ciclo individual
    continua custando o mesmo. Sem isso, dobrar a lista de termos dobrava o
    tempo de TODO ciclo.
    """
    # MEDIDO: uma vaga real ("Analista de Dados", JCPM Shoppings, Recife)
    # nunca foi notificada — e nao por causa do filtro: o titulo bate a
    # keyword mais forte da lista e Recife e uma das 8 cidades. Ela nunca
    # chegou a ser BUSCADA. Com 44 termos e 10 por ciclo, uma volta completa
    # leva 13 horas, e o rodizio e alfabetico: "analista de dados" disputa vez
    # de igual pra igual com "bigquery" e "looker".
    #
    # perfil.termos_prioritarios sai do rodizio e entra em TODO ciclo. Os
    # demais continuam rodando como antes, so que num conjunto menor.
    prioritarios = [t for t in perfil.termos_prioritarios if t in perfil.termos_busca]
    rodizio = [t for t in perfil.termos_busca if t not in prioritarios]

    total = len(rodizio)
    if total == 0:
        return list(prioritarios)

    tamanho_bloco = min(perfil.termos_por_ciclo, total)

    chave_offset = f"termos_offset_{perfil.chave}"
    offset_salvo = obter_metadado(chave_offset)
    # % total protege contra a lista ter encolhido desde o último ciclo
    # (termo removido do config.py) — sem isso, um offset salvo maior que o
    # tamanho atual da lista quebraria o acesso por índice abaixo.
    offset = int(offset_salvo) % total if offset_salvo else 0

    bloco = [rodizio[(offset + i) % total] for i in range(tamanho_bloco)]

    definir_metadado(chave_offset, str((offset + tamanho_bloco) % total))

    return list(prioritarios) + bloco


def _enviar_heartbeat_diario(
    perfil: Perfil, total_novas: int, scrapers_com_problema: list[str], total_fontes: int
):
    """No máximo 1 mensagem por dia (por perfil) confirmando que o ciclo
    rodou.

    O alerta de saúde só dispara quando ≥50% das fontes falha — mas se o
    workflow parar de rodar por completo (cron desabilitado pelo GitHub
    Actions por inatividade do repositório, erro de config, etc.), não
    existe ALERTA NENHUM disso: silêncio no Telegram fica idêntico a "rodou
    e não achou vaga nova". O heartbeat fecha essa lacuna — se ele parar de
    chegar um dia, o problema é o workflow não estar rodando, não a busca
    não ter achado nada. Por perfil: silêncio só do perfil Internacional
    (por exemplo) fica visível mesmo com o perfil Brasil rodando normal.

    A data do último envio fica salva no próprio jobs.db (tabela
    metadados), então sobrevive entre execuções do GitHub Actions (cada
    run é uma máquina nova) e não manda duplicado se o workflow rodar mais
    de uma vez no mesmo dia (cron normal ou workflow_dispatch manual).
    """
    chave = f"heartbeat_ultimo_dia_{perfil.chave}"
    hoje = date.today().isoformat()
    if obter_metadado(chave) == hoje:
        return

    hora_brasilia = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if scrapers_com_problema:
        status = f"{len(scrapers_com_problema)}/{total_fontes} fonte(s) com problema"
    else:
        status = "todas as fontes ok"

    enviar_mensagem(
        f"💓 <b>JobRadar {perfil.nome} ativo</b>\n\n"
        f"Confirmação diária: o ciclo rodou agora ({hora_brasilia}, {status}). "
        f"{total_novas} vaga(s) nova(s) neste ciclo.\n\n"
        "Se essa mensagem parar de chegar, o workflow parou de rodar — "
        "não que faltou vaga."
    )
    definir_metadado(chave, hoje)


def _enviar_digest_diario(perfil: Perfil):
    """No máximo 1 digest por dia (por perfil) — ver item 08. Junta tudo
    que ficou digest_pendente=1 desde o último envio (pode ser de vários
    ciclos de 3h) e manda ranqueado, melhor primeiro.

    Disparo: no ciclo cujo horário UTC bate com DIGEST_HORA_UTC (0 =
    meia-noite UTC = 21h em Brasília) — o cron já passa por essa hora
    exata todo dia, não precisa de agendamento à parte. Mesma lógica de
    "só uma vez por dia" do heartbeat (data salva em metadados), mas com
    um reforço: se por qualquer motivo o ciclo exato de DIGEST_HORA_UTC
    falhar/pular um dia inteiro, manda no primeiro ciclo depois de 24h
    sem envio — não deixa a fila crescer indefinidamente esperando um
    horário exato que pode não voltar a bater certo (ex: workflow atrasado
    pelo GitHub Actions naquele dia).
    """
    chave = f"digest_ultimo_dia_{perfil.chave}"
    agora = datetime.now(timezone.utc)
    # Dia em UTC, não date.today() (que é o dia LOCAL da máquina). A hora
    # comparada logo abaixo é UTC; misturar os dois dava resultado
    # diferente rodando no GitHub Actions (UTC) e na máquina da usuária
    # (UTC-3) — no Brasil, entre 21h e meia-noite o "hoje" local já é o
    # dia anterior ao "hoje" UTC.
    hoje = agora.date()

    if obter_metadado(chave) == hoje.isoformat():
        return

    # MEDIDO em produção: o digest NUNCA foi enviado. Prova direta — a
    # tabela metadados do jobs.db de produção tem heartbeat_ultimo_dia_*
    # (das duas chaves, atualizadas), e nenhum digest_ultimo_dia_*. O
    # heartbeat é disparado na linha ANTERIOR a esta função, no mesmo
    # ciclo: se ele chega e o digest não, a diferença é a condição de
    # horário. Resultado: 408 vagas presas na fila, acumulando desde que o
    # recurso existe, sem nunca chegar no Telegram.
    #
    # Eram duas causas somadas:
    #
    # 1. "agora.hour == DIGEST_HORA_UTC" exige que o ciclo TERMINE dentro
    #    de uma janela de 1 hora. Mas o cron só COMEÇA às 00:00 UTC e o
    #    ciclo dura ~80 min (medido pelos commits do robô: a execução das
    #    00:00 commitou às 02:14). Quando esta função roda, já é 1h ou 2h
    #    — a janela nunca está aberta.
    #
    # 2. A rede de segurança para o caso acima ("se pular um dia, manda no
    #    ciclo seguinte") exigia ultimo_envio_str is not None, ou seja, um
    #    envio anterior registrado. Como nunca houve o primeiro, ela nunca
    #    ligava: dependia exatamente daquilo que deveria consertar.
    #
    # A regra agora é "ainda não enviei hoje E já passou da hora
    # configurada" em vez de "a hora é exatamente X". Isso cobre os dois
    # casos de uma vez, sem precisar da rede de segurança separada: o
    # digest sai no PRIMEIRO ciclo do dia UTC que terminar depois de
    # DIGEST_HORA_UTC, independente de quanto o ciclo demorou ou de o
    # GitHub Actions ter atrasado o agendamento. Com DIGEST_HORA_UTC = 0,
    # é o primeiro ciclo de cada dia UTC (~22h de Brasília).
    #
    # Continua no máximo 1 por dia: o metadado só é gravado depois do
    # envio confirmado, e a checagem acima corta o resto do dia.
    if agora.hour < DIGEST_HORA_UTC:
        return

    vagas_pendentes = obter_vagas_pendentes_digest(perfil.chave)
    if not vagas_pendentes:
        # Marca mesmo sem vaga nenhuma — senão o "atrasado" acima dispara
        # todo ciclo seguinte até aparecer alguma vaga pendente de novo.
        definir_metadado(chave, hoje.isoformat())
        return

    if enviar_digest(vagas_pendentes, perfil.nome):
        marcar_digest_enviado(perfil.chave)
        definir_metadado(chave, hoje.isoformat())
        logger.info(f"[{perfil.nome}] Digest diário enviado: {len(vagas_pendentes)} vaga(s).")
    else:
        # Não marca metadado nem limpa a fila — tenta de novo no próximo
        # ciclo (ver enviar_digest/marcar_digest_enviado: preferir duplicar
        # a perder vaga).
        logger.warning(
            f"[{perfil.nome}] Falha ao enviar digest diário ({len(vagas_pendentes)} vaga(s) "
            "pendentes) - tenta de novo no próximo ciclo."
        )


# Quantos ciclos seguidos sem UMA vaga bruta antes de avisar que a fonte
# morreu. 3 ciclos = ~9 horas.
#
# MEDIDO (02/10), nos ciclos 388-390: a WeWorkRemotely voltou 0, depois 4,
# depois 0. Com limiar 1 ou 2 ela dispararia alerta sem ter problema -- fonte
# pequena tem dia fraco. A Gupy voltou 0 nos TRES, e e essa que precisa
# avisar. 3 separa os dois casos com folga.
#
# O QUE ACONTECEU DEPOIS, em producao (03/10) -- e vale mais que o paragrafo
# acima, porque e a primeira vez que este alerta disparou de verdade:
#
#   03:54 do ciclo 394 -- "WeWorkRemotelyIntlScraper esta sem trazer vaga ha 3
#   ciclos seguidos". As 11:21 do ciclo 395 ela voltou com 4 vagas.
#
# Ou seja: o alerta cumpriu a especificacao e a especificacao e que estava
# apertada pra esta fonte. O limiar 3 foi calibrado na morte da Gupy, que traz
# centenas por ciclo; a WeWorkRemotely traz 4 num dia bom e 0 nos outros, e
# pra ela tres ciclos vazios seguidos e rotina. O paragrafo acima usou 0-4-0
# como prova de que 3 bastava, e 0-4-0 so nao bateu 3 por sorte da amostra.
#
# DECISAO DA USUARIA, 03/10: fica como esta. Entao o numero 3 continua, e este
# bloco existe pra que o proximo alerta da WeWorkRemotely seja reconhecido
# como esperado em vez de investigado do zero. Se um dia incomodar, o conserto
# ja esta desenhado: limiar por fonte, maior pras de FREQUENCIA_BAIXA, com o
# numero tirado do historico de cada uma.
CICLOS_ZERADOS_PRA_ALERTAR = 3


def _chave_zeros(nome: str) -> str:
    return f"zeros_consecutivos_{nome}"


def _chave_ja_avisou(nome: str) -> str:
    return f"alerta_fonte_morta_{nome}"


def avaliar_fonte_morta(trouxe_vaga: bool, zeros_antes: str | None,
                        ja_avisou: str | None) -> tuple[int, bool, bool]:
    """Decide, pra UMA fonte, o novo contador de zeros e se cabe avisar.

    Devolve (zeros_agora, deve_avisar, deve_avisar_que_voltou).

    POR QUE POR FONTE, E NAO PELA MAIORIA. O alerta de saude existente exige
    maioria ESTRITA das fontes com problema, e isso esta certo pro que ele
    mede ("o ciclo inteiro degringolou"). Mas uma fonte morrendo SOZINHA passa
    invisivel, e foi o que aconteceu duas vezes:

      · 01/09: a Solides caiu de ~400 vagas pra 70 e ninguem viu.
      · desde 02/10 (pelo menos): a Gupy responde 404 em TODO termo, devolve
        zero vaga, e tambem ninguem viu -- descoberto por acaso, ao olhar log
        de ciclo por outro motivo.

    Nos dois casos o log DIZIA a verdade ("resposta inesperada da API, nao e
    busca vazia" -- correcao feita em 31/08). O sistema sabia e nao avisava.

    POR QUE ESPERAR 3 CICLOS, E NAO AVISAR NO PRIMEIRO. Esta na docstring de
    _deve_alertar_saude e vale igual aqui: "alerta que dispara sem motivo e
    pior que alerta que nao existe -- depois de duas ou tres vezes, deixa de
    ser lido". Fonte pequena tem dia de zero legitimo (a WeWorkRemotely fez
    0, 4, 0 nos ciclos 388-390). Exigir 3 seguidos separa "dia fraco" de
    "morreu" sem precisar saber nada sobre a fonte.

    AVISA UMA VEZ POR QUEDA, nao por ciclo: ja_avisou segura o resto. Sem
    isso, fonte morta vira 8 mensagens por dia ate alguem consertar -- e o
    alerta morre de tanto repetir.
    """
    try:
        zeros = int(zeros_antes or 0)
    except ValueError:
        zeros = 0

    if trouxe_vaga:
        # Voltou. Avisa a recuperacao SO se a queda tinha sido avisada --
        # senao seria mensagem sobre um problema que ela nunca soube que teve.
        return 0, False, bool(ja_avisou)

    zeros += 1
    deve = zeros >= CICLOS_ZERADOS_PRA_ALERTAR and not ja_avisou
    return zeros, deve, False


def _registrar_saude_da_fonte(perfil, nome: str, trouxe_vaga: bool) -> None:
    """Guarda o contador de zeros da fonte e avisa no Telegram quando ela
    morre -- ou quando volta. Estado vive na tabela `metadados`, a mesma que
    guarda o rodizio de termos e o controle do digest."""
    zeros, avisar, voltou = avaliar_fonte_morta(
        trouxe_vaga,
        obter_metadado(_chave_zeros(nome)),
        obter_metadado(_chave_ja_avisou(nome)),
    )
    definir_metadado(_chave_zeros(nome), str(zeros))

    if avisar:
        logger.error(
            f"[{perfil.nome}] {nome} está sem trazer vaga há {zeros} ciclos "
            "seguidos — tratada como fonte morta, alerta enviado."
        )
        if enviar_mensagem(
            f"🔴 <b>Fonte morta: {nome}</b>\n\n"
            f"Não trouxe <b>uma única vaga bruta</b> nos últimos {zeros} ciclos "
            f"(~{zeros * 3}h), no perfil {perfil.nome}.\n\n"
            "Zero vaga bruta não é \"não tem vaga hoje\" — é a fonte não "
            "respondendo. Vale olhar o log do ciclo: costuma haver status 403, "
            "404 ou 504 ali dizendo o motivo."
        ):
            definir_metadado(_chave_ja_avisou(nome), str(zeros))
    elif voltou:
        logger.info(f"[{perfil.nome}] {nome} voltou a trazer vaga.")
        if enviar_mensagem(f"🟢 <b>{nome} voltou</b>\n\nA fonte está trazendo vaga de novo."):
            definir_metadado(_chave_ja_avisou(nome), "")


def _deve_alertar_saude(com_problema: int, total: int) -> bool:
    """A maioria ESTRITA das fontes falhou neste ciclo?

    MEDIDO: a regra era ">= metade", o que com 2 fontes significa que UMA
    sozinha ja dispara o alerta. Isso passou a importar quando o Indeed foi
    desligado e o perfil Internacional ficou com 2 fontes: o WeWorkRemotely e
    pequeno (5 vagas no ciclo medido, vazio em 9 dos 10 termos), entao um dia
    mais fraco viraria "JobRadar com problema" sem haver problema nenhum.

    Alerta que dispara sem motivo e pior que alerta que nao existe: depois de
    duas ou tres vezes, ele deixa de ser lido -- e ai nao serve mais nem
    quando o problema e real.

    Maioria ESTRITA (">" em vez de ">=") resolve sem enfraquecer o resto:

        2 fontes -> exige 2 (antes 1)  <- o caso que motivou a mudanca
        3 fontes -> exige 2 (igual)
        7 fontes -> exige 4 (igual)
        8 fontes -> exige 5 (antes 4)

    Ou seja: com 2 fontes o alerta passa a significar "as duas cairam", que e
    o que "com problema" deveria querer dizer.
    """
    if total <= 0:
        return False
    return com_problema > total / 2

def ciclo_de_busca(perfil: Perfil):
    total_novas = 0
    total_brutas = 0
    total_filtradas = 0
    scrapers_com_problema = []
    descartes_escopo_ciclo: Counter = Counter()
    # Diagnóstico (ver Job.rejeitada_so_pelo_cargo): vaga numa das cidades
    # aceitas que só não passou porque o título não bate keyword nenhuma.
    # Existe pra medir se vale abrir a descrição dessas vagas — hoje o filtro
    # lê só o título, e vaga de BI com nome comercial escapa.
    titulo_barrou_em_cidade: list[str] = []

    termos_do_ciclo = _proximo_bloco_termos(perfil)
    logger.info(
        f"[{perfil.nome}] Bloco de termos deste ciclo: {len(termos_do_ciclo)}/"
        f"{len(perfil.termos_busca)} — {', '.join(termos_do_ciclo)}"
    )
    scrapers = _construir_scrapers(perfil, termos_do_ciclo)

    # A parte lenta (abrir navegador, navegar, esperar seletor) roda em
    # paralelo aqui. Tudo que segue (filtrar, checar dedup, notificar,
    # salvar) continua rodando só na thread principal, um scraper de cada
    # vez, conforme a future dele termina — nunca duas threads escrevendo
    # no SQLite ou chamando o Telegram ao mesmo tempo. Cada scraper já é
    # auto-contido (cria e fecha seu(s) próprio(s) browser(s) Playwright
    # dentro de buscar_vagas()), então dá pra rodar vários ao mesmo tempo em
    # threads sem risco — nenhum compartilha Browser/Page com outro.
    with ThreadPoolExecutor(max_workers=perfil.max_scrapers_concorrentes) as executor:
        futures = {executor.submit(scraper.buscar_vagas): scraper for scraper in scrapers}

        for future in as_completed(futures):
            scraper = futures[future]
            nome = scraper.__class__.__name__

            try:
                vagas = future.result()
            except Exception as e:
                logger.error(f"[{perfil.nome}] Erro no scraper {nome}: {e}")
                scrapers_com_problema.append(nome)
                _registrar_saude_da_fonte(perfil, nome, trouxe_vaga=False)
                continue

            # Cada scraper trata timeout por termo internamente (só loga e
            # segue pro próximo termo), então um site totalmente bloqueado
            # não lança exceção pra cá — só devolve lista vazia. Por isso
            # também contamos "0 vaga bruta nessa fonte" como problema, não
            # só exceção.
            if not vagas:
                logger.warning(f"[{perfil.nome}] {nome} não retornou nenhuma vaga bruta neste ciclo.")
                scrapers_com_problema.append(nome)
                _registrar_saude_da_fonte(perfil, nome, trouxe_vaga=False)
                continue

            _registrar_saude_da_fonte(perfil, nome, trouxe_vaga=True)

            total_brutas += len(vagas)
            vagas_filtradas, descartes = filtrar_vagas(vagas, perfil.regras)
            descartes_escopo_ciclo.update(descartes)

            ids_aprovadas = {v.id for v in vagas_filtradas}
            titulo_barrou_em_cidade.extend(
                f"{v.titulo} — {v.empresa} ({v.local})"
                for v in vagas
                if v.id not in ids_aprovadas and v.rejeitada_so_pelo_cargo(perfil.regras)
            )

            # Eixo secundário (Ibéria, quando ligado): mesma regra de cargo,
            # cidade diferente — sem duplicar o que já bateu na regra
            # primária.
            vagas_secundarias = []
            if perfil.eixo_secundario_ativo and perfil.regras_eixo_secundario is not None:
                ids_filtradas = {v.id for v in vagas_filtradas}
                candidatas, descartes_secundario = filtrar_vagas(vagas, perfil.regras_eixo_secundario)
                descartes_escopo_ciclo.update(descartes_secundario)
                vagas_secundarias = [v for v in candidatas if v.id not in ids_filtradas]

            total_filtradas += len(vagas_filtradas) + len(vagas_secundarias)

            novas_da_fonte = 0
            for vaga in vagas_filtradas:
                if ja_vista(vaga):
                    continue

                # Item 08: só notifica na hora quando a relevância passa do
                # limiar (ver LIMIAR_DIGEST_IMEDIATO em config.py) — abaixo
                # disso, vai pra fila do digest diário sem mensagem
                # individual (ver _enviar_digest_diario). Fila é salvar com
                # digest_pendente=True: não tem "notificação que pode
                # falhar" nesse caminho (a mensagem só sai no digest, depois),
                # então salvar direto não arrisca perder a vaga do jeito que
                # salvar ANTES de notificar arriscava no caminho imediato.
                #
                # MEDIDO: vaga com Job.publicacao_antiga (publicado_em "há X
                # meses/anos" — ver job.py) nunca vai pra notificação
                # imediata, mesmo com relevância alta — score mede "bate com
                # o que você procura", não "é recente". Site com pouco
                # volume pra um termo deixa vaga de meses atrás na página
                # visível (confirmado ao vivo: Sólides ordena por data, mas
                # sem volume novo suficiente a antiga não sai da 1ª página).
                # Não é descartada (mesma vaga ainda pode estar aberta) — só
                # sai do caminho "🚨 urgente" e vai pro digest em lote.
                if vaga.relevancia >= LIMIAR_DIGEST_IMEDIATO and not vaga.publicacao_antiga:
                    # Notifica ANTES de salvar. Se salvasse primeiro e o
                    # Telegram falhasse, a vaga ficava marcada como "vista"
                    # pra sempre — o próximo ciclo pulava ela em ja_vista()
                    # e a vaga se perdia sem nunca ter sido notificada de
                    # verdade.
                    if not notificar_vaga(vaga):
                        logger.warning(
                            f"[{perfil.nome}] Falha ao notificar '{vaga.titulo}' - não marcada "
                            "como vista, tenta de novo no próximo ciclo."
                        )
                        continue
                    salvar_vaga(vaga, perfil_chave=perfil.chave)
                    logger.info(f"[{perfil.nome}] Nova vaga: {vaga.titulo} - {vaga.empresa}")
                else:
                    salvar_vaga(vaga, perfil_chave=perfil.chave, digest_pendente=True)
                    motivo_digest = "vaga antiga" if vaga.publicacao_antiga else f"relevância {vaga.relevancia}/10"
                    logger.info(
                        f"[{perfil.nome}] Nova vaga (digest, {motivo_digest}): "
                        f"{vaga.titulo} - {vaga.empresa}"
                    )

                total_novas += 1
                novas_da_fonte += 1

            for vaga in vagas_secundarias:
                if ja_vista(vaga):
                    continue

                # Mesma regra de vaga antiga do loop acima.
                if vaga.relevancia >= LIMIAR_DIGEST_IMEDIATO and not vaga.publicacao_antiga:
                    if not notificar_vaga_exploratoria(vaga):
                        logger.warning(
                            f"[{perfil.nome}] Falha ao notificar '{vaga.titulo}' (exploratória) - "
                            "não marcada como vista, tenta de novo no próximo ciclo."
                        )
                        continue
                    salvar_vaga(vaga, perfil_chave=perfil.chave)
                    logger.info(
                        f"[{perfil.nome}] Nova vaga exploratória ({perfil.eixo_secundario_rotulo}): "
                        f"{vaga.titulo} - {vaga.empresa}"
                    )
                else:
                    salvar_vaga(vaga, perfil_chave=perfil.chave, digest_pendente=True, exploratoria=True)
                    motivo_digest = "vaga antiga" if vaga.publicacao_antiga else f"relevância {vaga.relevancia}/10"
                    logger.info(
                        f"[{perfil.nome}] Nova vaga exploratória (digest, {motivo_digest}): "
                        f"{vaga.titulo} - {vaga.empresa}"
                    )

                total_novas += 1
                novas_da_fonte += 1

            # Funil por fonte: sem isso só dava pra ver bruta (por fonte) e
            # nova (só o total do ciclo) — o meio (quanto o filtro de
            # cargo/cidade descarta, fonte por fonte) ficava invisível.
            logger.info(
                f"[{perfil.nome}][{nome}] Funil: {len(vagas)} brutas → "
                f"{len(vagas_filtradas) + len(vagas_secundarias)} filtradas → {novas_da_fonte} novas"
            )

    logger.info(
        f"[{perfil.nome}] Ciclo concluído: {total_brutas} brutas → {total_filtradas} filtradas → "
        f"{total_novas} nova(s)."
    )

    # MEDIDO: descarte por escopo era invisível no log — o funil mostra
    # bruta → filtrada → nova, mas nunca QUAL escopo derrubou vaga nem
    # QUANTAS. Um escopo mal reconhecido (texto cru tipo "lagos nigeria",
    # não mapeado em _MERCADOS_REMOTO) barra do jeito certo, mas some sem
    # rastro — foi assim que um bug real (escopo virando allowlist) passou
    # despercebido até virar relato explícito. Loga só quando há descarte
    # (a maioria dos ciclos não tem nenhum), ordenado do que mais derrubou
    # vaga pro que menos derrubou.
    if descartes_escopo_ciclo:
        detalhe = "; ".join(
            f"{escopo} ({n})" for escopo, n in descartes_escopo_ciclo.most_common()
        )
        logger.info(f"[{perfil.nome}] Descarte por escopo: {detalhe}")

    # MEDIDO: uma vaga real ("Analista Comercial JR", Lactalis, Recife) não
    # foi notificada — local aceito, título sem nenhuma das 36 keywords, mas a
    # descrição com 5 dos 11 qualificadores de dados. Este contador mede
    # quantas vagas por ciclo caem nesse caso, pra decidir por número (e não
    # por palpite) se vale abrir a descrição delas. Mostra até 10 exemplos —
    # o suficiente pra julgar se são vagas de verdade ou ruído.
    if titulo_barrou_em_cidade:
        logger.info(
            f"[{perfil.nome}] Em cidade aceita, barradas só pelo título: "
            f"{len(titulo_barrou_em_cidade)}"
        )
        for exemplo in titulo_barrou_em_cidade[:10]:
            logger.info(f"[{perfil.nome}]   · {exemplo}")

    # Alerta de saúde: se a maioria das fontes falhou/voltou vazia, avisa no
    # Telegram. Sem isso, um bloqueio geral ou mudança de layout passaria
    # despercebido — o workflow do GitHub Actions continuaria "verde" mesmo
    # com tudo quebrado.
    if _deve_alertar_saude(len(scrapers_com_problema), len(scrapers)):
        enviar_mensagem(
            f"⚠️ <b>JobRadar {perfil.nome} com problema</b>\n\n"
            f"{len(scrapers_com_problema)}/{len(scrapers)} fontes falharam ou voltaram "
            f"vazias neste ciclo: {', '.join(scrapers_com_problema)}.\n\n"
            "Vale checar o log do GitHub Actions."
        )

    _enviar_heartbeat_diario(perfil, total_novas, scrapers_com_problema, len(scrapers))
    _enviar_digest_diario(perfil)


def _rodar_um_ciclo_de_cada(perfis: list[Perfil]):
    # Uma vez por execução, não por perfil: o offset do getUpdates (ver
    # processar_feedback_pendente) é global — feedback de vaga não tem
    # perfil, e rodar duas vezes na mesma execução só gastaria uma chamada
    # de API à toa (a segunda sempre veria "nada novo desde a última vez").
    processar_feedback_pendente()

    for perfil in perfis:
        print(f"\n{'=' * 50}")
        print(f"PERFIL: {perfil.nome.upper()}")
        print("=" * 50)

        print("\nPalavras monitoradas:")
        for palavra in perfil.palavras_monitoradas:
            print(f"• {palavra}")

        if perfil.paises_pesquisados:
            print("\nPaíses pesquisados:")
            for pais in perfil.paises_pesquisados:
                print(f"• {pais}")

        ciclo_de_busca(perfil)


def main():
    parser = argparse.ArgumentParser(description="JobRadar - monitor de vagas")
    parser.add_argument(
        "--perfil",
        required=True,
        nargs="+",
        choices=sorted(PERFIS.keys()),
        help=(
            "Qual(is) mercado(s) rodar nesta execução — 'brasil', 'internacional', "
            "ou os dois (--perfil brasil internacional)."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Roda um único ciclo de busca (de cada perfil selecionado) e encerra "
             "(usado no GitHub Actions, que já dispara o script periodicamente via cron).",
    )
    args = parser.parse_args()

    perfis_selecionados = [PERFIS[chave] for chave in args.perfil]

    if not args.once:
        print(f"\nIntervalo de checagem: {INTERVALO_MINUTOS} min\n")

    # Chamado UMA VEZ só, antes de qualquer perfil rodar — não por perfil.
    # A checagem de "banco suspeito" (ver database.py) compara se o arquivo
    # já existia ANTES desta execução; se cada perfil chamasse iniciar_db()
    # separadamente na mesma execução, o segundo perfil veria o arquivo que
    # o primeiro acabou de criar/popular momentos atrás e podia disparar
    # falso positivo (arquivo "já existia" só porque o perfil anterior já
    # rodou nesta mesma execução, não porque é run antigo de verdade).
    try:
        iniciar_db()
    except BancoVazioSuspeito as e:
        logger.error(str(e))
        nomes = ", ".join(p.nome for p in perfis_selecionados)
        enviar_mensagem(f"🛑 <b>JobRadar abortado</b>\n\nPerfis desta execução: {nomes}\n\n{e}")
        sys.exit(1)

    if args.once:
        _rodar_um_ciclo_de_cada(perfis_selecionados)
        return

    while True:
        _rodar_um_ciclo_de_cada(perfis_selecionados)
        logger.info(f"Aguardando {INTERVALO_MINUTOS} minutos até a próxima checagem...")
        time.sleep(INTERVALO_MINUTOS * 60)


if __name__ == "__main__":
    main()
