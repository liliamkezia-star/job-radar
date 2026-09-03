<div align="center">

# 📡 JobRadar
### Monitor Automatizado de Vagas de Dados & BI

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Scraping-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Banco%20versionado-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/testes-573%20passing-success?style=for-the-badge)
![Status](https://img.shields.io/badge/status-em%20produção-success?style=for-the-badge)

**Autora:** Liliam Kezia Oliveira Souza

</div>

---

## 💎 Proposta de valor

> Em cidade pequena, vaga boa de Dados/BI aparece pouco e some rápido — quem checa o board duas vezes por dia perde para quem checou na primeira hora. **JobRadar** substitui essa checagem manual: varre **9 fontes** a cada **3 horas**, filtra por cargo, cidade, mercado e idioma em três níveis de confiança, pontua cada vaga por relevância e notifica no Telegram — de graça, sem servidor próprio, 24 horas por dia.

## 📄 Resumo executivo

Entre 07 de agosto e 1º de setembro de 2026, o sistema processou **2.437 vagas únicas** sem intervenção manual.

| Indicador | Número |
|---|---|
| 📊 Vagas processadas (deduplicadas) | **2.437** |
| 🧪 Testes automatizados (CI a cada push) | **573** |
| 🌎 Fontes monitoradas | **9** |
| 🏙️ Cidades-alvo + remoto | **9 + remoto** |
| ⏱️ Frequência de checagem | **a cada 3h** |
| 🔗 Concentração numa única fonte (LinkedIn) | **93,4%** ⚠️ |
| 💰 Custo de infraestrutura | **R$ 0** |

A concentração em LinkedIn está documentada como **risco**, não como conquista: o endpoint usado não é oficial, e o sistema perde quase todo o alcance se ele mudar ou bloquear. Ver [Limites conhecidos](#-limites-conhecidos).

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
| Vagas do LinkedIn com data | 231/1.639 (14,1%) | **504/504 (100%)** |

**Três hipóteses minhas foram derrubadas pelos próprios dados** — e é isso que a medição serve para fazer:

- *"Esses avisos de vaga perdida são alarme falso"* — eram, em três fontes. Na quarta, não: as buscas devolviam 10 resultados quando rodadas isoladas. O aviso estava certo e vaga estava sendo perdida.
- *"O perfil internacional só precisa das keywords que o Brasil já tem"* — alinhar as listas ganhou **zero** vaga. O que ganhou 7 foi um mecanismo que aquele perfil não tinha.
- *"Cidade pequena com ferramenta de nicho não tem vaga mesmo"* — tinha 10.

Quando a medição não é possível, isso fica escrito no código em vez de escondido. A correção de rate-limit do LinkedIn, por exemplo, só se manifesta no IP de datacenter do GitHub Actions e não reproduz localmente — então foi desenhada para ser **segura por construção**: ajuda se o diagnóstico estiver certo, e não piora nada se estiver errado.

---

## 📸 Como chega para você

Vaga de alta relevância chega na hora, com nível, data de publicação e link. O resto entra num resumo diário ranqueado — sem virar spam. Vaga com mais de 30 dias ganha aviso de "pode já estar preenchida" e sai do alerta imediato, mas nunca é descartada.

---

## 🗂️ Sumário

- [Como as decisões são tomadas](#-como-as-decisões-são-tomadas)
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
| **Busca** | Varre as fontes em paralelo, com rodízio de termos para controlar custo por ciclo |
| **Filtra** | Cargo (forte / ambíguo + qualificador / ferramenta + cargo), cidade ou mercado remoto, idioma |
| **Pontua** | Score 1–10 por vaga: cargo, ferramenta, senioridade, mercado, idioma — soma de sinais, sem IA |
| **Deduplica** | Por link e por empresa+título, para pegar a mesma vaga republicada em fonte diferente |
| **Notifica** | Alta relevância na hora; o resto num resumo diário ranqueado, melhor vaga no topo |
| **Aprende** | Botão 👍/👎 em cada notificação — feedback vira dado para medir precisão por fonte e por semana |

## 🏗️ Arquitetura técnica

- **Filtro em 3 níveis de confiança:** cargo inequívoco passa sozinho; cargo ambíguo (ex: `Analyst`) só conta com um qualificador de dados junto no título; ferramenta (ex: `Power BI`) só conta com palavra de cargo junto. Nada aprova por palavra solta — é o que segura `Financial Analyst` e `HR Analyst` fora do radar.
- **Score de relevância sem ML:** 5 sinais conhecidos, pesos calibrados contra o histórico real do banco. Conjunto pequeno e conhecido não precisa de modelo — precisa de critério explicável.
- **Zero infraestrutura:** GitHub Actions como motor de cron, SQLite como banco versionado no próprio Git. O histórico de vagas já vistas *é* o commit.
- **Resiliente:** nunca marca vaga como vista sem confirmar que a notificação saiu; alerta se a maioria das fontes falhar num ciclo; heartbeat diário confirmando que o robô está de pé; e uma segunda passada no fim do ciclo — no LinkedIn e na Sólides — que repete só as buscas que voltaram vazias. Ela se mede sozinha no log e carrega no código o critério que a mata, escrito antes do primeiro resultado (ver Limites conhecidos).
- **573 testes em CI:** cada caso documenta um bug real já corrigido nesta base — inclusive os que ainda não foram corrigidos, fixados como comportamento conhecido em vez de escondidos.

## 📋 Regras de negócio

O filtro existe para uma busca específica, e as regras estão explícitas em `core/config.py`:

- **Brasil remoto:** aceito de qualquer lugar do país.
- **Brasil presencial ou híbrido:** só em Campina Grande-PB, João Pessoa-PB, Recife-PE, Natal-RN, Caruaru-PE, Manaus-AM, Maceió-AL, Aracaju-SE e Fortaleza-CE.
- **Internacional:** **só remoto**, e só em mercados de língua portuguesa ou espanhola. Presencial e híbrido fora do Brasil são rejeitados; `Remote — US only` é rejeitado.

Cidade homônima é tratada: `Campina Grande do Sul, Paraná` e `Fortaleza de Minas, Minas Gerais` são barradas pela conferência de UF, que entende tanto a sigla quanto o estado por extenso.

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
├── scrapers/                    ← um módulo por fonte
├── tests/                       ← 573 casos, roda em CI a cada push
├── data/
│   └── jobs.db                  ← banco versionado (histórico de dedup)
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

573 casos em 19 arquivos, cobrindo filtro, regras de negócio, paginação de cada fonte, datas de publicação e o relatório de precisão — todos rodando a cada push via GitHub Actions.

Os testes seguem uma convenção: **cada arquivo começa explicando o bug real que o motivou**, com o número medido. Um teste que só afirma que `2 + 2 = 4` não conta; o que conta é o que quebrou de verdade e como se descobriu.

## ⚠️ Limites conhecidos

Registrados de propósito — problema documentado é problema que alguém pode consertar.

| Limite | Situação |
|---|---|
| **93,4% das vagas vêm do LinkedIn** | Endpoint não oficial. Se mudar ou bloquear, o sistema perde quase todo o alcance. |
| **Resposta instável do LinkedIn** | O endpoint guest às vezes serve a página e às vezes devolve vazio para a *mesma* busca. Medido em três rodadas: o mesmo par (termo × cidade) devolve 0 e 10 em horas diferentes, do mesmo IP. A primeira hipótese — bloqueio ao IP de datacenter do Actions — foi **derrubada**: o ciclo rodado em rede residencial deu 22 buscas vazias contra 13 do Actions. Repetir na hora (5s/10s/30s) recuperou 0 de 13; o rodízio de termos recupera 12 de 22 sozinho. Mitigação atual: repetir no fim do ciclo. **Medida em produção, 4 ciclos:** recuperou 43, 25, 94 e 27 vagas inéditas — buscas que o ciclo teria dado como vazias. Custo: ~25 requisições extras em ~375, cerca de 2 minutos. |
| **Fontes secundárias rendem pouco** | Catho, GeekHunter e 99Jobs somam menos de 3% das vagas. Funcionam — só não têm volume no nicho buscado. Mantidas porque o critério de remoção é estar quebrada, não render pouco. |
| **A API da Sólides também mente** | `count = 0` na primeira página faz a paginação parar, e esse zero nem sempre é verdade: num ciclo a fonte caiu de ~400 para 70 vagas, e minutos depois a mesma API respondia 209, 133 e 516 vagas para os termos que tinham voltado zero. No dia seguinte foram nove respostas **504**, quase todas já na página 1 — um erro ali não custa uma busca, custa o termo inteiro. Mitigado pela mesma segunda passada, que repete termo com `count = 0`, erro de rede, status ≠ 200 ou resposta não-JSON. |
| **O filtro lê só o título** | Vaga de BI com nome comercial (ex: "Analista Comercial" com Power BI na descrição) escapa. É o preço de manter o ruído perto de zero, e está instrumentado no log para virar decisão com número. |
| **Ruído aceito conscientemente** | `Data Center Operations Analyst` passa, porque "data center" casa o qualificador "data". Não apareceu nas amostras medidas; está fixado em teste para quando incomodar. |

---

<div align="center">

*Case de portfólio em automação de dados — Python, Playwright, SQLite, GitHub Actions e engenharia de filtro sem ML.*

</div>
