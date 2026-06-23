from bs4 import BeautifulSoup
import pandas as pd
import requests
import os
from scrapers.utils import headers, get_page, file_is_updated, delete_file

# Resolve dinamicamente os caminhos absolutos do projeto para garantir o funcionamento independente de onde o orquestrador é acionado
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))

URL = 'https://fabtcg.com/living-legend/'

# Orquestrador responsável por extrair o status histórico de heróis que já rotacionaram (atingiram o formato Living Legend)
def create_ll_heroes_csv():

    output_path = os.path.join(main_dir, 'scrap_output')
    os.makedirs(output_path, exist_ok=True)

    csv_name = 'll_heroes_fabtcg.csv'
    output_path = os.path.join(output_path, csv_name)

    # Validação de estado (Early Exit): evita consumo desnecessário de rede e processamento se a base já foi atualizada hoje
    if file_is_updated(output_path):
        print(">>>ll_heroes_fabtcg.csv is up to date.")
        return
    else:
        print(">>>ll_heroes_fabtcg.csv doesn't exist or is out of date. Updating...")
        
        # Garante a remoção do arquivo desatualizado para prevenir corrupção de dados ou mix de informações antigas com novas
        delete_file(output_path)

        # Utiliza uma sessão HTTP persistente (Keep-Alive) em conjunto com o sistema de retry (get_page) para garantir resiliência
        session = requests.Session()
        session.headers.update(headers)
        response = get_page(URL, session)
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table', class_ = 'has-fixed-layout')

        # Validação de integridade do DOM: assegura que o site renderizou as tabelas corretamente antes de acessar índices fixos
        if len(tables) > 1:
            trs = tables[2].find_all('tr')
            heroes = []
            formats = []

            for line in trs[1:]:
                tr = line.find_all('td')
                if len(tr) >= 2:
                    heroes.append(tr[0].text.strip())
                    formats.append(tr[1].text.strip())

            df = pd.DataFrame({
                'Hero': heroes,
                'Format': formats,
            })

            # Persiste os dados de forma limpa (index=False) para não gerar colunas numéricas residuais e manter o banco de dados puro
            df.to_csv(output_path, index=False)
            print(">>>ll_heroes_fabtcg.csv successfully updated!")
        else:
            print("Erro: Tabela de herois Living Legends não encontrada no HTML.")

if __name__ == "__main__":
    create_ll_heroes_csv()