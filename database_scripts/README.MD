# ⚔️ Flesh and Blood TCG - Data Intelligence Pipeline

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-gray?style=for-the-badge)

## 📌 Sobre o Projeto
Este projeto é uma **Pipeline Completa de Engenharia de Dados (ETL)** desenvolvida para extrair, transformar e modelar dados competitivos do Card Game *Flesh and Blood* (FaB). 

O ecossistema do jogo gera um volume massivo de dados descentralizados. O objetivo deste sistema é realizar a ingestão contínua e automatizada de milhares de decklists de torneios oficiais, cruzar essas informações com um banco de dados relacional (que contém todos os atributos mecânicos de cada carta) e persistir tudo em um modelo estruturado. Isso permite análises profundas de *Data Science*, como a composição do metagame, taxa de vitórias de heróis específicos e a aderência de cartas em formatos competitivos.

---

## 📡 Fontes de Dados (Data Sources)

A pipeline consome informações de diferentes fontes estruturadas e não estruturadas, unificando-as no final do processo:

| Tipo de Dado | Fonte | Método de Ingestão |
| :--- | :--- | :--- |
| **Decklists e Torneios** | [Site Oficial Flesh and Blood](https://fabtcg.com/decklists/) | Scraping via `BeautifulSoup` e `requests` |
| **Living Legend (Pontuação)** | [FaB TCG - Living Legend](https://fabtcg.com/living-legend/) | Scraping HTML estruturado em `Pandas` |
| **Heróis e Armas Assinatura** | [FaB TCG - Heroes](https://fabtcg.com/heroes/) | Scraping HTML |
| **Database de Cartas (Atributos)** | [The FaB Cube (GitHub)](https://github.com/the-fab-cube/flesh-and-blood-cards) | API / Consumo de payload `.json` bruto |

---

## 🚀 Arquitetura e Decisões de Engenharia

Para garantir que o sistema escale sem gargalos e suporte as atualizações frequentes do jogo, diversas práticas avançadas de Engenharia de Software e Dados foram implementadas:

### 1. Geração Determinística de Chaves (`deck_id`)
Como o site oficial não expõe um ID único rastreável para cada deck na tabela principal, foi necessário criar uma chave primária sintética e idempotente. O `deck_id` é gerado através da **combinação de metadados do torneio** (iniciais do nome, última palavra e posição do jogador) acoplada a um **Hash MD5 da URL original** do deck. Isso garante unicidade no banco de dados e impede a duplicidade de registros em raspagens futuras (Upsert seguro).

### 2. Schema Drift Resilience (Resiliência a Mudanças de Esquema)
A LSS (criadora do jogo) frequentemente introduz novas mecânicas e atributos nas cartas. O banco de dados SQLite principal (`full_cards.db`) não possui colunas *hardcoded*. O script varre dinamicamente as chaves (keys) de todo o JSON de cartas extraído e **cria as colunas da tabela sob demanda**, forçando apenas as chaves principais (`internal_id`, `unique_id`, `name`, `pitch`, `types`) no início para melhor UX e legibilidade de Analistas de Dados.

### 3. Extração Concorrente e Thread Safety
O download de milhares de páginas individuais de decklists seria um gargalo de I/O em execução síncrona. 
* O projeto utiliza `ThreadPoolExecutor` para realizar dezenas de requisições simultâneas.
* A persistência dos dados brutos é feita em um arquivo *Append-Only* (`.jsonl`), protegido por um `threading.Lock()` (MutEx) para garantir a exclusão mútua e evitar corrupção do JSON durante a escrita paralela.
* Em caso de interrupção, o sistema retoma exatamente de onde parou lendo os IDs já salvos no JSONL.

### 4. Zero-Copy Database Migration
Para cruzar os metadados dos decks com os dados das cartas, foi utilizado o comando nativo `ATTACH DATABASE` do SQLite. Em vez de exportar os dados das cartas para a memória do Python (pandas/listas) e recriá-los com comandos lentos de `INSERT`, a tabela de cartas é clonada diretamente dentro do motor SQL (Zero-Copy), preservando chaves, restrições e ordenação quase instantaneamente.

### 5. Data Cleansing e Heurísticas
A internet possui dados "sujos". O módulo `utils.py` atua como um sanitizador:
* **Look-up Tables:** Um dicionário `EVENT_MAPPING` padroniza os nomes caóticos de torneios digitados por lojistas para categorias estruturadas (ex: "Pro Quest").
* **Heurísticas Reflexivas:** Classes e Talentos não estão explícitos na API. O sistema usa matemática de conjuntos (`set`) e heurísticas gramaticais para varrer a base lendo o final das *strings* e descobrindo dinamicamente novas Classes e Talentos, tornando o projeto *Future-Proof*.

---

## 📂 Estrutura do Projeto

```text
├── run_scrapers.py                   # Entry point: Orquestrador da extração de dados
├── scrapers/  
│   ├── utils.py                      # Regras de negócio, headers, Data Cleansing e Retry Logic
│   ├── fab_decklists.py              # Extração do índice de torneios (Incremental)
│   ├── fab_decklists_detail.py       # Extração detalhada das listas (Multithread e Lock)
│   ├── fab_ll.py                     # Scraping da pontuação de Living Legend
│   ├── fab_ll_heroes.py              # Histórico de Heróis rotacionados
│   └── signature_weapons.py          # Mapeamento de Heróis e Armas
├── database_scripts/  
│   ├── build_full_cards_database.py  # Baixa o JSON oficial e estrutura em SQLite (Schema Dinâmico)
│   └── build_database.py             # Modelagem dimensional relacional final (Player, Deck, Deck_Card)
└── database_output/                  # Artefatos gerados (Arquivos .db e .jsonl)