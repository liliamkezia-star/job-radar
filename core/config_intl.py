
# Config do programa internacional (busca vaga remota fora do Brasil que
# aceita/pede português ou espanhol). Separado do config.py de propósito —
# ver decisão registrada na conversa: misturar ia forçar o filtro de cidade
# do Nordeste e as keywords em português do JobRadar original a servir dois
# propósitos diferentes ao mesmo tempo, deixando os dois mais frágeis.
#
# Credenciais do Telegram e caminho do banco são os MESMOS do projeto
# principal (reaproveita o bot já configurado, e o dedup por link no mesmo
# jobs.db não tem risco de colisão — o id é hash do link, e vaga
# internacional nunca vai ter o mesmo link de uma vaga brasileira).
from core.config import (  # noqa: F401
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DB_PATH,
    CIDADES_EUROPA_IBERICA,
    QUALIFICADORES_DADOS,
)

# Cargo ambíguo neste perfil: "Analyst" sozinho é usado em finanças, RH,
# compras, risco — qualquer área. Só conta como match quando o título TAMBÉM
# traz um qualificador de dados, exatamente como no perfil BR.
#
# MEDIDO (2026-08-29) contra 175 vagas reais do LinkedIn Intl (8 termos, 3
# mercados, 85 já aprovadas). Foram testados DOIS caminhos na mesma amostra:
#
#   A) hoje                                         85 aprovadas
#   B) + as keywords fortes em inglês que o BR tem  85   (+0)
#   C) + cargo ambíguo "Analyst"                    92   (+7)
#
# O caminho B era a hipótese preferida — a de que o buraco fosse só as duas
# listas de keywords terem divergido, e não falta de mecanismo. Ela foi
# DERRUBADA pela medição: alinhar as listas não ganhou uma vaga sequer.
#
# As 7 que só o mecanismo pega, todas remotas de mercado aceito:
#     Data & Analytics Analyst                            Lisboa
#     Data & Analytics Analyst - Lisbon                   Lisboa
#     Business & Data Integration Analyst - HR Analytics  Lisboa
#     Senior Data Research Analyst (Portuguese speaker)   Madri
#     Multilingual Data Research Analyst                  Madri
#     Analytics Analyst - Remote Work                     Jalisco
#     Data Services Analyst                               México
#
# As três primeiras vinham aparecendo no log, ciclo após ciclo, como
# "barradas só pelo título". Zero ruído nas 175 da amostra.
#
# RISCO ACEITO, o mesmo do perfil BR: "Data Center Operations Analyst" e
# "Data Entry Analyst" passam, porque casam o qualificador "data" sem serem
# análise de dados. Não apareceram na amostra. Está travado em teste.
#
# LIMITE DA MEDIÇÃO, registrado por honestidade: os 8 termos usados eram os
# mais específicos da lista ("data analyst spanish speaker" e variantes). Os
# termos largos do perfil ("spanish speaker" sozinho) NÃO foram testados. A
# proteção do qualificador é sobre o TÍTULO e independe do termo que achou a
# vaga, então não deve mudar — mas isso é raciocínio, não medição.
KEYWORDS_CARGO_AMBIGUO_INTL = ["Analyst"]

# NÃO entraram, e por quê (medido na mesma amostra):
#   "Especialista" -> 0 vagas a mais. Mesmo resultado do teste no perfil BR.
#   "Analista"     -> 0 vagas a mais aqui (no BR trazia DBA, e a usuária
#                     decidiu deixar de fora).
# Sem número, seria palpite.
#
# QUALIFICADORES_DADOS vem do config.py em vez de uma lista própria: é a
# mesma lista que o perfil BR usa e que a medição acima empregou. Uma adição
# óbvia seria "datos" (espanhol), que falta ali — mas ela NÃO foi medida,
# então fica como proposta, não como mudança.

