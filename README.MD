# ⚔️ Flesh and Blood TCG — Inteligência de Dados

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-gray?style=for-the-badge)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow?style=for-the-badge)

## 📌 Sobre o Projeto

Este projeto é uma **pipeline de Engenharia e Inteligência de Dados** construída para extrair, tratar e modelar dados competitivos do TCG *Flesh and Blood* (FaB).

O ecossistema do jogo gera um volume grande de informações descentralizadas: decklists de torneios, pontuação do formato Living Legend, além do catálogo completo de cartas com seus atributos mecânicos. O objetivo do sistema é automatizar a coleta (scraping), padronizar e cruzar esses dados, e persistir tudo em um modelo relacional (SQLite), permitindo análises como composição de metagame, popularidade de heróis e aderência de cartas em diferentes formatos.

---

## 🤖 Uso de IA no Desenvolvimento

Usei o **Google Gemini** como mentor técnico ao longo do desenvolvimento — para revisar decisões de arquitetura, discutir trade-offs e apontar boas práticas. A lógica de negócio, a modelagem dos dados e a implementação são minhas; a IA atuou como revisora e caixa de ressonância, não como autora do projeto.

Na prática, esse apoio se traduziu em:

- **Discussões sobre concorrência** — por que paralelizar a extração detalhada de decklists com `ThreadPoolExecutor` e por que proteger a escrita no JSONL com `threading.Lock()` para evitar corrupção por escrita simultânea.
- **Revisão da estratégia de migração** — validação do uso de *Zero-Copy* via `ATTACH DATABASE` no SQLite para clonar o catálogo de cartas sem reprocessamento custoso em Python.
- **Boas práticas de resiliência e integridade** — discussão sobre requisições resilientes (retry com espera entre tentativas), idempotência (raspagem incremental por ID determinístico) e integridade referencial no banco.
- **Documentação orientada ao "porquê"** — os comentários nos scripts descrevem não só *o que* o código faz, mas a **decisão de engenharia** por trás de cada trecho.

Todas as decisões documentadas na seção de arquitetura abaixo eu consigo explicar e defender — que é, no fim, o que torna o projeto meu.

---

## 📡 Fontes de Dados

