from bs4 import BeautifulSoup
import pandas as pd
import requests
import sys
import os
from scrapers.utils import headers, get_page, file_is_updated, delete_file

# Resolve dinamicamente os caminhos absolutos do projeto para evitar erros de execução independentemente de onde o script for chamado
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))

URL = 'https://fabtcg.com/living-legend/'

# Orquestrador responsável por extrair, limpar e persistir a pontuação oficial do formato Living Legend
def create_ll_csv():
    output_path = os.path.join(main_dir, 'scrap_output')
    os.makedirs(output_path, exist_ok=True)

    csv_name = 'living_legends_fabtcg.csv'
    output_path = os.path.join(output_path, csv_name)

    # Validação de estado (Early Exit) para evitar consumo de rede e processamento redundante se o arquivo já for do dia atual
    if file_is_updated(output_path):
        print(">>>living_legends_fabtcg.csv up to date")
        return
    else:
        print(">>>living_legends_fabtcg.csv dont exist or is out of date.")
        
        # Garante a remoção da base antiga para evitar mistura de dados ou leitura de arquivos corrompidos
        delete_file(output_path)

        # Utiliza uma sessão HTTP para manter a conexão viva (Keep-Alive), otimizando a performance da requisição
        session = requests.Session()
        session.headers.update(headers)
        response = get_page(URL, session)
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table', class_ = 'has-fixed-layout')

        # Validação de segurança: assegura que o site possui as tabelas esperadas antes de forçar o acesso ao índice [2]
        if len(tables) > 2:
            trs = tables[2].find_all('tr')
            heroes = []
            current_season_points = []
            points = []

            for line in trs[1:]:
                tr = line.find_all('td')
                if len(tr) >= 4:
                    heroes.append(tr[1].text.strip())

                    # Tratamento de dados (Fallback): garante que heróis recém-lançados sem pontuação recebam zero, evitando valores nulos no banco
                    if len(tr[2].text.strip()) > 0:
                        current_season_points.append(tr[2].text.strip())
                    else:
                        current_season_points.append(0)

                    if len(tr[3].text.strip()) > 0:
                        points.append(tr[3].text.strip())
                    else:
                        points.append(0)

            df = pd.DataFrame({
                'Hero': heroes,
                'Current_Season_Points': current_season_points,
                'Points': points
            })

            # Persiste os dados brutos de forma limpa (index=False) para não gerar colunas numéricas residuais durante a importação no SQLite
            df.to_csv(output_path, index=False)
            print(">>>living_legends_fabtcg.csv up to date")
        else:
            print("Erro: Tabela de Living Legends não encontrada no HTML.")

if __name__ == "__main__":
    create_ll_csv()