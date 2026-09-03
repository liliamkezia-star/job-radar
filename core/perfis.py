"""Perfis de mercado (Brasil / Internacional) do JobRadar.

Antes disso existiam DOIS programas quase idênticos — main.py e
main_intl.py — cada um com sua própria cópia do ciclo de busca (buscar →
filtrar → checar dedup → notificar antes de salvar → funil por fonte →
alerta de saúde → heartbeat). O que diverge de verdade entre os dois
mercados é só DADO: fontes, termos de busca, cidades aceitas, regra de
cargo. A lógica de execução em si é a mesma — daí valer a pena descrever
cada mercado como um objeto (`Perfil`) e ter um único motor (main.py) que
roda qualquer um dos dois, escolhido em tempo de execução via `--perfil`.

Cada `Perfil` tem uma `chave` curta (usada tanto no argumento --perfil
quanto como sufixo nas chaves da tabela `metadados` — rodízio de termos,
cadência de baixa frequência e heartbeat ficam isolados por perfil, mesmo
os dois perfis rodando na mesma execução do workflow e escrevendo no mesmo
jobs.db).
"""

from dataclasses import dataclass, field

from core.config import (
    KEYWORDS,
    KEYWORDS_CARGO_FORTE,
    KEYWORDS_CARGO_AMBIGUO,
    QUALIFICADORES_DADOS,
    FERRAMENTAS_TITULO,
    QUALIFICADORES_CARGO,
    CIDADES,
    CIDADES_EUROPA_IBERICA,
    ATIVAR_EIXO_IBERICO_BR,
    MERCADOS_REMOTO_ACEITOS,
    TERMOS_BUSCA,
    TERMOS_PRIORITARIOS,
    TERMOS_POR_CICLO,
)
from core.config_intl import (
    KEYWORDS_INTL,
    KEYWORDS_CARGO_AMBIGUO_INTL,
    QUALIFICADORES_DADOS,
    TERMOS_BUSCA_INTL,
    TERMOS_POR_CICLO_INTL,
    LOCATIONS_INTL,
    DOMINIOS_INDEED_INTL,
    CIDADES_INTL,
    ATIVAR_EIXO_IBERICO,
    MERCADOS_REMOTO_ACEITOS_INTL,
    IDIOMAS_EXIGIDOS_INTL,
)
from core.job import RegrasFiltro
from scrapers.catho import CathoScraper
from scrapers.geekhunter import GeekHunterScraper
from scrapers.gupy import GupyScraper
from scrapers.indeed import IndeedScraper
from scrapers.indeed_intl import IndeedIntlScraper
from scrapers.jobs99 import Jobs99Scraper
from scrapers.linkedin import LinkedInScraper
from scrapers.linkedin_intl import LinkedInIntlScraper
from scrapers.senior import SeniorScraper
from scrapers.solides import SolidesScraper
from scrapers.weworkremotely_intl import WeWorkRemotelyIntlScraper

# "alta" roda TODO ciclo; "baixa" roda só na primeira execução de cada dia
# (ver _fontes_baixa_frequencia_ja_rodaram_hoje em main.py). Existe pra
# fonte de baixo rendimento não pesar no custo de todo ciclo.
FREQUENCIA_ALTA = "alta"
FREQUENCIA_BAIXA = "baixa"


@dataclass
class DefinicaoScraper:
    """Uma fonte dentro de um perfil.

    `kwargs_extras`: além de `termos_busca` (que todo scraper recebe), fonte
    internacional precisa de argumento próprio — `locations=` no
    LinkedInIntlScraper, `dominios=` no IndeedIntlScraper. Fonte do perfil
    BR não precisa de nada extra (LinkedInScraper já traz seus países
    default de config.py), então fica com kwargs_extras vazio.
    """
    classe: type
    frequencia: str
    kwargs_extras: dict = field(default_factory=dict)


