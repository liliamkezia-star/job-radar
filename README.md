<div align="center">

# 📡 JobRadar
### Monitor Automatizado de Vagas de Dados & BI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Scraping-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Dedup%20%26%20estado-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/testes-652%20passing-success?style=for-the-badge)
![Status](https://img.shields.io/badge/status-em%20produção-success?style=for-the-badge)

**Autora:** Liliam Kezia Oliveira Souza

</div>

---

## 💎 Proposta de valor

> Em cidade pequena, vaga boa de Dados/BI aparece pouco e some rápido — quem checa o board duas vezes por dia perde para quem checou na primeira hora. **JobRadar** substitui essa checagem manual: varre **9 fontes** (as principais a cada **3 horas**, as secundárias uma vez por dia), filtra por cargo, cidade, mercado e idioma em três níveis de confiança, pontua cada vaga por relevância e notifica no Telegram — de graça, sem servidor próprio, 24 horas por dia.

A escassez que justifica o projeto está medida no próprio banco: das **3.624 vagas** já processadas, **108 (3,0%)** ficam numa das nove cidades-alvo. O resto é remoto ou está fora da regra. Procurar isso à mão significa varrer 33 vagas para achar uma.

## 📄 Resumo executivo

Entre 07 de agosto e 03 de outubro de 2026 — 58 dias — o sistema processou **3.624 vagas únicas** sem intervenção manual.

| Indicador | Número |
|---|---|
| 📊 Vagas processadas (deduplicadas) | **3.624** |
| 🧪 Testes automatizados (CI a cada push) | **652** |
| 🌎 Fontes ativas | **9** |
| 🏙️ Cidades-alvo + remoto | **9 + remoto** |
| ⏱️ Frequência de checagem | **a cada 3h** |
| ⏳ Duração de um ciclo completo | **~26 min** (os dois perfis) |
| 🔗 Concentração em LinkedIn (BR + Intl) | **93,8%** ⚠️ |
| 💰 Custo de infraestrutura | **R$ 0** |

Sobre o número de concentração, porque ele já foi lido errado aqui dentro: **93,8%** é a soma dos dois scrapers de LinkedIn (Brasil, 76,4%, e Internacional, 17,4%). São módulos diferentes, mas o mesmo endpoint não oficial e o mesmo ponto único de falha — então o número que importa para risco é o de 93,8%. Confundir os dois já produziu um "ganho" de 93,8% para 75% que nunca existiu: eram métricas diferentes comparadas entre si.

A concentração está documentada como **risco**, não como conquista. Ver [Limites conhecidos](#-limites-conhecidos).

---

## 🔬 Como as decisões são tomadas

Esta é a parte do projeto que mais me interessa como analista: **nenhuma mudança de comportamento entra sem medição antes.** Não porque seja elegante, mas porque a alternativa falhou de forma cara — e a maior parte dos defeitos encontrados aqui era invisível no log.

O padrão que se repetiu: o robô parecia saudável, o GitHub Actions ficava verde, vagas chegavam normalmente — e mesmo assim faltava vaga. Cada caso só apareceu quando alguém desconfiou de um **número**, não de uma mensagem de erro.

**Dois exemplos, com o antes e depois medidos:**

O LinkedIn não reconhece `location=Brasil`. Ele não devolve erro — devolve um resultado genérico dos Estados Unidos, indistinguível de uma busca bem-sucedida. A busca nacional brasileira nunca funcionou, e ninguém tinha como notar.

| LinkedIn (perfil Brasil) | Vagas | Do Brasil | Dos EUA |
|---|---|---|---|
| Antes (`location=Brasil`) | 910 | **19 (2,1%)** | 268 |
| Depois (`location=Brazil`) | 813 | **354 (43,5%)** | **0** |

O card do LinkedIn traz a data de publicação em inglês (`"4 months ago"`), mas a extração procurava padrões em português. O campo vinha vazio, então vaga de quatro meses era notificada como se fosse nova.

| Data de publicação preenchida | Antes | Depois |
|---|---|---|
| Vagas do LinkedIn com data (medido nas 504 seguintes à correção) | 231/1.639 (14,1%) | **504/504 (100%)** |

**Quatro hipóteses minhas foram derrubadas pelos próprios dados** — e é isso que a medição serve para fazer:

- *"Esses avisos de vaga perdida são alarme falso"* — eram, em três fontes. Na quarta, não: as buscas devolviam 10 resultados quando rodadas isoladas. O aviso estava certo e vaga estava sendo perdida.
- *"O perfil internacional só precisa das keywords que o Brasil já tem"* — alinhar as listas ganhou **zero** vaga. O que ganhou 7 foi um mecanismo que aquele perfil não tinha.
- *"Cidade pequena com ferramenta de nicho não tem vaga mesmo"* — tinha 10.
- *"O endpoint do LinkedIn devolve vazio porque bloqueia IP de datacenter"* — o ciclo rodado em rede residencial deu **22** buscas vazias contra **13** do GitHub Actions. A hipótese explicava o sintoma e estava errada; a comparação original punha 7 requisições isoladas contra 7 que eram a enésima de uma fila de ~500.

Quando a medição não é possível, isso fica escrito no código em vez de escondido. A correção de rate-limit do LinkedIn, por exemplo, só se manifesta no IP de datacenter do GitHub Actions e não reproduz localmente — então foi desenhada para ser **segura por construção**: ajuda se o diagnóstico estiver certo, e não piora nada se estiver errado.

---

## 🧯 O que quebrou — e como se descobriu

Em 58 dias de produção, **três fontes pararam de funcionar sem emitir um único erro**. Nenhuma das três foi descoberta por alerta; todas por alguém olhando um número que não fechava. Esta seção existe porque o padrão é mais interessante que os bugs.

| Fonte | O que aconteceu | Como aparecia no log | Antes → depois |
|---|---|---|---|
| **Sólides** | A API respondeu `count = 0` para termos que tinham centenas de vagas, e depois morreu de vez (404 na rota). Reconstruída sobre o portal novo, que embute os dados no HTML (RSC do Next em pedaços). | `0 resultados reais` — idêntico a uma busca legitimamente vazia | de ~400 para **70 vagas** num ciclo, sem alerta |
| **Gupy** | A API do portal saiu do ar: 404 em todo termo, 404 sem parâmetro, 404 na raiz. Reconstruída sobre o `__NEXT_DATA__` da página de busca. | a fonte simplesmente não aparecia no funil | **0 vagas brutas em 3 ciclos** → 299, 316 e 550 |
| **GeekHunter** | O layout do card mudou: o link passou a envolver só o título, e cidade e modalidade foram para o `<div>` bisavô. Sem cidade, toda vaga morria no filtro de localização. | funil com brutas e zero aprovadas | **71 brutas → 0 aprovadas** → 76 brutas → **8 aprovadas** |

O que a reconstrução da Gupy entregou no primeiro dia, e é o que o projeto menos acha:

| Vaga | Local | Modalidade | Nota |
|---|---|---|---|
| Analista de Dados Júnior — Casa dos Ventos | Fortaleza, CE | Presencial | 7 |
| Analista de BI Pleno — Join \| Creative Tech | Recife, PE | Híbrido | 7 |
| Analista de Dados CRM — Consultoria RH Recife | Recife, PE | Presencial | 6 |
| ANALISTA DE DADOS | Fortaleza, CE | Presencial | 6 |

Quatro vagas presenciais/híbridas nas cidades-alvo em um dia — a categoria mais rara do projeto. A GeekHunter, no mesmo dia, entregou a primeira vaga em quase dois meses.

**A lição virou código.** Os três casos têm a mesma causa raiz: *falha silenciosa é pior que falha ruidosa*. O que entrou por causa disso:

- **Alerta por fonte**: três ciclos seguidos sem uma vaga bruta e a fonte é tratada como morta, com aviso no Telegram — uma vez por queda, não por ciclo. O alerta que já existia exigia maioria das fontes com problema, e fonte morrendo sozinha passava invisível.
- **O scraper grita quando o formato muda**: a Gupy registra `ERROR` se o `__NEXT_DATA__` sair do lugar; a Sólides, se a lista de vagas mudar de forma; a GeekHunter, se não achar o container do card. Nenhum dos três volta "0 resultados" quando o problema é de formato.
- **404 deixou de ser confundido com timeout**: na GeekHunter, termo com uma página só respondia 404 na página 2, caía no mesmo caminho do timeout e gerava "pode ter ficado vaga de fora" em todo termo pequeno. Aviso que grita errado toda vez deixa de ser lido — e aí o dia em que ele estiver certo passa batido também.

---

## 📸 Como chega para você

Vaga de alta relevância chega na hora, com nível, data de publicação e link. O resto entra num resumo diário ranqueado — sem virar spam. Vaga com mais de 30 dias ganha aviso de "pode já estar preenchida" e sai do alerta imediato, mas nunca é descartada.

O limiar entre "chega na hora" e "espera o resumo" foi calibrado com medição, não por gosto: nota ≥ 7 dava 7,1 notificações por dia, nota ≥ 4 dá 42,2. O valor em uso é **4**, escolhido depois de ver as duas pontas da tabela.

---

## 🗂️ Sumário

- [Como as decisões são tomadas](#-como-as-decisões-são-tomadas)
- [O que quebrou — e como se descobriu](#-o-que-quebrou--e-como-se-descobriu)
- [Como funciona (pipeline)](#-como-funciona-pipeline)
- [Arquitetura técnica](#%EF%B8%8F-arquitetura-técnica)
- [Regras de negócio](#-regras-de-negócio)
- [Estrutura do repositório](#-estrutura-do-repositório)
- [Como rodar](#-como-rodar)
- [Testes](#-testes)
- [Limites conhecidos](#-limites-conhecidos)

---

## 🧭 Como funciona (pipeline)

| Etapa | O que faz |
|---|---|
| **Busca** | Varre as fontes em paralelo, com rodízio de termos (10 por ciclo + 5 prioritários, de 45 cadastrados) para controlar custo por ciclo |
| **Filtra** | Cargo (forte / ambíguo + qualificador / ferramenta + cargo), cidade ou mercado remoto, idioma |
| **Pontua** | Score 1–10 por vaga: cargo, ferramenta, senioridade, mercado, idioma — soma de sinais, sem IA |
| **Deduplica** | Por link e por empresa+título, para pegar a mesma vaga republicada em fonte diferente |
| **Notifica** | Nota ≥ 4 na hora; o resto num resumo diário ranqueado, melhor vaga no topo |
| **Vigia** | Funil por fonte em todo ciclo (brutas → filtradas → novas) e alerta quando uma fonte seca |
| **Aprende** | Botão 👍/👎 em cada notificação — feedback vira dado para medir precisão por fonte e por semana |

## 🏗️ Arquitetura técnica

- **Filtro em 3 níveis de confiança:** cargo inequívoco passa sozinho; cargo ambíguo (ex: `Analyst`) só conta com um qualificador de dados junto no título; ferramenta (ex: `Power BI`) só conta com palavra de cargo junto. Nada aprova por palavra solta — é o que segura `Financial Analyst` e `HR Analyst` fora do radar.
- **Score de relevância sem ML:** 5 sinais conhecidos, pesos calibrados contra o histórico real do banco. Conjunto pequeno e conhecido não precisa de modelo — precisa de critério explicável.
- **Dois perfis, uma máquina:** Brasil e Internacional são **dado** (`core/perfis.py`), não código duplicado. Cada um tem suas regras, suas fontes e sua frequência; o motor é o mesmo.
- **Zero infraestrutura:** GitHub Actions como motor de cron e SQLite como estado. O banco de vagas já vistas sobrevive entre ciclos — hoje versionado no próprio Git, em migração para cache + artifact (ver Limites conhecidos).
- **Scraping sem navegador onde dá:** Gupy, Sólides e Senior leem JSON ou HTML direto com `requests` — sem Playwright, sem seletor para quebrar. A Gupy lê o `__NEXT_DATA__` da página; a Sólides remonta o payload RSC do Next. Navegador só onde a página exige.
- **Resiliente:** nunca marca vaga como vista sem confirmar que a notificação saiu; alerta se a maioria das fontes falhar num ciclo **e** se uma fonte secar sozinha; heartbeat diário confirmando que o robô está de pé; aborta antes de buscar se o banco voltar vazio, para não notificar o histórico inteiro como se fosse novo; e uma segunda passada no fim do ciclo — no LinkedIn e na Sólides — que repete só as buscas que voltaram vazias. Ela se mede sozinha no log e carrega no código o critério que a mata, escrito antes do primeiro resultado (ver Limites conhecidos).
- **652 testes em CI:** cada caso documenta um bug real já corrigido nesta base — inclusive os que ainda não foram corrigidos, fixados como comportamento conhecido em vez de escondidos.

## 📋 Regras de negócio

O filtro existe para uma busca específica, e as regras estão explícitas em `core/config.py`:

- **Brasil remoto:** aceito de qualquer lugar do país.
- **Brasil presencial ou híbrido:** só em Campina Grande-PB, João Pessoa-PB, Recife-PE, Natal-RN, Caruaru-PE, Manaus-AM, Maceió-AL, Aracaju-SE e Fortaleza-CE.
- **Internacional:** **só remoto**, e só em mercados de língua portuguesa ou espanhola. Presencial e híbrido fora do Brasil são rejeitados; `Remote — US only` é rejeitado.

Cidade homônima é tratada: `Campina Grande do Sul, Paraná` e `Fortaleza de Minas, Minas Gerais` são barradas pela conferência de UF, que entende tanto a sigla (`PR`) quanto o estado por extenso (`Paraná`) — e tanto o formato com vírgula (`Recife, PE, Brasil`) quanto com hífen (`Santa Cruz do Sul - RS, Brasil`), porque as fontes usam os dois.

## 📁 Estrutura do repositório

```
JobRadar/
├── main.py                      ← motor único: um ciclo de busca por perfil
├── relatorio_precisao.py        ← aprovadas/notificadas por fonte e por semana
├── core/
│   ├── perfis.py                ← Brasil vs Internacional (dado, não lógica duplicada)
│   ├── config.py                ← cargos, cidades, termos, pesos (perfil Brasil)
│   ├── config_intl.py           ← o mesmo para o perfil internacional
│   ├── job.py                   ← Job, filtro, score de relevância
│   └── logger.py
├── database/
│   └── database.py              ← SQLite: dedup, fila do digest, metadados
├── notifier/
│   └── telegram.py              ← notificação individual, digest, botão 👍/👎
├── scrapers/                    ← um módulo por fonte (12 módulos, 9 ativos)
├── tests/                       ← 652 casos em 23 arquivos, roda em CI a cada push
├── data/
│   └── jobs.db                  ← estado: dedup, rodízio de termos, fila do digest
└── .github/workflows/
    ├── jobradar.yml             ← cron de produção (a cada 3h)
    └── testes.yml               ← CI
```

## 💻 Como rodar

```bash
git clone <repo>
cd JobRadar
python -m venv venv && venv\Scripts\activate   # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Criar `.env` na raiz com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (via [@BotFather](https://t.me/BotFather)), depois:

```bash
python main.py --perfil brasil internacional --once   # um ciclo e encerra
python main.py --perfil brasil                        # contínuo, a cada 3h
```

Para testar sem tocar no banco de produção:

```bash
JOBRADAR_DB_PATH=data/teste.db python main.py --perfil brasil --once
```

## 🧪 Testes

```bash
pytest tests/ -v
```

652 casos em 23 arquivos, cobrindo filtro, regras de negócio, paginação de cada fonte, datas de publicação, as guardas de estado e o relatório de precisão — todos rodando a cada push via GitHub Actions.

Os testes seguem duas convenções:

**Cada arquivo começa explicando o bug real que o motivou**, com o número medido. Um teste que só afirma que `2 + 2 = 4` não conta; o que conta é o que quebrou de verdade e como se descobriu.

**O dado de teste é capturado da fonte, não inventado.** Essa regra nasceu de um prejuízo: o link das vagas da Sólides ficou quebrado **24 dias** sem ninguém notar, porque a fixture do teste tinha uma URL completa, escrita à mão, enquanto o site mandava a URL incompleta. O teste verificava a imaginação de quem o escreveu. Hoje os testes de card e de link usam o texto real capturado da página, e cada suíte nova é verificada por mutação — altera-se o código de propósito para confirmar que algum teste quebra.

## ⚠️ Limites conhecidos

Registrados de propósito — problema documentado é problema que alguém pode consertar.

| Limite | Situação |
|---|---|
| **93,8% das vagas vêm do LinkedIn** | Endpoint não oficial (76,4% do scraper Brasil + 17,4% do Internacional). Se mudar ou bloquear, o sistema perde quase todo o alcance. É o maior risco estrutural do projeto e não tem mitigação hoje. |
| **Resposta instável do LinkedIn** | O endpoint guest às vezes serve a página e às vezes devolve vazio para a *mesma* busca. Medido em três rodadas: o mesmo par (termo × cidade) devolve 0 e 10 em horas diferentes, do mesmo IP. A hipótese de bloqueio ao IP de datacenter foi **derrubada** (22 buscas vazias em rede residencial contra 13 no Actions). Repetir na hora (5s/10s/30s) recuperou 0 de 13; o rodízio de termos recupera 12 de 22 sozinho. Mitigação atual: repetir no fim do ciclo. **Medida em produção, 4 ciclos:** recuperou 43, 25, 94 e 27 vagas inéditas. Custo: ~25 requisições extras em ~375, cerca de 2 minutos. Nos ciclos de 03/10 as buscas vazias caíram a **zero** — mudança não explicada, sob observação. |
| **O banco de estado ainda é versionado no Git** | `data/jobs.db` está no repositório, e isso cobra duas contas: rodada local perde registro (`git checkout` devolve o banco ao estado commitado, e vaga já avisada volta a ser inédita — aconteceu, 13 registros perdidos) e o histórico de busca fica num repositório público. **Migração em duas etapas:** a primeira semeia e mede um cache do GitHub Actions sem trocar nada; a segunda tira o banco do Git. Em duas etapas porque a guarda contra notificar em massa só pegava banco *vazio*, não banco *ausente* — tirar o banco do Git sem isso faria as 3.624 vagas chegarem de uma vez. A guarda nova já existe, desligada, atrás de `JOBRADAR_EXIGIR_BANCO_EXISTENTE`. |
| **Indeed fora dos perfis** | Bloqueio anti-bot completo no IP do GitHub Actions: timeout na página 1 de todo termo, nos 6 domínios de país, em 3 ciclos. Na máquina doméstica a mesma busca devolveu 911 vagas — é o antes-e-depois de IP mais limpo do projeto. Mesmo assim ficou de fora, por número e não por birra: rendeu **25 vagas, todas no primeiro dia** (0,7% do histórico), e a versão internacional estendia o ciclo em 19 minutos entregando zero. A Indeed não tem API pública de busca desde a desativação da Publisher API. Código preservado em `scrapers/indeed*.py`, pronto para religar. |
| **A Gupy corta a profundidade** | O portal declara `total: 100` tanto para `analista de dados` quanto para `analista` — número idêntico para termo estreito e largo é teto, não total (a API antiga dizia 252). Custa pouco porque a lista é ordenada por recência: as ~100 mais recentes cobrem 16 dias, e a janela do robô é de 30. Cobraria numa partida a frio, com banco vazio. |
| **GeekHunter não informa data de publicação** | O card não traz data, nem no container. Então `publicacao_antiga` nunca barra vaga dessa fonte, e anúncio velho pode chegar como novo. Consertar exige uma requisição por vaga — é decisão de custo, não bug. |
| **O alerta de fonte morta está calibrado para fonte grande** | O limiar de 3 ciclos vazios veio da morte da Gupy, que traz centenas por ciclo. A WeWorkRemotely traz 4 num dia bom e 0 nos outros: em 03/10 ela disparou o alerta e voltou 7 horas depois. Decidido manter o limiar; o conserto está desenhado no comentário (limiar por fonte). |
| **Fontes secundárias rendem pouco** | Catho, GeekHunter, 99Jobs e Senior somam menos de 2% das vagas. Funcionam — só não têm volume no nicho buscado. Mantidas porque o critério de remoção é estar quebrada, não render pouco. |
| **A API da Sólides também mente** | `count = 0` na primeira página faz a paginação parar, e esse zero nem sempre é verdade: num ciclo a fonte caiu de ~400 para 70 vagas, e minutos depois a mesma API respondia 209, 133 e 516 vagas para os termos que tinham voltado zero. No dia seguinte foram nove respostas **504**, quase todas já na página 1. Mitigado pela segunda passada, que repete termo com `count = 0`, erro de rede, status ≠ 200 ou resposta não-JSON. **Resultado medido:** 20 vagas inéditas no primeiro ciclo e zero nos oito seguintes. Mantida por decisão da autora, com o número registrado no código. |
| **O botão 👍/👎 nunca foi usado** | O mecanismo está pronto e instrumentado, e o relatório de precisão sabe ler o feedback — mas em 3.624 vagas não há **um único** voto registrado. Enquanto isso continuar, a precisão por fonte é estimada pelo funil, não pela opinião de quem recebe. |
| **O filtro lê só o título** | Vaga de BI com nome comercial (ex: "Analista Comercial" com Power BI na descrição) escapa. É o preço de manter o ruído perto de zero, e está instrumentado no log para virar decisão com número. |
| **Ruído aceito conscientemente** | `Data Center Operations Analyst` passa, porque "data center" casa o qualificador "data". Não apareceu nas amostras medidas; está fixado em teste para quando incomodar. |

---

<div align="center">

*Case de portfólio em automação de dados — Python, Playwright, SQLite, GitHub Actions e engenharia de filtro sem ML.*

</div>
