
import os
from dotenv import load_dotenv

load_dotenv()

# Cargo forte: título que só existe mesmo em vaga de dados/BI, sem
# possibilidade real de ser outra área.
KEYWORDS_CARGO_FORTE = [
    "Analista de Dados",
    "Analista BI",
    "Analista de BI",
    "Business Intelligence",
    "Data Analytics",
    "Analista de Analytics",
    "Data Analyst",
    "Desenvolvedor BI",
    "Consultor BI",
    "Analista de Inteligência de Negócios",
    "BI Developer",
    "BI Analyst",
    "Analista de Reporting",
    "Analista de Inteligência de Mercado",
    "Analista de Indicadores",
    "Reporting Analyst",
    "Insights Analyst",
    "Data Insights Analyst",
    "MIS Analyst",
    "Analista de MIS",
    "Assistente de BI",
    "Auxiliar de BI",
    "Analista de Inteligência Comercial",
    "Data Specialist",
    "Data Quality Analyst",
    "Data Intelligence Analyst",
    "BI & Analytics Analyst",
    "Analytics Specialist",
    "Especialista em Dados",
    "Analista de Planejamento e Dados",
    # "Datos" (espanhol) não é "Dados" (português) — nenhuma keyword em
    # português cobre título em espanhol, mesmo sendo a mesma vaga. Faz
    # sentido aqui no pipeline BR (não só em config_intl.py) porque
    # LinkedInScraper já busca em Argentina/Chile (ver LOCATIONS_LINKEDIN).
    "Analista de Datos",
    "Analítica de Datos",
]

# Cargo ambíguo: título que também é usado em vaga sem nada a ver com
# dados/BI (ex: "Business Analyst" e "Analista de Negócios" existem em
# TI, finanças, RH, operações... qualquer área). Só conta como match se o
# título TAMBÉM tiver um QUALIFICADORES_DADOS junto — é o que permite ir
# adicionando cargo adjacente (Product Analyst, CRM Analyst, Marketing
# Analyst etc.) sem cada um virar fonte de ruído sozinho.
KEYWORDS_CARGO_AMBIGUO = [
    "Business Analyst",
    "Analista de Negócios",
    "Business Analytics",
    "Analista de Performance",
    # MEDIDO (2026-08-22) contra 293 vagas reais do LinkedIn (4 termos, 4
    # mercados): "Analyst" sozinho trouxe 2 vagas a mais, as DUAS certas —
    # "Data & Analytics Analyst" (Oliver Wyman, Lisboa) e "Analytics Analyst
    # - Remote Work" (Jalisco). Zero ruído na amostra.
    #
    # A Oliver Wyman e a Air Liquide ("Business & Data Integration Analyst -
    # HR Analytics") apareceram no log do dia anterior como barradas só pelo
    # título: sao vagas de dados que nenhuma keyword cobria, porque a lista
    # tem os cargos COMPOSTOS ("Data Analyst", "BI Analyst") e não o
    # substantivo sozinho.
    #
    # O risco previsto era "Data Center Operations Analyst" — "data center"
    # casa o qualificador "data" sem ter nada a ver com análise. Medido: não
    # apareceu nenhuma vez nas 293. Se aparecer, é aqui que se olha.
    #
    # NÃO entraram, e por quê:
    #   "Especialista" — 0 vagas a mais na mesma amostra. A vaga que motivou
    #       a ideia ("Especialista de Inteligencia de Negocio (BI)", TeleVía)
    #       não caiu na coleta. Sem número seria palpite.
    #   "Analista"     — 3 a mais, mas 2 eram "Analista de Banco de Dados".
    #       DBA é outra profissão, mesma razão que mantém "desenvolvedor" e
    #       "engenheiro" fora. Decisão da usuária em 22/08.
    "Analyst",
]

# Termo que precisa aparecer junto no título quando o cargo é ambíguo, pra
# confirmar que é vaga de dados/BI e não de outra área qualquer.
QUALIFICADORES_DADOS = [
    "dados",
    "data",
    "bi",
    "sql",
    "power bi",
    "analytics",
    "kpi",
    "dashboard",
    "métricas",
    "reporting",
    "insights",
]

