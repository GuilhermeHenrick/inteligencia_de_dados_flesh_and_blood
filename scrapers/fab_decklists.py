from bs4 import BeautifulSoup
import pandas as pd
import requests
import time
import hashlib
import sys
import os
import concurrent.futures

# Resolve o diretório raiz do projeto dinamicamente para evitar erros de caminhos relativos durante a execução
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))

output_path = os.path.join(main_dir, 'scrap_output')
os.makedirs(output_path, exist_ok=True)

# Importa as configurações globais e funções de resiliência centralizadas no utils
from scrapers.utils import headers, EVENT_MAPPING, get_page, file_is_updated

csv_name = "decklists_fabtcg.csv"
output_path = os.path.join(output_path, csv_name)

# Utiliza uma Session para reaproveitar a conexão TCP, melhorando significativamente a performance em múltiplas requisições
session = requests.Session()
session.headers.update(headers)

# Aplica regras de negócio (Look-up Table) para limpar e padronizar nomes de eventos não estruturados (Data Cleansing)
def classify_event(event_name):
    lower_name = str(event_name).lower()
    for key, value in EVENT_MAPPING.items():
        if key in lower_name:
            return value
    return "other"

# Cria uma chave primária (ID) determinística combinando metadados e um hash MD5 da URL para garantir unicidade no banco de dados
def create_id(data):
    country, date, decklist_name, event, format, hero, result, deck_link, event_type = data

    last_word = decklist_name.split(" ")[-1]
    words_id = decklist_name.split(" ")[0:-1]
    
    initials = [word[0] for word in words_id if word] 
    string_initials = ''.join(initials)
    
    pos = 'ni' if result == 'not informed' else result
    id_base = string_initials + last_word + pos

    link_hash = hashlib.md5(deck_link.encode('utf-8')).hexdigest()[:6]

    return id_base + link_hash

# Função de extração principal que recebe 'existent_ids' para aplicar a lógica de raspagem incremental (só baixa o que é novo)
def extract_data(existent_ids):
    info_page = []
    hit_existing = False
    
    for p in range(1, 20):
        if hit_existing:
            break
            
        url = f"https://fabtcg.com/decklists/?page={p}"
        response = get_page(url, session)

        if response:
            soup = BeautifulSoup(response.content, 'lxml')
            table = soup.find('table', class_='table table-striped table-hover decklist-table')
            
            if not table:
                continue

            trs = table.find_all('tr')
            
            for line in trs:
                columns = line.find_all('td')
                if len(columns) < 7: 
                    continue
                    
                data = [col.text.strip() for col in columns]
                
                elemento_a = columns[2].find('a')
                data.append(elemento_a.get('href') if elemento_a else "no_link")
                
                event_type = classify_event(data[3])
                data.append(event_type)

                new_id = create_id(data)
                data.append(new_id)
                
                # Interrompe a varredura (Early Exit) imediatamente ao encontrar um deck já salvo, poupando recursos e rede
                if new_id not in existent_ids:
                    info_page.append(data)
                else:
                    hit_existing = True
                    break
        else:
            return None, False

    return info_page, hit_existing

# Orquestrador do módulo responsável pelo controle de estado do arquivo e persistência final dos dados (I/O)
def create_decklists_csv():
    if file_is_updated(output_path):
        print(f"The {output_path} is now updated with today's date.")
    else:
        existent_ids = set()
        
        # Carrega os IDs já conhecidos para a memória (Cache) antes de iniciar a extração
        if os.path.exists(output_path):
            old_csv = pd.read_csv(output_path)
            if 'deck_id' in old_csv.columns:
                existent_ids = set(old_csv['deck_id'])
        else:
            old_csv = pd.DataFrame()
        
        info_new, hit_existing = extract_data(existent_ids)
    
        if info_new:
            columns_df = ["country", "date", "decklist", "event", "format", "hero", "result", "deck_link", "event_type", "deck_id"]
            df_new = pd.DataFrame(info_new, columns=columns_df)
            df_new['result'] = df_new['result'].replace('', 'not informed')
    
            # Realiza a concatenação dos dados recém-raspados com o histórico antigo (Upsert/Merge em arquivo plano)
            if not old_csv.empty:
                df_updated = pd.concat([df_new, old_csv], ignore_index=True)
            else:
                df_updated = df_new
    
            df_updated.to_csv(output_path, index=False)
            print(f"Success! {len(info_new)} New decks added to {output_path}.")
        else:
            print("The scan was complete, no new decks to add.")