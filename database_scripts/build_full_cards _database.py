import sqlite3
import requests
import json
import os

# Função orquestradora encapsulada para impedir execuções acidentais e manter a memória limpa ao finalizar o escopo
def build_cards_db():
    print("<============= Iniciando construção do Banco de Cartas =============>")
    
    # Resolve caminhos relativos de forma absoluta, garantindo a execução isolada ou via orquestrador principal
    local_dir = os.path.dirname(os.path.abspath(__file__))
    main_dir = os.path.abspath(os.path.join(local_dir, '..'))
    
    output_dir = os.path.join(main_dir, 'database_output')
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, 'full_cards.json')
    db_path = os.path.join(output_dir, 'full_cards.db')

    url_json_cards = "https://raw.githubusercontent.com/the-fab-cube/flesh-and-blood-cards/omens-of-the-third-age/json/english/card.json"

    # Adiciona timeout explícito para evitar que a thread trave indefinidamente caso a API do GitHub sofra instabilidades
    try:
        response = requests.get(url_json_cards, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Erro ao baixar o JSON: {e}")
        return

    cards_json = response.json()
    print(f"Transferência concluída! {len(cards_json)} cartas encontradas.")

    # Realiza cache local do JSON bruto para permitir auditoria de dados (Data Lineage) em caso de falha no parser
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(cards_json, f, ensure_ascii=False, indent=4)
    print("Cópia local JSON criada com sucesso!")

    main_keys_set = set()
    printings_keys_set = set()
    
    # Implementa Schema Drift Resilience: varre todo o payload dinamicamente para descobrir novas colunas sem precisar atualizar o código (Hardcode)
    for card in cards_json:
        for key in card.keys():
            if key != "printings":
                main_keys_set.add(key)
                
        printings = card.get('printings', [])
        for p in printings:
            printings_keys_set.update(p.keys())

    # Define a ordenação prioritária das colunas para melhorar a legibilidade e usabilidade (Quality of Life) de consultas por analistas
    priority_keys = ["unique_id", "name", "pitch", "types"]
    ordered_json_keys = []
    
    # Adiciona a chave primária artificial (internal_id) como primeira coluna estrutural da tabela
    main_sql_columns = ["internal_id INTEGER PRIMARY KEY AUTOINCREMENT"]
    
    # Constrói o schema SQL forçando as colunas prioritárias nas primeiras posições da tabela
    for key in priority_keys:
        if key in main_keys_set:
            ordered_json_keys.append(key)
            if key == "unique_id":
                main_sql_columns.append(f"{key} TEXT UNIQUE") # UNIQUE é obrigatório para referenciar como Foreign Key depois
            else:
                main_sql_columns.append(f"{key} TEXT")
                
    remaining_keys = [k for k in main_keys_set if k not in priority_keys]
    
    for key in remaining_keys:
        ordered_json_keys.append(key)
        main_sql_columns.append(f"{key} TEXT")

    printing_keys = list(printings_keys_set)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ativa restrições de chave estrangeira no SQLite para garantir a integridade referencial entre a carta e seus printings (relacionamento 1:N)
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute('DROP TABLE IF EXISTS cards_printings')
    cursor.execute('DROP TABLE IF EXISTS cards_main')

    query_create_main = f"CREATE TABLE cards_main ({', '.join(main_sql_columns)})"
    cursor.execute(query_create_main)

    columns_printings_sql = [
        "internal_id INTEGER PRIMARY KEY AUTOINCREMENT",
        "card_unique_id TEXT",                            
    ]
    for key in printing_keys:
        columns_printings_sql.append(f"{key} TEXT")
    columns_printings_sql.append("FOREIGN KEY(card_unique_id) REFERENCES cards_main(unique_id)")

    query_create_printings = f"CREATE TABLE cards_printings ({', '.join(columns_printings_sql)})"
    cursor.execute(query_create_printings)

    # Utiliza binding parameters (?) para prevenir falhas de sintaxe e escapar aspas simples/duplas presentes nos nomes das cartas
    placeholders_main = ', '.join(['?'] * len(ordered_json_keys))
    query_insert_main = f"INSERT INTO cards_main ({', '.join(ordered_json_keys)}) VALUES ({placeholders_main})"

    columns_printings_insert = ['card_unique_id'] + printing_keys
    placeholders_printings = ', '.join(['?'] * len(columns_printings_insert))
    query_insert_printings = f"INSERT INTO cards_printings ({', '.join(columns_printings_insert)}) VALUES ({placeholders_printings})"

    for card in cards_json:
        main_values = []
        for key in ordered_json_keys:
            value = card.get(key)
            # Serializa dicionários ou listas aninhadas em texto, pois o SQLite não possui suporte nativo para tipos complexos (Arrays/JSON)
            if isinstance(value, (list, dict)):
                main_values.append(json.dumps(value, ensure_ascii=False))
            else:
                main_values.append(value)
                
        cursor.execute(query_insert_main, main_values)
        
        card_id = card.get('unique_id')
        printings = card.get('printings', [])
        
        for p in printings:
            values_printings = [card_id]
            for key in printing_keys:
                value = p.get(key)
                if isinstance(value, (list, dict)):
                    values_printings.append(json.dumps(value, ensure_ascii=False))
                else:
                    values_printings.append(value)
                    
            cursor.execute(query_insert_printings, values_printings)

    # Efetua o commit atômico no final do loop para garantir que o banco não receba dados parciais em caso de interrupção inesperada
    conn.commit()
    conn.close()
    print(">>> Banco de dados full_cards.db construído com sucesso!\n")

if __name__ == "__main__":
    build_cards_db()