| Tipo de Dado | Fonte | Método de Ingestão |
| :--- | :--- | :--- |
| **Decklists e Torneios** | [fabtcg.com/decklists](https://fabtcg.com/decklists/) | Scraping via `BeautifulSoup` + `requests` |
| **Living Legend (Pontuação)** | [fabtcg.com/living-legend](https://fabtcg.com/living-legend/) | Scraping HTML estruturado, parseado com `Pandas` |
| **Catálogo completo de cartas** | [The Fab Cube (GitHub)](https://github.com/the-fab-cube/flesh-and-blood-cards) | Download direto do JSON oficial |

---

## 🚀 Arquitetura e Decisões de Engenharia

### 1. Orquestração centralizada (`run_scrapers.py`)
Um único ponto de entrada dispara os três scrapers em sequência, com cronômetro de execução e um bloco `try/except/finally` que isola falhas de um scraper sem derrubar o restante da pipeline.

### 2. Geração determinística de chaves (`deck_id`)
O site não expõe um ID único por deck. Por isso, o `deck_id` é construído combinando metadados do torneio (iniciais do nome, última palavra, posição do jogador) com um **hash MD5** da URL do deck — garantindo unicidade e permitindo *upserts* seguros sem duplicar registros em raspagens futuras.

### 3. Raspagem incremental e idempotente
Os scripts evitam trabalho redundante de duas formas:
- **Por data:** `file_is_updated()` verifica se o arquivo já foi atualizado no dia, evitando novas requisições desnecessárias (`fab_ll.py`).
- **Por ID já conhecido:** `fab_decklists.py` interrompe a varredura de páginas assim que encontra um `deck_id` já salvo (*early exit*), evitando reler o histórico inteiro a cada execução.

### 4. Concorrência e Thread Safety (`fab_decklists_detail.py`)
A extração detalhada de cada decklist individual é o gargalo de I/O da pipeline (milhares de páginas). Para resolver isso:
- Uso de `ThreadPoolExecutor` (15 workers) para paralelizar as requisições.
- Persistência em arquivo *append-only* (`.jsonl`), protegida por `threading.Lock()` para impedir corrupção por escrita simultânea.
- Em caso de interrupção, a extração retoma de onde parou, lendo os IDs já salvos no JSONL.

### 5. Zero-Copy Database Migration (`build_database.py`)
Para cruzar os dados de decks com o catálogo de cartas, o script usa `ATTACH DATABASE` do SQLite, clonando a tabela de cartas diretamente dentro do próprio motor SQL — sem precisar carregar tudo em memória Python e reinserir linha a linha.

### 6. Schema Drift Resilience (`build_full_cards_database.py`)
A LSS (criadora do jogo) introduz novos atributos com frequência. Em vez de colunas fixas (*hardcoded*), o script varre dinamicamente todas as chaves presentes no JSON de cartas e cria as colunas da tabela sob demanda — apenas fixando `unique_id`, `name`, `pitch` e `types` no início, por legibilidade.

### 7. Data Cleansing e heurísticas (`utils.py`)
- **Look-up table (`EVENT_MAPPING`):** padroniza nomes caóticos de eventos digitados por lojistas em categorias estruturadas.
- **Classes e Talentos dinâmicos:** como essas categorias não vêm explícitas na API, o sistema usa conjuntos (`set`) e uma heurística gramatical (a Classe é sempre a última palavra do campo `types` de um herói) para descobrir Classes e Talentos automaticamente — tornando o código resistente a novos lançamentos do jogo.
- **Resiliência de rede:** `get_page()` tenta cada requisição até 3 vezes, com pausa entre as tentativas, protegendo a pipeline contra instabilidades pontuais do site.

---

## 📂 Estrutura do Projeto

```text
├── run_scrapers.py                       # Entry point: orquestra todos os scrapers em sequência
├── requirements.txt                      # Dependências do projeto
│
├── scrapers/
│   ├── utils.py                          # Headers, retry logic, data cleansing, listas dinâmicas de Classes/Talentos
│   ├── fab_decklists.py                  # Índice de decklists (raspagem incremental por página)
│   ├── fab_decklists_detail.py           # Detalhe de cada decklist (multithread + lock + resume)
│   └── fab_ll.py                         # Pontuação atual do formato Living Legend
│
├── database_scripts/
│   ├── build_full_cards_database.py      # Baixa o JSON oficial de cartas e gera full_cards.db (schema dinâmico)
│   └── build_database.py                 # Modelagem relacional final: Player, Deck, Deck_Card (com Zero-Copy)
│
├── scrap_output/                         # CSVs e JSONL gerados pelos scrapers
│   ├── decklists_fabtcg.csv
│   ├── detailed_decklists.jsonl
│   └── living_legends_fabtcg.csv
│
└── database_output/                      # Bancos de dados SQLite e cache do catálogo de cartas
    ├── full_cards.json
    ├── full_cards.db
    └── fabtcg_decklists.db
```

---

## 🗄️ Modelo de Dados (banco final: `fabtcg_decklists.db`)

| Tabela | Descrição |
| :--- | :--- |
| `Cards` | Catálogo completo de cartas (clonado do `full_cards.db` via Zero-Copy) |
| `Player` | Jogadores únicos, identificados por `player_id` |
| `Deck` | Metadados de cada decklist: herói, evento, formato, posição e data |
| `Deck_Card` | Relação N:N entre `Deck` e `Cards`, com pitch, quantidade e flag de equipamento |

---

## ⚙️ Como Executar

1. Clone o repositório e instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

2. Construa o catálogo de cartas (necessário antes do banco de decklists):
   ```bash
   python database_scripts/build_full_cards_database.py
   ```

3. Rode a pipeline de scrapers (decklists e Living Legend):
   ```bash
   python run_scrapers.py
   ```

4. Construa o banco relacional final, cruzando decklists com o catálogo de cartas:
   ```bash
   python database_scripts/build_database.py
   ```

Ao final, o arquivo `database_output/fabtcg_decklists.db` estará pronto para consultas SQL e análises de Data Science.

---

## 🛠️ Stack Principal

- **Python 3** — linguagem principal do projeto
- **Requests + BeautifulSoup (lxml)** — coleta e parsing de HTML
- **Pandas** — manipulação e persistência tabular (CSV)
- **SQLite3** — modelagem e persistência relacional
- **concurrent.futures (ThreadPoolExecutor)** — paralelização de I/O de rede
- **Streamlit / Plotly / Matplotlib** *(disponíveis em `requirements.txt`)* — para futuras camadas de visualização e análise

---

## 📈 Status

Projeto em desenvolvimento ativo. Próximos passos incluem camadas de análise exploratória (metagame, win rate por herói) e, possivelmente, um dashboard interativo sobre os dados já coletados.
