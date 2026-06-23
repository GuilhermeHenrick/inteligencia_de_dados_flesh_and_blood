from bs4 import BeautifulSoup
import pandas as pd
import requests
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

    link_hash = hashlib.md5(deck_link.encode('utf-8')).hexdigest()

    return link_hash + '_' + id_base

# --- FUNÇÕES AUXILIARES PARA CONCORRÊNCIA ---

def get_max_page(start_page):
    """Busca a última página disponível na paginação a partir da página inicial."""
    url = f"https://fabtcg.com/decklists/?page={start_page}"
    response = get_page(url, session)
    if response:
        soup = BeautifulSoup(response.content, 'lxml')
        pages = soup.find_all('a', class_='page-numbers')
        if pages and len(pages) >= 2:
            # Retorna o valor contido no penúltimo botão (que representa a última página numérica)
            return int(pages[-2].text.strip())
    return start_page

def process_page(page_num, existent_ids):
    """Faz a extração e o parser de uma única página de forma isolada para execução na thread."""
    info_page = []
    hit_existing = False
    
    url = f"https://fabtcg.com/decklists/page/{page_num}/"
    response = get_page(url, session)
    
    if not response:
        return None, False, page_num

    soup = BeautifulSoup(response.content, 'lxml')
    table = soup.find('table')
    
    if not table:
        return info_page, hit_existing, page_num

    trs = table.find_all('tr')
    
    for line in trs:
        columns = line.find_all('td')
        if len(columns) < 7: 
            continue
            
        data = [col.text.strip() for col in columns]
        
        elemento_a = columns[2].find('a')
        data.append(elemento_a.get('href')+' ' if elemento_a else "no_link")
        
        event_type = classify_event(data[3])
        data.append(event_type)

        new_id = create_id(data)
        data.append(new_id)
        
        # Interrompe a varredura se encontrar um deck já salvo
        if new_id not in existent_ids:
            info_page.append(data)
        else:
            hit_existing = True
            break
            
    return info_page, hit_existing, page_num

# Função de extração principal usando ThreadPoolExecutor
def extract_data(existent_ids):
    start_page = 1 
    print(f"Descobrindo o total de páginas a partir da página {start_page}...")
    max_page = get_max_page(start_page)
    
    all_new_data = []
    hit_global = False
    
    BATCH_SIZE = 15
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        for current_batch_start in range(start_page, max_page + 1, BATCH_SIZE):
            if hit_global:
                break
                
            batch_end = min(current_batch_start + BATCH_SIZE, max_page + 1)
            print(f"Processando concorrentemente as páginas: {current_batch_start} a {batch_end - 1}...")
            
            # Submete o lote atual para as threads worker
            futures = {executor.submit(process_page, p, existent_ids): p for p in range(current_batch_start, batch_end)}
            results = {}
            
            # Coleta os resultados assim que cada thread termina
            for future in concurrent.futures.as_completed(futures):
                info, hit, p_num = future.result()
                results[p_num] = (info, hit)
            
            # Consolida na ORDEM DAS PÁGINAS para garantir a consistência do Early Exit
            for p in range(current_batch_start, batch_end):
                if p in results:
                    info, hit = results[p]
                    if info:
                        all_new_data.extend(info)
                    if hit:
                        hit_global = True
                        break

    return all_new_data, hit_global

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

if __name__ == "__main__":
    create_decklists_csv()