# Cargo em múltiplos idiomas — vaga internacional pode ter o anúncio escrito
# em inglês, português ou espanhol, dependendo de quem contratou.
KEYWORDS_INTL = [
    "Data Analyst",
    "Business Intelligence",
    "BI Analyst",
    "Data Analytics",
    "Data Specialist",
    "Analista de Dados",
    "Business Analyst",
    # Nomenclatura em espanhol
    "Analista de Datos",
    "Analítica de Datos",
    "Analista de Inteligencia de Negocios",
    "Especialista en Datos",
    "Analista de Business Intelligence",
    "Analista de Reportes",
    # Eixo separado: Data Annotation / AI Evaluator — não é análise de
    # dados, é rotular/avaliar dado pra treinar IA, mas é um nicho remoto
    # que contrata muito por idioma (PT-BR/ES) e paga em dólar, então entra
    # como categoria própria de cargo, não mistura com as de análise.
    "Data Annotator",
    "Data Annotation",
    "AI Evaluator",
    "AI Trainer",
    "Data Labeler",
    "Search Quality Rater",
    # Engenharia de dados, pedida pela usuária em 03/10/2026. Espelha o
    # que entrou em KEYWORDS_CARGO_FORTE (core/config.py) — deixar os dois
    # perfis diferentes aqui recriaria exatamente a divergência silenciosa
    # que fez o perfil internacional ficar sem mecanismo por semanas.
    #
    # Entra como FILTRO. O termo de BUSCA internacional é outra lista e tem
    # regra própria (ver TERMOS_BUSCA_INTL abaixo: cargo sozinho aqui é o
    # mundo inteiro sem filtro de idioma), então não é simétrico ao perfil
    # BR, onde TERMOS_CARGO é derivado de KEYWORDS automaticamente.
    #
    # Sem esta entrada, a vaga "Data Engineer" que o itjobs.pt e o
    # LinkedIn Intl encontram seria reprovada SÓ PELO CARGO — medido em
    # 03/10 nos dois perfis, antes de mexer.
    "Engenheiro de Dados",
    "Data Engineer",
    "Analytics Engineer",
]

# Termos de busca: cargo + sinal de idioma (português/espanhol/bilíngue) ou
# +sinal de mercado (LATAM, Spanish Market). Não faz sentido buscar só
# "data analyst" sozinho aqui — isso é o mundo inteiro sem filtro nenhum de
# idioma, a maioria fora do nosso alcance.
TERMOS_BUSCA_INTL = [
    "data analyst spanish speaker",
    "data analyst spanish speaking",
    "data analyst portuguese speaker",
    "data analyst portuguese speaking",
    "bilingual data analyst spanish",
    "bilingual data analyst portuguese",
    "business intelligence spanish speaker",
    "business intelligence spanish speaking",
    "business intelligence portuguese speaker",
    "business intelligence portuguese speaking",
    "remote data analyst latam",
    # Engenharia de dados, 03/10/2026. Com sinal de idioma/mercado porque a
    # regra desta lista está escrita acima: cargo sozinho aqui é "o mundo
    # inteiro sem filtro nenhum de idioma". "data engineer" puro traria
    # vaga global que o filtro de mercado reprova depois — custo de
    # requisição com ganho zero, que é o erro que esta lista evita por
    # desenho.
    "data engineer portuguese speaker",
    "data engineer spanish speaker",
    "remote data engineer latam",
    "remote data analyst latin america",
    "data analyst spanish market",
    "business intelligence spanish markets",
    "analista de datos remoto",
    # MEDIDO ao vivo: vaga real ("Business Analyst (Colombia) - Remote",
    # Connect Tech+Talent) aparece em location=Colombia&f_WT=2 pro termo
    # bare "business analyst" — testei "spanish speaker", "business
    # intelligence spanish speaker", "remote data analyst latin america" e
    # "latam" contra a mesma vaga, location e filtro remoto: nenhum achou
    # (o anúncio não repete nenhuma dessas frases). O comentário original
    # lá em cima ("não faz sentido buscar só 'data analyst' sozinho, é o
    # mundo inteiro sem idioma") não vale AQUI: todo termo desta lista já
    # roda escopado por país (LOCATIONS_INTL) + remoto (f_WT=2) — nunca é
    # busca global. E o filtro de idioma pós-busca (RegrasFiltro.
    # idiomas_exigidos) só entra em jogo quando a vaga NÃO declara mercado
    # nenhum no texto — quando o local já é um país aceito (ex: Colômbia),
    # o PAÍS é o sinal, dispensa achar "spanish"/"portuguese" no título
    # (mesma regra que já vale pro resto do filtro, ver job.py). Termo de
    # cargo puro, escopado por país aceito, é seguro e fecha o vazamento:
    # KEYWORDS_INTL aprova "Business Analyst"/"Data Analyst"/"Business
    # Intelligence" como cargo forte, mas nenhum dos dois primeiros nunca
    # era BUSCADO sozinho — só entravam por acidente, dentro de uma frase
    # combinada.
    "business analyst",
    "data analyst",
    "business intelligence",
    # Eixo Data Annotation / AI Evaluator
    "data annotation spanish speaker",
    "data annotation portuguese speaker",
    "ai evaluator spanish",
    "ai evaluator portuguese",
    "ai trainer portuguese speaker",
    "ai trainer spanish speaker",
    "remote data annotator latam",
    # Termos "soltos" (idioma/mercado sem cargo emparelhado na própria
    # busca) — diferente dos de cima, que sempre combinam cargo+idioma numa
    # frase só. MEDIDO: zero ocorrência de "Spanish"/"Español"/"LATAM" como
    # termo próprio no projeto — toda vaga que anuncia a vaga com o idioma
    # em destaque ("Spanish Speaker — Data Analytics Role", "LATAM Remote
    # Team") e não bate exatamente numa das frases combinadas acima ficava
    # invisível pra busca. Não é o mesmo risco do comentário lá em cima
    # (buscar só "data analyst" sozinho, sem NENHUM filtro de idioma) — aqui
    # é o oposto, idioma sem cargo na busca, e o cargo continua sendo
    # exigido depois por KEYWORDS_INTL antes de qualquer notificação.
    "spanish speaker",
    "spanish speaking",
    "portuguese and spanish",
    "spanish market",
    "latam",
]