@dataclass
class Perfil:
    chave: str  # "brasil" / "internacional" — valor do --perfil e sufixo de chave em metadados
    nome: str  # nome de exibição nos logs/Telegram, ex: "Internacional"
    palavras_monitoradas: list[str]
    paises_pesquisados: list[str] | None  # só o perfil internacional imprime isso no banner
    regras: RegrasFiltro
    regras_eixo_secundario: RegrasFiltro | None
    eixo_secundario_ativo: bool
    eixo_secundario_rotulo: str  # usado só no texto do log ("Nova vaga exploratória (<rótulo>)")
    termos_busca: list[str]
    termos_por_ciclo: int
    definicao_scrapers: list[DefinicaoScraper]
    # Termos fora do rodízio, buscados em TODO ciclo (ver TERMOS_PRIORITARIOS
    # em config.py). Lista vazia = tudo entra no rodízio, que é o
    # comportamento de antes deste campo existir (perfil internacional).
    termos_prioritarios: list[str] = field(default_factory=list)
    max_scrapers_concorrentes: int = 4


# Regra primária: cidade brasileira (Nordeste) ou "Remoto" com mercado
# Brasil/LATAM/Portugal/Espanha aceito (ver Job.escopo_remoto).
_REGRAS_BR = RegrasFiltro(
    keywords_forte=KEYWORDS_CARGO_FORTE,
    keywords_ambiguo=KEYWORDS_CARGO_AMBIGUO,
    qualificadores_dados=QUALIFICADORES_DADOS,
    ferramentas_titulo=FERRAMENTAS_TITULO,
    qualificadores_cargo=QUALIFICADORES_CARGO,
    cidades=CIDADES,
    mercados_remoto_aceitos=MERCADOS_REMOTO_ACEITOS,
)

# Eixo secundário (Ibéria): mesma regra de cargo, cidade europeia em vez de
# brasileira. DESLIGADO — ver ATIVAR_EIXO_IBERICO_BR em config.py: usuário só
# quer vaga remota do mercado internacional, não presencial/híbrida em
# Lisboa/Madrid. Continua definido (não apagado) pra religar fácil depois.
_REGRAS_BR_IBERIA = RegrasFiltro(
    keywords_forte=KEYWORDS_CARGO_FORTE,
    keywords_ambiguo=KEYWORDS_CARGO_AMBIGUO,
    qualificadores_dados=QUALIFICADORES_DADOS,
    ferramentas_titulo=FERRAMENTAS_TITULO,
    qualificadores_cargo=QUALIFICADORES_CARGO,
    cidades=CIDADES_EUROPA_IBERICA,
)

