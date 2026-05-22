# ⚔️ Inteligência de Dados - TCG Flesh and Blood

## 📌 Sobre o Projeto
Este projeto consiste em um pipeline de **Engenharia de Dados e Web Scraping** focado na extração, transformação e análise de dados do metagame do Trading Card Game (TCG) **Flesh and Blood**. 

O objetivo principal é coletar dados de *decklists*, heróis e cartas, processá-los de forma eficiente e estruturá-los para consumo em dashboards interativos (como Looker Studio), permitindo análises aprofundadas sobre o estado atual do jogo.

## 🚀 Tecnologias e Ferramentas
* **Linguagem:** Python
* **Web Scraping:** `BeautifulSoup`, `requests`
* **Processamento de Dados:** `pandas`
* **Orquestração:** `papermill` (para execução programática de Jupyter Notebooks)
* **Armazenamento:** Arquivos `.csv`

## 📂 Estrutura do Repositório
* `Fab_decklists.ipynb` / `Fab_herois.ipynb`: Notebooks responsáveis pela lógica de extração e transformação inicial das diferentes entidades do jogo.
* `merge_dfs.py`: Script principal que orquestra todo o pipeline. Utiliza o `papermill` para rodar os notebooks parametrizados e consolida os DataFrames em uma base única.
* `utils.py`: Módulo contendo funções auxiliares e reutilizáveis (como paginação, headers de requisição e tratamentos HTML).

## ⚙️ Principais Funcionalidades
* **Extração Paralelizada:** Uso de múltiplas *threads* para realizar requisições simultâneas, reduzindo drasticamente o tempo de coleta nas páginas de decks.
* **ETL Automatizado:** Transformação de notebooks de exploração visual em etapas automatizadas e sólidas de um pipeline de dados através do `papermill`.
* **Armazenamento Otimizado:** Exportação dos dados consolidados em formato Parquet para maior compressão e performance na leitura em ferramentas de BI.
* **Scraping Ético:** Implementação de *delays* controlados entre as requisições para evitar sobrecarga nos servidores de origem.

## 🛠️ Como Executar

1. **Clone o repositório:**
   
```bash
   git clone [https://github.com/GuilhermeHenrick/Intelig-ncia-de-Dados-TCG-Flash-and-Blood-.git](https://github.com/GuilhermeHenrick/Intelig-ncia-de-Dados-TCG-Flash-and-Blood-.git)
   cd Intelig-ncia-de-Dados-TCG-Flash-and-Blood-