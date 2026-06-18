import sqlite3
import json
import re
from datetime import datetime
import os

# Função utilitária de limpeza de dados: converte strings inconsistentes de datas para o formato ISO 8601 (YYYY-MM-DD), essencial para ordenação e filtros no banco de dados
def parse_date(date_str):
    if not date_str or date_str.strip() == '—': return None
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
    format_list = ['%B %d, %Y', '%b %d, %Y', '%d %b %Y', '%d %B %Y', '%d.%m.%y', '%m.%d.%y', '%d.%m.%Y', '%m.%d.%Y', '%Y-%m-%d']
    for fmt in format_list:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

# Normalizador de Strings: padroniza caracteres Unicode e símbolos visuais ('||' para '//') para garantir que o cruzamento de nomes (Matching) das cartas não falhe
def clean_card_name(raw_name):
    if not raw_name: return ""
    new_name = str(raw_name).replace("||", " // ")
    unicode_map = {
        "\\u014d": "ō", "u014d": "ō", "\\u0101": "ā", "u0101": "ā",
        "\\u1e63": "ṣ", "u1e63": "ṣ", "\\u00e9": "é", "u00e9": "é",
        "\\u00e0": "à", "u00e0": "à", "\\u00f0": "ð", "u00f0": "ð",
        "\\u00ed": "í", "u00ed": "í"
    }
    for incorrect, correct in unicode_map.items():
        new_name = new_name.replace(incorrect, correct)
    return new_name.strip()

# Mecanismo de Busca em Cache (In-Memory Lookup): cruza o nome limpo e o pitch da carta extraída do JSONL com o dicionário carregado do banco de dados
def search_card_id(clean_name, pitch_json, cards_map):
    name = clean_name.lower()
    name_normalized = name.replace(" ", "").replace(",", "").replace("'", "")

    if pitch_json in ["", " ", "0", 0]:
        pitch = 0
    else:
        try:
            pitch = int(pitch_json)
        except (ValueError, TypeError):
            pitch = None

    valid_pitch = [0, None] if pitch in [0, None] else [pitch]

    for p in valid_pitch:
        if (name, p) in cards_map:
            return cards_map[(name, p)]
        
    for (name_dict, pitch_dict), uid in cards_map.items():
        if pitch_dict in valid_pitch:
            dict_name_norm = name_dict.replace(" ", "").replace(",", "").replace("'", "")
            if dict_name_norm.startswith(name_normalized):
                return uid
            
    return None

