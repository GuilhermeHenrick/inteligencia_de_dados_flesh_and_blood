from bs4 import BeautifulSoup
import pandas as pd
import requests
import json
import time
import sys
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from scrapers.utils import headers, get_page

# Resolve dinamicamente os caminhos absolutos do projeto para garantir o funcionamento independente de onde o orquestrador é acionado
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))

# Função core de parsing: converte a estrutura HTML não padronizada da página em um dicionário Python estruturado (Data Extraction)
def extract_decklist(url, deck_id, session):
    response = get_page(url, session)
    if not response:
        return {"Deck ID": deck_id, "Erro": "Página não acessível"}
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    player_info = {}
    player_element = soup.find('h4', class_='text-center decklist-author')
    if player_element and player_element.find('a'):
        player_a = player_element.find('a')
        player_info['name'] = player_a.text.strip()
        player_info['id'] = player_a.get('href').split('/')[-2]
    
    country_element = soup.find('span', class_='flag-icon')
    if country_element:
        classes = country_element.get('class', [])
        for c in classes:
            if c.startswith('flag-icon-'):
                player_info['country'] = c.replace('flag-icon-', '').upper()

    decklist_info = {}
    info_table = soup.find('table', class_='table table-striped table-hover decklist-table')
    if info_table:
        for tr in info_table.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) == 2:
                key = tds[0].text.strip().lower()
                val = tds[1].text.strip()
                decklist_info[key] = val

    deck_name = ""
    name_element = soup.find('h1', class_='text-center title')
    if name_element:
        deck_name = name_element.text.strip()

    hero_name = ""
    hero_header = soup.find('div', class_='decklist-header-image')
    if hero_header:
        hero_div = hero_header.find('div', class_='decklist-hero')
        if hero_div and hero_div.find('h1'):
            hero_name = hero_div.find('h1').text.strip()

    deck_data = {
        "Deck ID": deck_id,
        "Decklist_name": deck_name,
        "Hero": hero_name,
        "Player_info": player_info,
        "Decklist_info": decklist_info,
        "Equipments": [],
        "Deck": []
    }

    blocks = soup.find_all('div', class_='col-12 col-md-6 mb-4')
    for block in blocks:
        title_el = block.find('h4')
        if not title_el:
            continue
            
        title = title_el.text.strip()
        rows = block.find_all('div', class_='row decklist-card-row')
        
        if title in ["Weapons", "Equipment"]:
            for row in rows:
                name_el = row.find('div', class_='col-9 decklist-card-name').find('a')
                qty_el = row.find('div', class_='col-3 text-right')
                if name_el and qty_el:
                    deck_data["Equipments"].append({name_el.text.strip(): qty_el.text.strip()})
        else:
            for row in rows:
                name_el = row.find('div', class_='col-9 decklist-card-name').find('a')
                qty_el = row.find('div', class_='col-3 text-right')
                if name_el and qty_el:
                    pitch = 0
                    pitch_span = row.find('span', class_='pitch-btn')
                    if pitch_span:
                        pitch_classes = pitch_span.get('class', [])
                        if 'pitch-1' in pitch_classes: pitch = 1
                        elif 'pitch-2' in pitch_classes: pitch = 2
                        elif 'pitch-3' in pitch_classes: pitch = 3

                    deck_data["Deck"].append({
                        "name": name_el.text.strip(),
                        "qty": qty_el.text.strip(),
                        "pitch": pitch
                    })

    # Libera ativamente a memória ocupada pela árvore do BeautifulSoup, prevenindo memory leaks em raspagens de longa duração
    soup.decompose()
    return deck_data

# Wrapper de execução para as threads: isola falhas individuais (evitando crash global) e aplica jitter (espera aleatória) para burlar rate limits
def update_task(link, deck_id, deck_name, session):
    try:
        deck = extract_decklist(link, deck_id, session)
        time.sleep(random.uniform(0.1, 0.3)) 
        return deck, deck_id, deck_name
    except Exception as e:
        return {"Deck ID": deck_id, "Erro": str(e)}, deck_id, deck_name

# Orquestrador multithread responsável pelo controle de fila de URLs, retomada de estado (resume) e persistência concorrente (I/O)
def update_detailed_decklists():
    output_path_dir = os.path.join(main_dir, 'scrap_output')
    csv_path = os.path.join(output_path_dir, 'decklists_fabtcg.csv')
    jsonl_path = os.path.join(output_path_dir, 'detailed_decklists.jsonl')

    session = requests.Session()
    session.headers.update(headers)
    df = pd.read_csv(csv_path)

    processed_ids = set()
    
    # Reconstrói o estado atual lendo o arquivo JSONL (Append-Only) para garantir que decks já processados sejam ignorados em caso de reinício
    if os.path.exists(jsonl_path):
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        d = json.loads(line)
                        if 'Deck ID' in d:
                            processed_ids.add(d['Deck ID'])
                    except json.JSONDecodeError:
                        continue
        print(f">>>Resuming extraction. {len(processed_ids)} decks have already been downloaded.")

    decks_to_update = []
    
    for row in df.itertuples():
        data = list(row)
        link = data[8]
        deck_id = data[10]
        deck_name = data[3]
        
        if link != "no_link" and deck_id not in processed_ids:
            decks_to_update.append((link, deck_id, deck_name))

    print(f">>>New decks to update: {len(decks_to_update)}")

    if not decks_to_update:
        print(">>>All detailed decklists are up to date.")
        return

    new_extracted = 0
    lock = threading.Lock()

    try:
        with open(jsonl_path, 'a', encoding='utf-8') as f:
            # Implementa concorrência via ThreadPoolExecutor para paralelizar requisições de I/O, acelerando drasticamente o download
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = {
                    executor.submit(update_task, link, deck_id, deck_name, session): deck_id 
                    for link, deck_id, deck_name in decks_to_update
                }

                for future in as_completed(futures):
                    deck_result, deck_id, deck_name = future.result()

                    # Garante Thread Safety (exclusão mútua): impede que duas threads escrevam no arquivo simultaneamente e corrompam a estrutura do JSON
                    with lock:
                        f.write(json.dumps(deck_result, ensure_ascii=False) + '\n')
                        processed_ids.add(deck_id)
                        new_extracted += 1
                        print(f"[{new_extracted}/{len(decks_to_update)}] Extracted: {deck_name}")

    except KeyboardInterrupt:
        print("\nInterrupted by the user! Ongoing threads will be canceled.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in the main loop: {e}")

    print(f"\nFinished! {new_extracted} New decks downloaded and saved securely.")

if __name__ == "__main__":
    update_detailed_decklists()