# Revelo não entrou: o portal de vagas exige login pra navegar, não dá pra
# fazer scraping público de forma confiável.
#
# Trampos SAIU depois de investigar por que rendia 0 notificação em 6 dias
# (~71 vagas brutas/ciclo com 99Jobs). Testei o parâmetro de busca (term=)
# direto na API do site com "analista de dados" e "business intelligence" —
# os dois devolveram a MESMA lista de vagas (Diretor de Arte, SDR,
# Atendimento Publicitário...), nenhuma de dados. A busca do site não
# filtra nada, é sempre o feed genérico recente; a categoria própria
# "Análise e Gestão de Dados" do site tem só 4 vagas no total, contra 226
# de "Emprego" geral (majoritariamente marketing/criação/comercial). O
# vazio vinha da FONTE (site não é de tecnologia/dados) — código do
# scraper continua em scrapers/trampos.py se algum dia mudar.
#
# 99Jobs FICOU: mesma investigação, resultado diferente. A busca por
# "analista de dados" no site retorna vaga de verdade relevante ("Analista
# de Dados Sênior" etc.) — só que presencial/híbrida em São Paulo, fora da
# lista CIDADES e sem sinal de remoto. O vazio aí vem do FILTRO de
# localização (a mesma limitação que afeta o sistema todo), não da fonte —
# remover jogaria fora uma fonte que funciona.
#
# Cadência por fonte: medido em jobradar.log + jobs.db (vagas notificadas /
# vagas brutas retornadas, somado por fonte). Gupy e LinkedIn confirmam o
# que foi medido à parte (Gupy ~2,6%); Catho, GeekHunter e 99Jobs ficam
# abaixo de 1%.
#
# WeWorkRemotelyIntlScraper reaproveitado aqui (não duplicado): é agregador
# de vaga 100% remota que cobre o mercado "remoto internacional" que
# nenhuma das 8 fontes brasileiras alcança — mesmo scraper usado no perfil
# internacional, sem nada daquele perfil hardcoded. Sem medição própria
# ainda pra essa combinação (fonte + termos em português) — FREQUENCIA_BAIXA
# até medir rendimento real.
_SCRAPERS_BR = [
    DefinicaoScraper(GupyScraper, FREQUENCIA_ALTA),        # ~2,6% de rendimento
    DefinicaoScraper(LinkedInScraper, FREQUENCIA_ALTA),     # ~8,5% — a melhor fonte de longe
    DefinicaoScraper(SolidesScraper, FREQUENCIA_ALTA),      # ~1,1%
    # Indeed SAIU dos perfis (codigo continua em scrapers/indeed.py e
    # scrapers/indeed_intl.py, mesmo tratamento que o Trampos recebeu).
    #
    # MEDIDO em 3 ciclos consecutivos de producao (18/08): ZERO vaga bruta,
    # nas duas versoes. O log nao mostra "0 resultado" — mostra timeout na
    # PAGINA 1 de todo termo, em todos os 6 dominios de pais. Isso e
    # bloqueio anti-bot completo, nao ausencia de vaga. O proprio scraper ja
    # avisava do risco: IP de nuvem/datacenter (que e o do GitHub Actions) e
    # o mais bloqueado.
    #
    # Custo medido no relogio do log (os scrapers rodam em PARALELO, entao o
    # que importa e quem termina por ultimo):
    #
    #   Brasil        11m32s — gargalo e o LinkedIn (21:40:55), nao o Indeed
    #                 (21:33:42). Tirar daqui nao encurta o ciclo, so para
    #                 de gastar requisicao a toa.
    #   Internacional 25m42s — LinkedIn Intl termina 21:47:20 e o Indeed Intl
    #                 so 22:06:38. Ele SOZINHO estende o ciclo em 19 minutos,
    #                 entregando zero vaga.
    #
    # Ciclo completo: 37m14s -> ~18m. Sao ~2h30 por dia devolvidas.
    #
    # Pra religar quando/se o Indeed voltar a responder: descomente as duas
    # linhas abaixo (uma aqui, outra em _SCRAPERS_INTL). Nada mais precisa
    # mudar — imports, config e dominios continuam no lugar.
    # DefinicaoScraper(IndeedScraper, FREQUENCIA_ALTA),       # ~1,1%
    DefinicaoScraper(CathoScraper, FREQUENCIA_BAIXA),       # <1%, timeout frequente em headless
    DefinicaoScraper(GeekHunterScraper, FREQUENCIA_BAIXA),  # <1%
    DefinicaoScraper(Jobs99Scraper, FREQUENCIA_BAIXA),      # <1%, fonte confirmada funcionando
    DefinicaoScraper(WeWorkRemotelyIntlScraper, FREQUENCIA_BAIXA),  # nova, sem medição própria
    # MEDIDO ao vivo antes de ligar (3 termos, 398 vagas brutas): rendimento
    # de 0,3% — abaixo da Sólides (1,1%), a fonte mais fraca que ficou. A
    # busca da API casa pedaço de palavra, não o termo: "analista bi" trouxe
    # ANALISTA CONTÁBIL, ANALISTA DE CUSTOS, ANALISTA LOGÍSTICA. E só 1 das
    # 398 era remota — o portal é quase todo presencial, enquanto o remoto é
    # de onde vem a maior parte do volume deste projeto.
    #
    # Entra assim mesmo, e em FREQUENCIA_BAIXA, por três motivos:
    #
    # 1. Custo. 398 vagas em 4 SEGUNDOS, sem navegador. A Sólides gasta
    #    minutos pra render 1,1%. Por vaga útil, a conta favorece a Senior.
    # 2. Cobre a área mais fraca. A única aprovada foi presencial em Natal —
    #    e vaga presencial nas 8 cidades é o que o projeto menos acha (23 em
    #    1.279 no histórico).
    # 3. É a única fonte com data de publicação em 100% dos registros
    #    (398/398), contra praticamente zero nas outras.
    #
    # FREQUENCIA_BAIXA também porque o endpoint só foi testado de máquina
    # doméstica: o robô roda em IP de datacenter, que foi o que derrubou o
    # Indeed. Uma execução por dia mede sem multiplicar requisição.
    #
    # Critério de permanência, pra decidir por número e não por impressão
    # (mesmo critério que manteve o 99Jobs e tirou o Trampos): se numa semana
    # não trouxer vaga relevante das 8 cidades, sai.
    #
    # ---- VEREDITO PARCIAL, 03/09 (15 dias no ar, ZERO vaga no banco) ----
    #
    # O critério acima já venceu. Antes de remover, foi diagnosticado, porque
    # "não rende" e "está quebrada" pedem decisões opostas. MEDIDO: num ciclo
    # completo ela trouxe 1.847 vagas brutas e 0 passaram no filtro.
    #
    # A FONTE NÃO ESTÁ QUEBRADA. O mapeamento sai correto e as vagas são de
    # Dados de verdade:
    #
    #   Analista Engenharia de Dados Sênior      Igrejinha - RS         Híbrido
    #   ANALISTA POWER BI JR                     Ituiutaba/Canápolis-MG
    #   ANALISTA DE BUSINESS INTELLIGENCE PLENO  Goiânia                Presencial
    #   ANALISTA CIÊNCIA E ARQ DADOS PL          Ponta Grossa - PR      Presencial
    #
    # Elas caem por CIDADE. A Senior tem vaga em Porto Alegre, Maringá,
    # Blumenau, Veranópolis, Lajeado, Pelotas, Goiânia, Cuiabá, Ituiutaba --
    # nenhuma das nove aceitas. A base de clientes dela é Sul/Sudeste; o mapa
    # deste projeto é Nordeste mais Manaus. É incompatibilidade estrutural,
    # não defeito.
    #
    # A única vaga REMOTA da sondagem (Business Analyst II (CIGAM), Pelotas,
    # Remoto) foi rejeitada CORRETAMENTE: 'Business Analyst' é keyword ambígua
    # e exige qualificador de dados no título. A mesma vaga como 'Business
    # Analyst - Dados' passa. O filtro está certo.
    #
    # DECISÃO DA USUÁRIA: manter mais 15 dias, até 18/09. Custa ~30s por
    # ciclo, e a aposta é vaga REMOTA -- remoto no Brasil vale em qualquer
    # lugar, e a sondagem confirmou que a Senior publica vaga remota.
    # Se em 18/09 continuar zero, sai sem discussão.
    #
    # O QUE MUDARIA O VEREDITO: se as cidades aceitas passarem a incluir
    # Sul/Sudeste, esta fonte vira boa da noite pro dia -- ela já enxerga um
    # volume de vaga de Dados que o projeto hoje descarta por geografia.
    # Sondagem que produziu tudo isto: testar_senior.py.
    DefinicaoScraper(SeniorScraper, FREQUENCIA_BAIXA),      # 0,3%, mas 4s e cobre cidade
]