# Ferramenta que aparece como núcleo do título ("Analista de Power BI").
# Só conta como match se o título TAMBÉM tiver uma palavra de cargo — é o
# espelho da regra de KEYWORDS_CARGO_AMBIGUO: lá o cargo é ambíguo e pede
# domínio, aqui a ferramenta é ambígua e pede cargo. Sem isso, "Power BI"
# sozinho aprovaria "Power BI Senior" e "Desenvolvedor (Power BI + Python)",
# que são vaga de desenvolvimento, não de análise.
FERRAMENTAS_TITULO = [
    "Power BI",
]

# Palavra de cargo que confirma que a vaga de ferramenta é de análise.
# "desenvolvedor"/"developer"/"engenheiro" ficam FORA de propósito: é o que
# mantém vaga de dev fora do radar.
QUALIFICADORES_CARGO = [
    "analista",
    "analyst",
    "especialista",
    "specialist",
    "consultor",
    "consultant",
]

KEYWORDS = KEYWORDS_CARGO_FORTE + KEYWORDS_CARGO_AMBIGUO

# Termos de busca enviados a cada site. Ficam separados das KEYWORDS de
# propósito: TERMOS_BUSCA é a rede ampla (o que é pesquisado em cada site,
# incluindo termos de ferramenta/stack pra achar vaga com título atípico),
# enquanto KEYWORDS é o filtro final e só olha o título da vaga já
# encontrada. Um termo de ferramenta (ex: "dax") só resulta em notificação
# se o TÍTULO da vaga também bater com uma keyword de cargo — isso evita
# falso positivo de vaga que só cita a ferramenta como diferencial.
#
# TERMOS_CARGO é derivado direto de KEYWORDS (em vez de mantido à mão em
# lista separada) — antes as duas listas divergiam: metade das KEYWORDS
# (ex: "Desenvolvedor BI", "BI Analyst", "Analista de Negócios") nunca era
# buscada de verdade, só existia como filtro, então só pegava essas vagas
# por sorte via outro termo. Com a derivação automática isso não pode mais
# acontecer — toda keyword nova em KEYWORDS já vira busca também.
TERMOS_CARGO_EXTRA = [
    # termos mais amplos que a keyword exata, mantidos por dar rede mais
    # larga na busca (a keyword em si é mais restrita, de propósito, pra
    # não gerar falso positivo no filtro de título).
    "power bi",
    "inteligência de mercado",
]

TERMOS_CARGO = sorted(set(k.lower() for k in KEYWORDS) | set(TERMOS_CARGO_EXTRA))

# MEDIDO em jobradar.log (12 rodízios completos, Gupy+99Jobs+GeekHunter+
# Solides): "dax" e "power query" nunca resultaram em nenhuma vaga nova
# notificada nessas 4 fontes — 0 em 48 buscas cada, a maioria vazia
# ("0 resultados reais") e o resto timeout. "microsoft fabric" teve 1 vaga
# no log inteiro (363 notificações) com o termo no título, e essa vaga
# também tinha "Power BI"/"Analista de BI" no título — já seria achada por
# termo que continua na lista. Timeout: os 3 termos concentraram metade
# (13 de 26) dos timeouts dessas 4 fontes sendo só 3 dos 42 termos (7%) —
# confirma o padrão relatado. Removidos por render zero e custarem sessão
# igual a um termo de cargo.
TERMOS_FERRAMENTA = [
    "sql",
    "python",
    "tableau",
    "qlik",
    "looker",
    "bigquery",
]

TERMOS_BUSCA = TERMOS_CARGO + TERMOS_FERRAMENTA

# Termos que rodam em TODO ciclo, fora do rodízio.
#
# MEDIDO: uma vaga real ("Analista de Dados", JCPM Shoppings, Recife) não
# foi notificada. O título bate a keyword mais forte da lista e o local é
# uma das 8 cidades — passaria no filtro sem esforço. Ela nunca chegou a ser
# BUSCADA: com 44 termos e 10 por ciclo, uma volta completa leva 13 horas, e
# o rodízio é alfabético — "analista de dados" disputa vez de igual pra igual
# com "bigquery" e "looker". Vaga publicada logo depois da passagem do termo
# fica invisível por meio dia, e em portal que recebe vaga o tempo todo isso
# é tempo demais.
#
# Prioridade não é sobre volume, é sobre o que define o perfil: são os
# títulos que a usuária de fato procura, e os que mais aparecem nas vagas
# que já foram aprovadas. Passam de 1x a cada 13h para 8x por dia.
#
# Custo: bloco por ciclo vai de 10 para 15 termos (+50%). O ciclo medido é
# de 18 min desde que o Indeed saiu, então cabe — antes disso, com 37 min,
# não caberia. É essa folga que torna a mudança possível agora.
TERMOS_PRIORITARIOS = [
    "analista de dados",
    "analista de bi",
    "business intelligence",
    "data analyst",
    "power bi",
]

