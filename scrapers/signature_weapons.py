from bs4 import BeautifulSoup
import pandas as pd
import requests
import sys
import os
from scrapers.utils import headers, get_page, file_is_updated, delete_file

# Resolve dinamicamente os caminhos absolutos do projeto para garantir o funcionamento independente de onde o orquestrador é acionado
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))

URL = 'https://fabtcg.com/heroes/'

# Orquestrador responsável por extrair e mapear a relação de 1:1 entre os heróis e suas armas assinatura
def create_weapons_csv():
    output_path = os.path.join(main_dir, 'scrap_output')
    os.makedirs(output_path, exist_ok=True)

    csv_name = 'signature_weapons_fabtcg.csv'
    output_path = os.path.join(output_path, csv_name)

    # Validação de estado (Early Exit): evita consumo desnecessário de banda e processamento se a base de armas já estiver atualizada no dia
    if file_is_updated(output_path):
        print(">>>signature_weapons_fabtcg.csv is up to date.")
        return
    else:
        print(">>>signature_weapons_fabtcg.csv doesn't exist or is out of date. Updating...")
        delete_file(output_path)

        # Utiliza a função resiliente do utils com Session para manter a conexão ativa (Keep-Alive) e lidar com rate limits
        session = requests.Session()
        session.headers.update(headers)
        response = get_page(URL, session)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Varredura do DOM: isola os blocos individuais de cada herói para evitar cruzamento acidental de dados durante o loop
        blocks = soup.find_all('div', class_='col-sm-6 col-md-4 col-lg-3 blockblock block-list-margin')
        
        heroes = []
        weapons = []

        for block in blocks:
            hero_name = block.find('h3').text.strip()
            weapon_element = block.find('p')
            
            if weapon_element and 'Signature Weapon:' in weapon_element.text:
                weapon_name = weapon_element.text.replace('Signature Weapon:', '').strip()
                
                # Limpeza de dados (Data Cleansing): remove aspas simples/duplas que vêm do HTML para garantir a integridade da chave no banco relacional
                weapon_name = weapon_name.replace("'", "").replace('"', "").strip()
                
                heroes.append(hero_name)
                weapons.append(weapon_name)

        df = pd.DataFrame({
            'Hero': heroes,
            'Weapon': weapons
        })

        # Persiste os dados brutos de forma limpa (index=False) para não gerar colunas numéricas residuais durante a importação no SQLite
        df.to_csv(output_path, index=False)
        print(">>>signature_weapons_fabtcg.csv successfully updated!")

if __name__ == "__main__":
    create_weapons_csv()