# MEDIDO: filtro de cargo (KEYWORDS_INTL) nunca checou idioma — a exigência
# de espanhol/português vivia só nos TERMOS de busca acima, que casam
# contra o anúncio inteiro (LinkedIn/Indeed indexam a descrição toda, não
# só o título) e nunca são reconferidos depois. Resultado: "Senior Data
# Analyst"/"Data Analyst" remoto e sem mercado declarado passava sem
# nenhuma palavra em comum com espanhol/português/LATAM no que a gente
# guarda (título/empresa/local). Usado em Job.combina_com() só quando a
# vaga é remota SEM mercado aceito declarado (ver RegrasFiltro.idiomas_
# exigidos e comentário lá) — quando o escopo já é um país hispanofalante/
# lusófono aceito, o país é o sinal, essa lista nem entra em jogo.
#
# Mesmo vocabulário dos termos soltos acima (spanish/portuguese/latam),
# mais a grafia em espanhol/português — busca casa com anúncio em inglês
# na maioria das vezes, mas o TÍTULO que sobra pode vir em qualquer um dos
# três idiomas.
IDIOMAS_EXIGIDOS_INTL = [
    "spanish",
    "espanol",
    "español",
    "portuguese",
    "português",
    "portugues",
    "latam",
    "latin america",
    "america latina",
    "hispanohablante",
    "lusofono",
    "lusófono",
]

# Rodízio de termos, mesmo mecanismo do TERMOS_POR_CICLO em config.py (ver
# _proximo_bloco_termos em main.py) — só que com chave de metadados própria
# (sufixo "_internacional"), pra não colidir com o rodízio do perfil BR.
# Esse perfil nunca tinha rodízio antes de virar perfil de verdade (rodava a
# lista de termos INTEIRA todo ciclo, sem custo controlado, e nem chegava a
# rodar de fato — não estava no workflow do GitHub Actions). 27 termos x até
# 6 países/domínios por fonte já é bastante busca; bloco de 10 mantém o
# custo por ciclo parecido com o do perfil BR.
TERMOS_POR_CICLO_INTL = 10

# Mercados pesquisados por rodada de busca no LinkedIn (parâmetro location
# do endpoint). Lista enxuta de propósito — cada país aqui multiplica o
# número de buscas (termos x países), então começa pequeno e dá pra
# expandir depois que confirmar que vale o tempo de execução.
#
# "United States" e "United Kingdom" foram REMOVIDOS de propósito: mesmo com
# os termos de busca pedindo "spanish/portuguese speaker", o location filtra
# geografia, não idioma — a maioria das vagas retornadas pra EUA/Reino Unido
# é vaga comum do mercado local, que pede inglês fluente (causa raiz do
# problema relatado). O escopo agora é só América Latina + países ibéricos
# que falam espanhol/português, que é o que esse pipeline sempre quis cobrir.
#
# "Latin America"/"LATAM"/"EMEA"/"Iberia" NÃO entraram aqui — testei ao
# vivo no endpoint do LinkedIn e nenhum desses nomes de região resolve como
# location de verdade (retorna resultado genérico, sem filtrar nada, ou
# vazio). O endpoint só reconhece país/cidade específico. Por isso os
# países de LATAM entraram nominalmente, e "latam"/"latin america" como
# texto dentro do termo de busca (acima) em vez de location. "Iberia" não
# precisa de entrada própria — já é coberto por Spain + Portugal abaixo.
LOCATIONS_INTL = [
    "Spain",
    "Portugal",
    "Mexico",
    "Colombia",
    "Argentina",
    "Chile",
]

# Sem cidade nenhuma — só remoto, de qualquer país. "Remote" cobre o termo
# em inglês (a maioria dos cards vai estar em inglês), "Remoto" cobre os
# poucos que vierem em português/espanhol.
#
# PROBLEMA que isso sozinho causava: CIDADES_INTL é uma whitelist — só
# aceita "Remote"/"Remoto" no local. Isso rejeita vaga presencial/híbrida
# em Lisboa ou Madrid mesmo quando ela é achada de propósito (via
# LOCATIONS_INTL = Portugal/Spain), porque o local não escreve "Remote"
# literalmente. Não é uma regra "excluir Portugal" — é a lógica de
# whitelist só admitir o que está na lista, o que dá no mesmo na prática.
#
CIDADES_INTL = ["Remote", "Remoto"]