# Medido: os TERMOS_BUSCA inteiros (hoje 42) rodando em TODO ciclo é o que
# gera as centenas de sessões de navegador por execução — o custo cresce
# linear com o tamanho da lista, e a lista só cresce (mais ainda com a
# expansão internacional puxando mais termos no radar). TERMOS_POR_CICLO é
# o tamanho do BLOCO usado por ciclo, não o total de termos — main.py roda
# um bloco por vez em rodízio (ver _proximo_bloco_termos) e avança pro
# próximo bloco no ciclo seguinte, salvando a posição no jobs.db. Isso
# desacopla custo por ciclo de tamanho da lista: dobrar TERMOS_BUSCA dobra
# quantos ciclos até cobrir tudo de novo, não o custo de cada ciclo.
TERMOS_POR_CICLO = 10

# Onde vaga HIBRIDA ou PRESENCIAL e aceita (mais "Remoto", que nao e
# cidade e sim a porta de entrada da regra de modalidade remota — ver
# _FLAGS_REMOTO em job.py). Vaga hibrida/presencial fora desta lista e
# rejeitada; e uma whitelist, nao uma preferencia de ordenacao.
#
# Lista revisada contra o requisito escrito pela usuaria: as seis cidades
# obrigatorias sao Campina Grande, Joao Pessoa, Recife, Natal, Caruaru e
# Manaus. Maceio e Aracaju ficam por decisao explicita dela (interessam,
# mesmo fora do requisito minimo).
#
# MEDIDO: a lista anterior era "Nordeste", nao "as cidades que interessam",
# e divergia do requisito nos dois sentidos ao mesmo tempo:
#   - FALTAVA Manaus. Confirmado em teste: "Manaus - AM" + Hibrido era
#     REJEITADA. Nenhuma vaga presencial/hibrida de Manaus podia entrar,
#     e a busca por cidade do LinkedIn (derivada desta lista) nunca
#     procurou la.
#   - SOBRAVAM Jaboatao, Teresina, Sao Luis e Petrolina, que aceitavam
#     hibrida/presencial fora da regra. Confirmado em teste.
# Nenhum dos 76 testes existentes cobria essas regras — por isso a
# divergencia sobreviveu. Agora esta em tests/test_regras_de_negocio.py.
#
# Custo: LOCATIONS_LINKEDIN_CIDADES_PRESENCIAL e derivada daqui, entao
# cada cidade e uma busca a mais por termo no LinkedIn. Sai de 11 cidades
# para 8 — menos requisicao por ciclo E cobrindo Manaus, que faltava.
CIDADES = [
    "Remoto",
    # As seis do requisito
    "Campina Grande",
    "João Pessoa",
    "Recife",
    "Natal",
    "Caruaru",
    "Manaus",
    # Mantidas por decisao da usuaria, alem do requisito minimo
    "Maceió",
    "Aracaju",
    # Fortaleza-CE: pedida em 21/08/2026, presencial e híbrida como as
    # demais. Cuidado que ela exige: existem "Fortaleza de Minas" (MG),
    # "Fortaleza dos Nogueiras" (MA) e "Fortaleza dos Valos" (RS) — as três
    # batem o nome. Quem as barra é _UF_DA_CIDADE["fortaleza"] = "ce" em
    # job.py, e ela só funciona pro formato do LinkedIn ("Fortaleza de
    # Minas, Minas Gerais, Brazil") desde 5e91895, que ensinou a guarda a
    # ler estado por extenso. Sem aquele commit, esta cidade entraria com
    # três falsos positivos junto.
    "Fortaleza",
]

# MEDIDO: "Data Analyst @ Lisboa" e "Analista de Datos @ Madrid" reprovavam
# na localização, não no cargo — CIDADES acima é whitelist só de cidade
# brasileira, e a expansão de LOCATIONS_LINKEDIN pra Argentina/Chile (ver
# abaixo) passou a trazer vaga presencial/híbrida em Portugal/Espanha de
# vez em quando junto. Lista SEPARADA (não misturada em CIDADES, que
# continua só-Brasil de propósito — ver decisão registrada na criação do
# config_intl.py) com toggle próprio, pra dar pra ligar/desligar esse eixo
# sem mexer no resto do filtro. Canônica aqui porque config_intl.py já
# importa de config.py (não o contrário) — o pipeline internacional reusa
# essa mesma lista em vez de manter uma cópia (risco de divergir, mesmo
# motivo da unificação de _contem_termo/_tem_termo).
CIDADES_EUROPA_IBERICA = [
    "Portugal",
    "Lisboa",
    "Porto",
    "Braga",
    "Espanha",
    "España",
    "Spain",
    "Madrid",
    "Barcelona",
    "Valencia",
]

