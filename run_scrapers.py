import time

# Importa os módulos de extração garantindo que o orquestrador (Entry Point) permaneça desacoplado das regras de negócio do scraping
from scrapers.fab_decklists import create_decklists_csv
from scrapers.fab_decklists_detail import update_detailed_decklists
from scrapers.fab_ll import create_ll_csv
from scrapers.fab_ll_heroes import create_ll_heroes_csv
from scrapers.signature_weapons import create_weapons_csv

# Orquestrador principal (Pipeline Manager) responsável por acionar as rotinas de dados de forma sequencial e controlada
def run_all_scrapers():
    
    # Inicializa o monitoramento de performance para medir o tempo total de execução da esteira (Observabilidade)
    start_time = time.time()
    print("<================ STARTING FULL PIPELINE ================>\n")

    # Bloco de proteção global para garantir que falhas sistêmicas nos scrapers sejam capturadas, evitando crashs não tratados no servidor
    try:
        print("<======== 1. DECKLISTS ========>")
        create_decklists_csv()

        print("\n<======== 2. DETAILED DECKLISTS ========>")
        update_detailed_decklists()

        print("\n<======== 3. LIVING LEGENDS ========>")
        create_ll_csv()

        print("\n<======== 4. LIVING LEGENDS HEROES ========>")
        create_ll_heroes_csv()

        print("\n<======== 5. SIGNATURE WEAPONS ========>")
        create_weapons_csv()

    # Captura de erros críticos (Fail-safe): interrompe a pipeline de forma graciosa e fornece logs claros sobre o incidente
    except Exception as e:
        print(f"\n[CRITICAL ERROR] The pipeline was interrupted: {e}")

    # Bloco de execução garantida: calcula e exibe as métricas finais independentemente do sucesso ou falha da esteira
    finally:
        elapsed_time = time.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"\n<================ PIPELINE FINISHED IN {minutes}m {seconds}s ================>")


# Ponto de entrada oficial do projeto, impedindo que a pipeline seja disparada acidentalmente caso este arquivo seja importado por outro
if __name__ == "__main__":
    run_all_scrapers()