PERFIL_BR = Perfil(
    chave="brasil",
    nome="Brasil",
    palavras_monitoradas=KEYWORDS,
    paises_pesquisados=None,
    regras=_REGRAS_BR,
    regras_eixo_secundario=_REGRAS_BR_IBERIA,
    eixo_secundario_ativo=ATIVAR_EIXO_IBERICO_BR,
    eixo_secundario_rotulo="Ibéria",
    termos_busca=TERMOS_BUSCA,
    termos_por_ciclo=TERMOS_POR_CICLO,
    termos_prioritarios=TERMOS_PRIORITARIOS,
    definicao_scrapers=_SCRAPERS_BR,
    max_scrapers_concorrentes=4,
)


# Regra primária: só remoto ("Remote"/"Remoto" em CIDADES_INTL), mercado
# LATAM/Portugal/Espanha aceito.
#
# Cargo ambíguo entrou em 29/08 (ver KEYWORDS_CARGO_AMBIGUO_INTL em
# config_intl.py para a medição): +7 vagas em 175, zero ruído. Ferramenta
# continua fora — não foi medida.
#
# idiomas_exigidos: sem mercado declarado, exige espanhol/português/LATAM
# no título (ver IDIOMAS_EXIGIDOS_INTL e comentário em RegrasFiltro) — a
# busca já tentava garantir isso via termo, mas nunca era reconferido na
# vaga em si.
_REGRAS_INTL = RegrasFiltro(
    keywords_forte=KEYWORDS_INTL,
    keywords_ambiguo=KEYWORDS_CARGO_AMBIGUO_INTL,
    qualificadores_dados=QUALIFICADORES_DADOS,
    ferramentas_titulo=[],
    qualificadores_cargo=[],
    cidades=CIDADES_INTL,
    mercados_remoto_aceitos=MERCADOS_REMOTO_ACEITOS_INTL,
    idiomas_exigidos=IDIOMAS_EXIGIDOS_INTL,
)