# Toggle independente do ATIVAR_EIXO_IBERICO de config_intl.py — são dois
# eixos diferentes (esse aqui é do pipeline BR/main.py, aquele é do
# pipeline internacional/main_intl.py), cada um com seu próprio liga/
# desliga, mesmo compartilhando a mesma lista de cidades acima.
#
# DESLIGADO: do mercado internacional, só interessa vaga remota — vaga
# presencial/híbrida em Lisboa/Madrid (o que esse eixo notifica, marcada
# "exploratória") não é o que o usuário quer. CIDADES_EUROPA_IBERICA
# continua definida (não precisa apagar) pra caso o eixo volte a ser
# ligado depois — só o toggle muda.
ATIVAR_EIXO_IBERICO_BR = False

# LinkedInScraper é a única fonte do pipeline BR que também alcança vaga
# fora do Brasil (as outras são portais brasileiros) — mas até aqui rodava
# só com location=Brasil fixo no código (scrapers/linkedin.py:88), então
# essa "porta pra fora" nunca era usada.
#
# Mercado "casa": busca modalidade completa (presencial/híbrida + remoto),
# porque o usuário mora aqui e vaga local de verdade interessa.
# MEDIDO (2026-08-20): o endpoint de visitante do LinkedIn NÃO resolve
# "Brasil" — e não devolve erro. Ele devolve um resultado genérico dos EUA
# (Evansville-IN, Sandy-UT, Port Angeles-WA...), o MESMO que devolve pra
# qualquer location que ele não entende. Testado ao vivo, mesmo termo:
#     location="Brasil"  ->  10 vagas,  0 no Brasil
#     location="Brazil"  ->  10 vagas,  8 no Brasil
#
# Efeito no histórico: das 910 vagas que o LinkedIn já tinha trazido pro
# perfil BR, 281 eram dos EUA (o filtro descartava depois, mas elas ocupavam
# o orçamento de 20 resultados por termo) e só 19 eram do Brasil — e essas
# 19 vieram das buscas POR CIDADE, que resolvem normalmente. A passada
# nacional nunca trouxe uma vaga brasileira sequer.
#
# Foi assim que "Analista de Business Intelligence Pleno (Remoto)" da Vitru
# (Brasil/Remoto, relevância 7, APROVADA pelo filtro) nunca chegou a ser
# vista: ela é exatamente o caso que a passada nacional deveria cobrir.
LOCATIONS_LINKEDIN = ["Brazil"]

# Mercados adicionais: só busca REMOTA (f_WT=2) — vaga presencial/híbrida
# num país onde o usuário não mora não serve, então nem faz sentido gastar
# a passada nacional ali (era puro desperdício: Argentina/Chile já rodavam
# as duas passadas antes, mas a nacional nunca batia em CIDADES mesmo,
# que é só cidade brasileira). Espanhol ou português — mesmo critério do
# pipeline internacional. Lista reaproveita exatamente os países já usados
# e testados ao vivo no endpoint do LinkedIn em config_intl.py
# (LOCATIONS_INTL) — evita arriscar nome de país nunca testado (grafia
# errada ou região que o LinkedIn não resolve como location de verdade,
# como já visto com "LATAM"/"Latin America").
#
# CORRIGIDO (2026-08-20): esta lista dizia reaproveitar LOCATIONS_INTL, mas
# "México" e "Colômbia" tinham sido traduzidos pro português — e o LinkedIn
# não resolve nenhum dos dois. Medido ao vivo, mesmo termo:
#     "México"   -> 10 vagas,  0 no México  |  "Mexico"   -> 10, 10 no México
#     "Colômbia" ->  0 vagas               |  "Colombia" -> 10, 10 na Colômbia
# E no banco: o perfil internacional (LOCATIONS_INTL, em inglês) tinha 110
# vagas do México e 48 da Colômbia; o perfil BR, zero de cada.
#
# "Espanha" FICA como está: foi medido e resolve (9 de 10 na Espanha, 215
# vagas no histórico). Argentina/Chile/Portugal se escrevem igual nos dois
# idiomas. Ou seja: só muda o que está comprovadamente quebrado.
LOCATIONS_LINKEDIN_REMOTO_APENAS = ["Argentina", "Chile", "Mexico", "Colombia", "Espanha", "Portugal"]

