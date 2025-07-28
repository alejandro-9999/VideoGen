# core/pipeline.py
# ==============================================================================
# == ORQUESTADOR PRINCIPAL DEL PIPELINE DE NOTICIAS
# ==============================================================================

from datetime import datetime

from NewsProcessor import NewsDatabase
from services.database_manager import DatabaseManager
from services.ai_service import AIService
from modules.search.NewsFinder import NewsScraperFactory, NewsScraperManager
from modules.extraction.NewsContentExtractor import NewsContentExtractor


class NewsPipeline:
    def __init__(self, db_manager: DatabaseManager, ai_service: AIService, config: dict):
        self.db_manager = db_manager
        self.ai_service = ai_service
        self.config = config
        self.scraper_manager = NewsScraperManager()
        # Asegúrate que el extractor puede recibir el path de la BD del scraper
        self.content_extractor = NewsContentExtractor(db_path=config['SCRAPER_DB_PATH'])

    def _setup_scrapers(self, headless=True):
        """Configura los scrapers que se usarán en el gestor."""
        print("⚙️ Setting up scrapers...")
        self.scraper_manager.add_scraper("duckduckgo_api", NewsScraperFactory.create_scraper("duckduckgo_api"))
        self.scraper_manager.add_scraper("google", NewsScraperFactory.create_scraper("google", headless=headless))
        self.scraper_manager.add_scraper("duckduckgo",
                                         NewsScraperFactory.create_scraper("duckduckgo", headless=headless))
        self.scraper_manager.add_scraper("yahoo", NewsScraperFactory.create_scraper("duckduckgo", headless=headless))

        print("✅ Scrapers ready.")

    def _run_search_phase(self, query):
        """
        Fase 1: Búsqueda de noticias.
        Utiliza el gestor de base de datos central (self.db_manager) para
        registrar la búsqueda y guardar los resultados.
        """
        print("\n==== FASE 1: BÚSQUEDA DE NOTICIAS ====")

        # Se mantiene la mejora de la consulta con el servicio de IA
        improved_query_obj = self.ai_service.improve_search_query(query)
        improved_query = improved_query_obj.titulo_mejorado
        print(f"🔍 Búsqueda mejorada: '{improved_query}'")

        # --- INICIO DE LA CORRECCIÓN ---

        # 1. Se utiliza el gestor de base de datos centralizado (self.db_manager)
        #    para guardar la búsqueda. Esto asegura que se usa la conexión y
        #    el archivo de BD correctos (p. ej., 'raw_search_data.db').
        search_id = self.db_manager.save_search(
            improved_query,
            time_filter="w",
            max_results=self.config['EXTRACTION_LIMIT']
        )

        # La llamada al gestor de scrapers no cambia
        all_results = self.scraper_manager.search_all(
            improved_query,
            time_filter="w",
            max_results=self.config['EXTRACTION_LIMIT']
        )

        total_found = 0
        for engine, results in all_results.items():
            print(f"📰 {engine.capitalize()} encontró {len(results)} resultados.")
            if results:
                # 2. Se usa de nuevo self.db_manager para guardar los resultados de las noticias.
                self.db_manager.save_news_results(search_id, engine, results)
                total_found += len(results)

        # 3. (Opcional pero recomendado) Se obtiene el nombre de la BD del scraper
        #    desde el gestor para que el mensaje sea siempre preciso.
        scraper_db_path = self.db_manager.scraper_db
        print(
            f"💾 Total de {total_found} resultados guardados en '{scraper_db_path}' para la búsqueda ID {search_id}.")

        # --- FIN DE LA CORRECCIÓN ---

    def _run_extraction_phase(self):
        print("\n==== FASE 2: EXTRACCIÓN DE CONTENIDO ====")
        self.content_extractor.process_all_urls(
            limit=self.config['EXTRACTION_LIMIT'],
            max_workers=self.config['EXTRACTION_WORKERS']
        )

    def _ingest_extracted_news(self):
        print("\n==== FASE 3: INGESTA DE NOTICIAS CURADAS ====")
        articles = self.db_manager.get_extracted_articles_for_ingestion()
        for title, source, date, url, content in articles:
            self.db_manager.save_curated_news(title, source, date, url, content)
        print(f"✅ Ingesta completa. {len(articles)} artículos transferidos.")

    def _evaluate_all_news(self, target_search):
        print("\n==== FASE 4: EVALUACIÓN CON IA ====")
        news_list = self.db_manager.get_unevaluated_news()
        for id, title, content in news_list:
            news_dict = {"id": id, "titulo": title, "contenido": content}
            evaluation = self.ai_service.evaluate_news_article(news_dict, target_search)
            if evaluation.accion == "eliminar":
                self.db_manager.delete_news(id)
            else:
                self.db_manager.update_news_evaluation(id, evaluation.calificacion or 5)

    def _summarize_top_news(self):
        print("\n==== FASE 5: RESUMEN DE NOTICIAS DESTACADAS ====")
        articles = self.db_manager.get_top_rated_news(
            self.config['MIN_RATING_FOR_SUMMARY'],
            self.config['TOP_NEWS_LIMIT']
        )
        if not articles: return
        summary = self.ai_service.summarize_top_news(articles)
        print("\n🧠 Top noticias relevantes:\n", summary)

    def _generate_scripts(self):
        print("\n==== FASE 6: GENERACIÓN DE GUIONES ====")
        articles = self.db_manager.get_top_rated_news(
            self.config['MIN_RATING_FOR_SCRIPT'],
            self.config['TOP_NEWS_LIMIT']
        )
        for title, _, content in articles:
            script_obj = self.ai_service.generate_script_fragment(title, content)
            self.db_manager.save_script(title, script_obj.guion)
            print(f"   ✅ Guion guardado para: {title}")

    def run_complete_pipeline(self, search_query, target_search=None, clear_existing=True, headless_browser=True):
        if target_search is None:
            target_search = search_query

        # <<< CORRECCIÓN: Llamar a initialize_databases PRIMERO
        # Esto asegura que las tablas siempre existan antes de intentar limpiarlas.
        self.db_manager.initialize_databases()

        if clear_existing:
            self.db_manager.clear_all_databases()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🚀 Iniciando pipeline completo a las {timestamp}")
        print(f"🔎 Consulta: {search_query}")
        print(f"🎯 Objetivo de evaluación: {target_search}")

        # El resto del método sigue igual...
        self._setup_scrapers(headless=headless_browser)
        self._run_search_phase(search_query)
        self._run_extraction_phase()

        self._ingest_extracted_news()
        self._evaluate_all_news(target_search)
        self._summarize_top_news()
        self._generate_scripts()
        #
        self.scraper_manager.close_all()
        print("\n✅ Pipeline finalizado con éxito.")