# Orquestrador de ETL (Extract, Transform, Load): processa o JSONL de decklists de forma sequencial e modela os dados em formato relacional no SQLite
def build_decklists_db():
    print("<============= Iniciando construção do Banco de Decklists =============>")
    
    # Resolve caminhos absolutos dinamicamente para garantir a portabilidade do script independentemente do diretório de chamada
    local_dir = os.path.dirname(os.path.abspath(__file__))
    main_dir = os.path.abspath(os.path.join(local_dir, '..'))

    output_dir = os.path.join(main_dir, 'database_output')
    os.makedirs(output_dir, exist_ok=True)

    ORIGINAL_DB = os.path.join(output_dir, 'full_cards.db')
    NEW_DB = os.path.join(output_dir, 'fabtcg_decklists.db')
    JSONL_FILE = os.path.join(main_dir, 'scrap_output', 'detailed_decklists.jsonl')

    # Validação de Pré-requisitos (Sad Path): previne que o pipeline quebre de forma abrupta caso os arquivos dependentes ainda não existam
    if not os.path.exists(ORIGINAL_DB):
        print(f"[ERRO] O banco '{ORIGINAL_DB}' não foi encontrado. Execute o build_full_cards_database.py primeiro.")
        return
    if not os.path.exists(JSONL_FILE):
        print(f"[ERRO] O arquivo '{JSONL_FILE}' não foi encontrado. Execute as raspagens primeiro.")
        return

    conn = sqlite3.connect(NEW_DB)
    cursor = conn.cursor()
    
    # Garante a integridade referencial ao forçar o SQLite a respeitar e validar todas as restrições de Foreign Key (Chave Estrangeira) ativamente
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Migração Nativa (Zero-Copy): acopla o banco de cartas original e clona seu esquema para a tabela 'Cards' instantaneamente, mantendo a ordenação correta das colunas
    cursor.execute(f"ATTACH DATABASE '{ORIGINAL_DB}' AS old_db;")
    cursor.execute("SELECT sql FROM old_db.sqlite_master WHERE type='table' AND name='cards_main';")
    schema_original = cursor.fetchone()[0]
    schema_novo = schema_original.replace("CREATE TABLE cards_main", "CREATE TABLE IF NOT EXISTS Cards")
    cursor.execute(schema_novo)
    cursor.execute("INSERT OR IGNORE INTO Cards SELECT * FROM old_db.cards_main;")
    conn.commit()
    cursor.execute("DETACH DATABASE old_db;")

    # Criação do modelo dimensional: separa os dados lógicos em entidades (Player, Deck, Relação N:N) para reduzir redundância e otimizar queries futuras
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS Player (
        player_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        country TEXT
    );

    CREATE TABLE IF NOT EXISTS Deck (
        deck_id TEXT PRIMARY KEY,
        player_id TEXT,
        decklist_name TEXT,
        hero TEXT,
        event TEXT,
        format TEXT,
        position TEXT,
        event_date DATE,
        FOREIGN KEY (player_id) REFERENCES Player(player_id)
    );

    CREATE TABLE IF NOT EXISTS Deck_Card (
        deck_id TEXT,
        card_id TEXT,
        card_name TEXT,
        pitch INTEGER,
        quantity INTEGER,
        is_equipment BOOLEAN,
        PRIMARY KEY (deck_id, card_name, pitch),
        FOREIGN KEY (deck_id) REFERENCES Deck(deck_id),
        FOREIGN KEY (card_id) REFERENCES Cards(unique_id)
    );
    """)
    conn.commit()

    # Estratégia de Cache em Memória: carrega as chaves (UIDs) previamente para evitar o gargalo de consultas repetitivas de I/O no disco durante a transformação
    cursor.execute("SELECT unique_id, name, pitch FROM Cards")
    cards_map = {}
    for uid, name, pitch_db in cursor.fetchall():
        if name:
            try:
                pitch_val = int(pitch_db)
            except (ValueError, TypeError):
                pitch_val = None
            cards_map[(name.lower(), pitch_val)] = uid

    print("Processando decklists e inserindo no banco...")
    
    # Inicia a leitura do arquivo JSONL (Streaming de Dados) linha a linha, garantindo baixo consumo de RAM mesmo que o arquivo chegue a gigabytes
    with open(JSONL_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            d = json.loads(line)
            if 'Erro' in d or 'error' in d: continue
                
            deck_id = d.get('Deck ID')
            player_info = d.get('Player_info', {})
            player_name = player_info.get('name', 'Unknown')
            player_id = player_info.get('id', player_name) 
            info = d.get('Decklist_info', {})

            cursor.execute("INSERT OR IGNORE INTO Player (player_id, name, country) VALUES (?, ?, ?)", 
                           (player_id, player_name, player_info.get('country')))
            
            cursor.execute("""
                INSERT OR REPLACE INTO Deck (deck_id, player_id, decklist_name, hero, event, format, position, event_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (deck_id, player_id, d.get('Decklist_name'), d.get('Hero'), info.get('event'), info.get('format'), info.get('position'), parse_date(info.get('date'))))
            
            # Tratamento explícito para Equipamentos: insere pitch nulo (None) já que equipamentos no FAB não podem ser pitcheados para recursos
            for equip in d.get('Equipments', []):
                for raw_name, qty in equip.items():
                    clean_name = clean_card_name(raw_name)
                    card_id = search_card_id(clean_name, None, cards_map)
                    
                    safe_qty = int(qty) if qty else 1
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO Deck_Card (deck_id, card_id, card_name, pitch, quantity, is_equipment)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (deck_id, card_id, clean_name, None, safe_qty, True))
                    
            for card in d.get('Deck', []):
                raw_name = card.get('name')
                qty = card.get('qty')
                pitch = card.get('pitch')
                
                clean_name = clean_card_name(raw_name)
                card_id = search_card_id(clean_name, pitch, cards_map)
                
                # Resiliência de tipos (Type Safety): previne ValueError caso o scraper tenha capturado textos espúrios ou strings vazias do HTML
                safe_qty = int(qty) if str(qty).isdigit() else 1
                
                cursor.execute("""
                    INSERT OR REPLACE INTO Deck_Card (deck_id, card_id, card_name, pitch, quantity, is_equipment)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (deck_id, card_id, clean_name, pitch, safe_qty, False))

    # Transação Atômica Global: assegura que todas as inserções sejam consolidadas de uma só vez apenas quando o pipeline finalizar com sucesso
    conn.commit()
    conn.close()
    print(">>> Banco de dados fabtcg_decklists.db construído com sucesso!\n")

if __name__ == "__main__":
    build_decklists_db()