# MEDIDO: a passada nacional acima (location="Brazil") varre o país inteiro
# e só sobra o que bate em CIDADES depois do filtro — pra termo concorrido
# em SP/RJ/MG (a maioria), as 3 páginas (30 resultados) nunca chegam numa
# vaga de cidade menor do Nordeste, porque o volume dos polos maiores
# ocupa tudo antes. Testado ao vivo: página 1 de "analista de dados" em
# Brasil inteiro veio 100% São Paulo/Curitiba/Brasília, nenhuma do
# Nordeste. Busca ESPECÍFICA por cidade não depende de volume nacional —
# o próprio location= do LinkedIn já restringe o resultado à cidade, então
# funciona mesmo quando SP/RJ dominam o termo. "Remoto" (item de CIDADES)
# não é local de busca de verdade — sai da lista, já coberto pela passada
# remoto=True de LOCATIONS_LINKEDIN acima.
LOCATIONS_LINKEDIN_CIDADES_PRESENCIAL = [c for c in CIDADES if c != "Remoto"]

# Mercado que a vaga remota precisa aceitar pra contar, quando o texto de
# local DECLARA um escopo geográfico ("Remote — US only", "Remote — India").
# Ver Job.escopo_remoto/RegrasFiltro.mercados_remoto_aceitos em job.py — sem
# isso, uma vaga remota só pra outro país passava igual a uma remota de
# verdade pro Brasil. Vaga remota SEM escopo declarado no texto (a grande
# maioria) continua batendo normalmente, isso só filtra quando a fonte
# EXPLICITA um mercado incompatível.
#
# MEDIDO: Argentina/Chile/México/Colômbia ENTRAM nominalmente agora — a
# suposição de que "LATAM" cobria os quatro como guarda-chuva só valia
# enquanto extrair_escopo_remoto resolvia o texto pra "LATAM" literal.
# Depois que passou a reconhecer cidade (Buenos Aires/Santiago/Cidade do
# México/Bogotá — ver _CIDADES_MERCADO em job.py), o escopo passou a
# resolver pro PAÍS específico, não mais pro guarda-chuva — e o país
# específico nunca esteve nessa lista. Resultado: LOCATIONS_LINKEDIN_
# REMOTO_APENAS pagava o custo de buscar nesses 4 países e o filtro
# descartava tudo que a busca trazia de lá. "LATAM" continua na lista pra
# quando o texto disser isso literalmente (guarda-chuva de verdade, não
# substituto de nome de país). Portugal e Espanha entraram nominalmente
# pelo mesmo motivo, desde antes.
MERCADOS_REMOTO_ACEITOS = ["Brasil", "LATAM", "Argentina", "Chile", "México", "Colômbia", "Portugal", "Espanha"]

INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 180))

