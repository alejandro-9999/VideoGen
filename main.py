# main.py
# ==============================================================================
# == PUNTO DE ENTRADA PRINCIPAL PARA EJECUTAR EL PIPELINE
# ==============================================================================

# Importar configuraciones y componentes
import config
from services.database_manager import DatabaseManager
from services.ai_service import AIService
from core.pipeline import NewsPipeline


def main():
    """Configura e inicia el pipeline de procesamiento de noticias."""

    # 1. Crear instancias de los servicios
    db_manager = DatabaseManager(
        processor_db_path=config.PROCESSOR_DB_PATH,
        scraper_db_path=config.SCRAPER_DB_PATH
    )

    ai_service = AIService(model_name=config.OLLAMA_MODEL)

    # 2. Convertir el módulo de config en un diccionario para pasarlo fácilmente
    app_config = {key: getattr(config, key) for key in dir(config) if not key.startswith('__')}

    # 3. Inyectar los servicios y la configuración en el pipeline
    pipeline = NewsPipeline(
        db_manager=db_manager,
        ai_service=ai_service,
        config=app_config
    )

    # 4. Definir la consulta y ejecutar el pipeline
    query = "ultimas noticias sobre exploracion espacial y noticias de ciencia del espacio"

    pipeline.run_complete_pipeline(
        search_query=query,
        clear_existing=True,
        headless_browser=True
    )


if __name__ == "__main__":
    main()