# Eixo secundário (Ibéria): vaga presencial/híbrida em Portugal/Espanha,
# achada de propósito (LOCATIONS_INTL busca lá) mas que CIDADES_INTL (só
# remoto) rejeitaria. DESLIGADO — mesmo motivo do eixo BR acima.
# Mesmo cargo ambíguo da regra primária, de propósito: o eixo ibérico está
# DESLIGADO hoje, então isto não muda comportamento nenhum agora. Mas deixar
# os dois diferentes recriaria exatamente a divergência silenciosa que fez o
# perfil internacional ficar sem o mecanismo por tanto tempo.
_REGRAS_INTL_IBERIA = RegrasFiltro(
    keywords_forte=KEYWORDS_INTL,
    keywords_ambiguo=KEYWORDS_CARGO_AMBIGUO_INTL,
    qualificadores_dados=QUALIFICADORES_DADOS,
    ferramentas_titulo=[],
    qualificadores_cargo=[],
    cidades=CIDADES_EUROPA_IBERICA,
)

# As 3 fontes rodam toda vez (FREQUENCIA_ALTA) — perfil novo, sem medição de
# rendimento por fonte ainda que justifique separar em cadência alta/baixa
# como o perfil BR. Ajustar quando/se tiver dado real.
_SCRAPERS_INTL = [
    DefinicaoScraper(LinkedInIntlScraper, FREQUENCIA_ALTA, {"locations": LOCATIONS_INTL}),
    # Indeed Intl desligado — ver MEDIDO em _SCRAPERS_BR. Era o gargalo
    # absoluto do ciclo internacional: 19 dos 25 minutos, zero vaga.
    # DefinicaoScraper(IndeedIntlScraper, FREQUENCIA_ALTA, {"dominios": DOMINIOS_INDEED_INTL}),
    DefinicaoScraper(WeWorkRemotelyIntlScraper, FREQUENCIA_ALTA),
]

PERFIL_INTL = Perfil(
    chave="internacional",
    nome="Internacional",
    palavras_monitoradas=KEYWORDS_INTL,
    paises_pesquisados=LOCATIONS_INTL,
    regras=_REGRAS_INTL,
    regras_eixo_secundario=_REGRAS_INTL_IBERIA,
    eixo_secundario_ativo=ATIVAR_EIXO_IBERICO,
    eixo_secundario_rotulo="Ibéria",
    termos_busca=TERMOS_BUSCA_INTL,
    termos_por_ciclo=TERMOS_POR_CICLO_INTL,
    definicao_scrapers=_SCRAPERS_INTL,
    max_scrapers_concorrentes=3,
)

PERFIS = {
    PERFIL_BR.chave: PERFIL_BR,
    PERFIL_INTL.chave: PERFIL_INTL,
}