# Digest ranqueado (item 08): vaga com Job.pontuar_relevancia() >= este
# limiar notifica na hora; abaixo disso, fica na fila do digest diário — ver
# _enviar_digest_diario em main.py. Vaga com publicacao_antiga vai pro digest
# mesmo com nota alta, e isso não mudou: score mede "bate com o que você
# procura", não "é recente".
#
# ERA 7 ATÉ 10/09/2026. Baixou pra 4 a pedido da usuária, e o motivo tem
# nome: vaga boa estava se perdendo dentro do digest. O caso que abriu a
# discussão foi "Analista de Dados Pleno (Vaga Afirmativa para PCD)" do Grupo
# OLX, remota, encontrada em 09/09 — nota 6, um ponto abaixo do limiar, então
# foi pro resumo da manhã seguinte em vez de chegar na hora.
#
# MEDIDO (10/09) contra as 542 vagas dos 10 dias anteriores. A simulação
# reproduziu a nota guardada de todas as 542, sem uma divergência, então os
# números abaixo são do comportamento real e não de estimativa:
#
#     limiar   imediatas/dia   ficam no digest/dia
#        7           7,1              47,1          <- como era
#        6          37,0              17,2
#        5          42,0              12,2
#        4          42,2              12,0          <- escolhido
#        3          51,8               2,4
#
# 5 e 4 dão praticamente o mesmo resultado porque quase não há vaga com nota
# 4 (1 em 542). O que separa mesmo é 7 -> 6: são as vagas de nota 6, o maior
# grupo da base, e é onde estava a da OLX.
#
# O QUE ISSO CUSTA, dito claramente: ~42 mensagens individuais por dia, em
# rajadas de ~5 a cada ciclo de 3h. O digest existia justamente pra evitar
# isso. A troca foi feita de olhos abertos, com o número na mão.
#
# ALTERNATIVA MEDIDA E NÃO ESCOLHIDA, registrada porque resolve o mesmo caso
# por outro caminho e continua disponível: o score desconta 1 ponto de vaga
# remota "sem mercado declarado" (_PESO_MERCADO_NAO_CONFIRMADO em job.py).
# No perfil BRASIL esse desconto não faz sentido — remoto no Brasil vale em
# qualquer lugar pela regra de negócio, não há mercado a confirmar. Corrigir
# só isso, mantendo o limiar em 7, levaria de 7,1 para 7,7 mensagens/dia e
# traria 6 vagas em 10 dias: todas "Analista de Dados" Jr/Pleno remotas do
# perfil BR, incluindo exatamente a da OLX. No perfil INTERNACIONAL o
# desconto continua certo, porque lá só valem mercados de língua portuguesa
# e espanhola e a confirmação importa de verdade.
LIMIAR_DIGEST_IMEDIATO = 4

# Hora UTC a partir da qual o digest diário pode sair (uma vez por perfil,
# por dia — ver _enviar_digest_diario em main.py). A regra é "ainda não
# enviei hoje E já passou desta hora", então o digest sai no PRIMEIRO ciclo
# do dia UTC que TERMINAR depois dela — não numa janela exata de 1 hora,
# que era o que impedia o disparo de acontecer (o ciclo dura ~80 min e
# nunca terminava dentro da janela).
#
# 9 UTC: o ciclo que começa às 09:00 UTC termina por volta das 10:20 UTC =
# 07:20 em Brasília (UTC-3). Escolhido pela usuária: chega de manhã, com a
# lista do dia anterior pronta pra revisar, em vez de de madrugada.
#
# Era 0 (= ~22h20 de Brasília), mas esse valor nunca foi uma escolha de
# verdade — ficou assim desde que o recurso foi escrito e nunca chegou a
# funcionar, então nunca houve como perceber que horário dava na prática.
#
# Se o ciclo das 09:00 falhar num dia, o das 12:00 (13:20 UTC) manda — a
# regra é "já passou de 9", não "é exatamente 9", então qualquer ciclo
# seguinte do mesmo dia UTC serve de recuperação.
DIGEST_HORA_UTC = 9

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Caminho ancorado na RAIZ do projeto, não na pasta deste arquivo.
#
# MEDIDO: o commit b8227b0 ("Reorganiza raiz: ... -> core/") moveu este
# config.py da raiz pra core/. Como DB_PATH era relativo a __file__, o
# banco se mudou junto, em silêncio: data/jobs.db virou core/data/jobs.db.
# Efeito real, confirmado em disco e no jobradar.log:
#   - data/jobs.db (1.080 vagas, versionado) ficou órfão;
#   - core/data/jobs.db nasceu vazio, então iniciar_db() passou a abortar
#     por BancoVazioSuspeito em toda execução local;
#   - no GitHub Actions a pasta core/data/ não existe no repositório, então
#     o banco era recriado do zero a cada run — toda vaga virava "nova"
#     (renotificação a cada 3h), o rodízio de termos travava no offset 0
#     (só os 10 primeiros de 44 termos eram buscados), a fila do digest era
#     descartada e o heartbeat saía a cada ciclo em vez de 1x/dia;
#   - o passo "git add data/jobs.db" do workflow não via mudança nenhuma
#     ("Nada novo pra commitar"), então o estado nunca mais persistiu.
#
# _RAIZ_PROJETO sobe um nível a partir de core/, então o caminho deixa de
# depender de onde este arquivo mora — mover config.py de novo não move
# mais o banco junto. Coberto por tests/test_db_path.py, pra uma
# reorganização futura quebrar o teste em vez da produção.
#
# JOBRADAR_DB_PATH existe pra apontar um banco descartável em teste/
# experimento sem risco de escrever no banco real.
_RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("JOBRADAR_DB_PATH") or os.path.join(_RAIZ_PROJETO, "data", "jobs.db")