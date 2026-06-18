import os
import json
from datetime import datetime
import time
import requests

# Configuração de cabeçalhos (headers) para simular um navegador real e evitar bloqueios nas requisições web
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://google.com'
}

CLASSES_FAB = []
TALENTOS_FAB = []

# Define o caminho absoluto para o JSON de cartas voltando um nível (..) para a raiz do projeto
local_dir = os.path.dirname(os.path.abspath(__file__))
main_dir = os.path.abspath(os.path.join(local_dir, '..'))
json_path = os.path.join(main_dir, 'database_output', 'full_cards.json')

# Executa a geração dinâmica apenas se o banco de cartas já existir, evitando erros na primeira execução do projeto
if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        cards_data = json.load(f)
        
    classes_set = set()
    talentos_set = set()
    
    # Varre a base de dados para extrair Classes e Talentos automaticamente, garantindo que o código seja à prova de atualizações futuras do jogo
    for card in cards_data:
        types = card.get('types', [])
        
        if "Hero" in types:
            # Filtra os tipos estruturais que não compõem a Classe/Talento do Herói
            traits = [t for t in types if t not in ("Hero", "Demi-Hero")]
            
            if not traits:
                continue
                
            # Heurística de classificação: no jogo, a Classe é sempre a última palavra listada e os Talentos a precedem
            classes_set.add(traits[-1])
            
            if len(traits) > 1:
                for talento in traits[:-1]:
                    talentos_set.add(talento)
            
    # Converte os conjuntos (que garantem a unicidade dos dados) em listas ordenadas alfabeticamente
    CLASSES_FAB = sorted(list(classes_set))
    TALENTOS_FAB = sorted(list(talentos_set))
else:
    print(f"[AVISO UTILS] '{json_path}' não encontrado. As listas de Classes e Talentos estarão vazias.")
    
# Dicionário de Look-up table para padronização e limpeza de dados (Data Cleansing) referentes aos nomes dos eventos
EVENT_MAPPING = {
    "tc": "tc",
    "upf": "upf",
    "calling": "calling",
    "battle hardened": "battle hardened",
    "proquest": "pro quest",
    "pro quest": "pro quest",
    "road to nationals": "road to nationals",
    "sunday showdown": "sunday showdown",
    "skirmish": "skirmish",
    "national": "national",
    "silver age spotlight": "silver age spotlight",
    "world championship": "world championships",
    "pro tour": "pro tour",
    "dumpster": "dumpster dive",
    "dev download": "dev download",
    "10k": "Road to $10k",
    "zero to eighty": "zero to eighty",
    "celebrational": "celebrational",
    "store champions": "store champions",
    "smash palace": "smash palace",
    "cat footprints shilin armed cup": "cat footprints shilin armed cup",
    "the savage lands showdown": "the savage lands showdown",
    "commoner": "commoner",
    "hong kong regional championship": "hong kong regional championship",
    "bulk up": "bulk up",
    "primed to fight": "primed to fight",
    "masterclass": "masterclass",
    "world tour": "world tour",
    "BattleGrounds": "BattleGrounds"
}

# Verifica se o arquivo alvo já foi atualizado na data de hoje, evitando raspagens redundantes no site alvo
def file_is_updated(file_path: str):
    if not os.path.exists(file_path):
        return False
    
    mod_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
    current_date = datetime.now().date()
    
    return mod_date == current_date

# Função auxiliar para exclusão segura de arquivos, garantindo que o pipeline comece com arquivos limpos
def delete_file(file_path: str):
    if os.path.exists(file_path):
        os.remove(file_path)
    else:
        print(f"The file {file_path} does not exist.")

# Função resiliente para requisições web com lógica de retry, protegendo o pipeline contra oscilações de rede
def get_page(url: str, session: requests.Session):
    for attempt in range(3):
        try:
            response = session.get(url, timeout=10)

            if response.status_code == 200:
                return response
            
            print(f"Attempt {attempt + 1}: Status {response.status_code} in {url}")

        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} fail. Error: {e}")

        # Adiciona um pequeno intervalo antes de tentar novamente para não sobrecarregar o servidor
        time.sleep(2)
        
    return None