# Ver MERCADOS_REMOTO_ACEITOS em config.py e Job.escopo_remoto/
# extrair_escopo_remoto em job.py. Duas listas com propósito DIFERENTE,
# mesma lógica de TERMOS_BUSCA/TERMOS_POR_CICLO vs KEYWORDS: LOCATIONS_INTL
# é ONDE BUSCAR (custo real — cada país multiplica busca × termo, então fica
# enxuto nos mercados que mais contratam); esta lista aqui é O QUE ACEITAR
# (custo zero — só comparação de string), então cobre TODO país
# hispanofalante/lusófono, não só os 6 de LOCATIONS_INTL. Precisa ser
# abrangente porque desde que _mercado_correspondente() virou allowlist
# estrita (ver job.py) — escopo declarado que não bate aqui é REJEITADO,
# mesmo vindo de um país que o projeto quer aceitar, então faltar um país
# aqui vira falso negativo (barra vaga boa), não falso positivo.
#
# NÃO inclui "Brasil" porque esse pipeline é justamente o de vaga remota
# FORA do Brasil (main.py/PERFIL_BR já cobre o Brasil). Vaga "Remote — US
# only"/"Remote — India"/"Remote — Vietnam" segue sendo rejeitada, agora
# inclusive quando o país não está no dicionário de job.py (ver
# MEDIDO em _mercado_correspondente).
MERCADOS_REMOTO_ACEITOS_INTL = [
    "Portugal",
    "Espanha",
    "México",
    "Colômbia",
    "Argentina",
    "Chile",
    "Peru",
    "Uruguai",
    "Paraguai",
    "Bolívia",
    "Equador",
    "Venezuela",
    "Costa Rica",
    "Panamá",
    "Guatemala",
    "Honduras",
    "El Salvador",
    "Nicarágua",
    "República Dominicana",
    "Porto Rico",
    "Cuba",
    "Angola",
    "Moçambique",
    "Cabo Verde",
    "LATAM",
]

# Eixo separado pra isso, controlado por ATIVAR_EIXO_IBERICO — dá pra
# desligar sem mexer no resto do pipeline internacional (nem em
# CIDADES_INTL). Quando ativo, vaga presencial/híbrida em Portugal/Espanha
# passa também, mas marcada como "exploratória" na notificação (ver
# main_intl.py), pra distinguir de vaga remota de verdade.
# CIDADES_EUROPA_IBERICA (a lista de cidades) mudou pra config.py — o
# pipeline BR (main.py) passou a ter o mesmo eixo (ver ATIVAR_EIXO_IBERICO_BR
# lá), e as duas listas eram idênticas, então centralizei numa só pra não
# correr risco de uma mudar e a outra ficar pra trás. Esse toggle aqui
# continua LOCAL e independente do ATIVAR_EIXO_IBERICO_BR — são eixos de
# pipelines diferentes, cada um liga/desliga por conta própria.
#
# DESLIGADO: do mercado internacional, só interessa vaga remota — vaga
# presencial/híbrida em Lisboa/Madrid não é o que o usuário quer, mesmo
# achada de propósito via LOCATIONS_INTL. Continua fácil de religar depois
# (só o toggle), sem apagar nada da lista/lógica.
ATIVAR_EIXO_IBERICO = False

# Indeed usa subdomínio por país, não parâmetro de location como o
# LinkedIn. Confirmei ao vivo que es.indeed.com, pt.indeed.com e
# mx.indeed.com funcionam e trazem vaga local de verdade (ex: "Analista de
# Dados" em Lisboa, "Data Analyst" em Barcelona). co/ar/cl seguem o mesmo
# padrão de domínio mas não testei individualmente — se algum não resolver
# como esperado, o scraper só loga 0 vagas pra aquele país, não quebra o
# resto.
#
# "Estados Unidos" (www.indeed.com) e "Reino Unido" (uk.indeed.com) foram
# REMOVIDOS pelo mesmo motivo do LOCATIONS_INTL: domínio de país não filtra
# idioma, e a maioria das vagas desses dois mercados pede inglês fluente —
# era a fonte real das notificações de vaga em inglês.
#
# Mesmo aviso do Indeed BR original: tem proteção anti-bot que pode
# bloquear acesso automatizado (principalmente de IP de nuvem/datacenter),
# mesmo funcionando em teste manual.
DOMINIOS_INDEED_INTL = {
    "Espanha": "es.indeed.com",
    "Portugal": "pt.indeed.com",
    "México": "mx.indeed.com",
    "Colômbia": "co.indeed.com",
    "Argentina": "ar.indeed.com",
    "Chile": "cl.indeed.com",
}
