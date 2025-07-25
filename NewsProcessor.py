import os
import sqlite3
import requests
import json
from datetime import datetime
import ollama

# --- Nuevas importaciones para Structured Output ---
from pydantic import BaseModel, Field, conint, ValidationError
from typing import Literal, Optional

# Importa las nuevas clases de tu sistema de scraping
# Asegúrate de que los archivos search/NewsFinder.py y extraction/NewsContentExtractor.py
# estén en la ruta correcta o que el proyecto esté configurado como un paquete.
from search.NewsFinder import NewsScraperFactory, NewsScraperManager
from extraction.NewsContentExtractor import NewsContentExtractor

# ==============================================================================
# == MODELOS PYDANTIC PARA LA SALIDA ESTRUCTURADA DE OLLAMA
# ==============================================================================

class ImprovedQuery(BaseModel):
    """Define la estructura para la consulta de búsqueda mejorada por la IA."""
    titulo_mejorado: str = Field(description="El título de búsqueda de noticias mejorado y optimizado.")

class NewsEvaluation(BaseModel):
    """Define la estructura para la evaluación de una noticia."""
    accion: Literal["mantener", "eliminar"] = Field(description="La acción a tomar con el artículo.")
    calificacion: Optional[conint(ge=1, le=10)] = Field(
        default=None,
        description="Calificación de relevancia de 1 a 10, solo si la acción es 'mantener'."
    )

class ScriptFragment(BaseModel):
    """Define la estructura para el guion generado por la IA."""
    guion: str = Field(description="Fragmento de guion corto, directo, en minúsculas y en un solo párrafo.")


# ==============================================================================
# == CLASE PRINCIPAL DEL PROCESADOR DE NOTICIAS
# ==============================================================================

class NewsProcessor:
    def __init__(self, processor_db="data.db", scraper_db="news_search.db", model="mistral"):
        self.processor_db_name = processor_db
        self.scraper_db_name = scraper_db
        self.model_name = model

        # Instancias de los nuevos componentes
        self.init_database()
        self.scraper_manager = NewsScraperManager()
        self.content_extractor = NewsContentExtractor(db_path=self.scraper_db_name)

        self._initialize_processor_database()


    def init_database(self):
        """Inicializar la base de datos y crear las tablas necesarias"""
        with sqlite3.connect(self.scraper_db_name) as conn:
            cursor = conn.cursor()
            # Tabla para búsquedas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    time_filter TEXT,
                    max_results INTEGER
                )
            ''')
            # Tabla para resultados de noticias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER,
                    engine TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    description TEXT,
                    published_date TEXT,
                    source TEXT,
                    snippet TEXT,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (search_id) REFERENCES searches (id)
                )
            ''')
            # Índices para mejorar rendimiento
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_query ON searches(query)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_engine ON news_results(engine)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_search_id ON news_results(search_id)')
            conn.commit()

    def _initialize_processor_database(self):
        """Inicializa la base de datos del procesador (contenido curado)."""
        conn = sqlite3.connect(self.processor_db_name)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS noticias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                fuente TEXT,
                fecha TEXT,
                url TEXT UNIQUE,
                contenido TEXT,
                calificacion INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                guion TEXT
            )
        """)
        conn.commit()
        conn.close()

    def clear_all_databases(self):
        """Limpia las tablas tanto en la base de datos del procesador como en la del scraper."""
        # Limpiar BD del procesador
        conn_proc = sqlite3.connect(self.processor_db_name)
        cursor_proc = conn_proc.cursor()
        cursor_proc.execute("DELETE FROM noticias")
        cursor_proc.execute("DELETE FROM scripts")
        conn_proc.commit()
        conn_proc.close()
        print(f"🧹 Tables in '{self.processor_db_name}' cleared.")

        # Limpiar BD del scraper/extractor
        conn_scrap = sqlite3.connect(self.scraper_db_name)
        cursor_scrap = conn_scrap.cursor()
        cursor_scrap.execute("DELETE FROM searches")
        cursor_scrap.execute("DELETE FROM news_results")
        # Asegúrate de que esta tabla exista o quita la línea si no es así
        if cursor_scrap.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extracted_content'").fetchone():
            cursor_scrap.execute("DELETE FROM extracted_content")
        conn_scrap.commit()
        conn_scrap.close()
        print(f"🧹 Tables in '{self.scraper_db_name}' cleared.")


    def _save_news_to_processor_db(self, titulo, fuente, fecha, url, contenido):
        """Guarda una noticia curada en la base de datos del procesador."""
        conn = sqlite3.connect(self.processor_db_name)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO noticias (titulo, fuente, fecha, url, contenido)
            VALUES (?, ?, ?, ?, ?)
        """, (titulo, fuente, fecha, url, contenido))
        conn.commit()
        conn.close()

    # --- MÉTODOS DE IA (ACTUALIZADOS CON PYDANTIC) ---
    def _improve_search_query(self, query: str) -> ImprovedQuery:
        """Mejora una consulta de búsqueda usando un modelo de lenguaje y salida estructurada."""
        prompt = f"""
        Mejora este título de búsqueda de noticias para que sea más efectivo y amplio: "{query}".
        Enfócate en términos que produzcan resultados de alta calidad y relevancia internacional, dando el resultado en español.
        """
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=ImprovedQuery.model_json_schema()
            )
            # Valida y parsea la respuesta usando el modelo Pydantic
            return ImprovedQuery.model_validate_json(response['message']['content'])
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            print(f"Error improving search query: {e}. Using original query.")
            return ImprovedQuery(titulo_mejorado=query)

    def _evaluate_news(self, noticia: dict, target_search: str) -> NewsEvaluation:
        """Evalúa la relevancia de una noticia usando un modelo de lenguaje y salida estructurada."""
        titulo = noticia.get("titulo", "")
        contenido = noticia.get("contenido", "")
        prompt = f"""
        Eres un analista de noticias. Evalúa la relevancia del siguiente artículo en relación con la búsqueda objetivo "{target_search}" y su importancia internacional.
        Título: "{titulo}"
        Contenido: "{contenido[:500]}..."

        Debes decidir si el artículo debe 'mantener' o 'eliminar'.
        Si el contenido es irrelevante, un listado/ranking, un error, un comunicado de prensa, o muy local, debe ser eliminado.
        Si es válido y relevante, asígnale una calificación de 1 (poco relevante) a 10 (muy relevante e importante).
        """
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=NewsEvaluation.model_json_schema()
            )
            # Valida y parsea la respuesta
            return NewsEvaluation.model_validate_json(response['message']['content'])
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            print(f"Error in evaluation: {e}. Defaulting to 'mantener' with rating 5.")
            return NewsEvaluation(accion="mantener", calificacion=5)

    def _generate_script(self, title: str, content: str) -> str:
        """Genera un guion a partir de una noticia usando un modelo de lenguaje y salida estructurada."""
        if not content or len(content) < 50:
            return "⚠️ Contenido insuficiente."

        prompt = f"""
        Genera un fragmento de guion para un video de noticias a partir de este artículo:
        Título: "{title}"
        Contenido: "{content}"

        El guion debe ser corto, directo, en minúsculas y en un solo párrafo.
        Es muy importante que reemplaces siglas como NASA por N A S A y unidades como km/h por kilómetros por hora para facilitar la locución.
        """
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                format=ScriptFragment.model_json_schema()
            )
            # Valida, parsea y extrae el guion
            script_obj = ScriptFragment.model_validate_json(response['message']['content'])
            return script_obj.guion
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            return f"Error al generar guion: {e}"

    # --- MÉTODOS DEL NUEVO PIPELINE (ACTUALIZADOS PARA USAR LOS NUEVOS MÉTODOS DE IA) ---

    def _setup_scrapers(self, headless=True):
        """Configura los scrapers que se usarán en el gestor."""
        print("⚙️ Setting up scrapers...")
        self.scraper_manager.add_scraper("duckduckgo_api", NewsScraperFactory.create_scraper("duckduckgo_api"))
        self.scraper_manager.add_scraper("google", NewsScraperFactory.create_scraper("google", headless=headless))
        self.scraper_manager.add_scraper("duckduckgo", NewsScraperFactory.create_scraper("duckduckgo", headless=headless))
        self.scraper_manager.add_scraper("yahoo", NewsScraperFactory.create_scraper("duckduckgo", headless=headless))


        print("✅ Scrapers ready.")

    def _run_search_phase(self, query, max_results=25):
        """Fase 1: Utiliza el NewsScraperManager para buscar noticias."""
        print(f"\n==== FASE 1: BÚSQUEDA DE NOTICIAS ====")
        
        # Obtenemos el objeto Pydantic y luego accedemos al atributo
        improved_query_obj = self._improve_search_query(query)
        improved_query = improved_query_obj.titulo_mejorado
        print(f"🔍 Búsqueda mejorada: '{improved_query}'")

        db = NewsDatabase(self.scraper_db_name)
        search_id = db.save_search(improved_query, time_filter="w", max_results=max_results)
        all_results = self.scraper_manager.search_all(improved_query, time_filter="w", max_results=max_results)

        total_found = 0
        for engine, results in all_results.items():
            print(f"📰 {engine.capitalize()} encontró {len(results)} resultados.")
            if results:
                db.save_news_results(search_id, engine, results)
                total_found += len(results)
        print(f"💾 Total de {total_found} resultados guardados en '{self.scraper_db_name}' para la búsqueda ID {search_id}.")

    def _run_extraction_phase(self, limit=50, max_workers=5):
        """Fase 2: Utiliza NewsContentExtractor para obtener el contenido completo."""
        print(f"\n==== FASE 2: EXTRACCIÓN DE CONTENIDO ====")
        self.content_extractor.process_all_urls(limit=limit, max_workers=max_workers)

    def _ingest_extracted_news(self):
        """Fase 3: Transfiere noticias extraídas con éxito a la BD del procesador."""
        print(f"\n==== FASE 3: INGESTA DE NOTICIAS CURADAS ====")
        conn = sqlite3.connect(self.scraper_db_name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                nr.title, nr.source, nr.published_date, ec.url, ec.content
            FROM extracted_content ec
            JOIN news_results nr ON ec.news_result_id = nr.id
            WHERE ec.success = 1 AND ec.word_count > 50
        """)
        articles_to_ingest = cursor.fetchall()
        conn.close()

        ingested_count = 0
        for title, source, date, url, content in articles_to_ingest:
            self._save_news_to_processor_db(title, source, date, url, content)
            ingested_count += 1
        print(f"✅ Ingesta completa. {ingested_count} artículos transferidos a '{self.processor_db_name}'.")

    def evaluate_all_news(self, target_search):
        """Fase 4: Evalúa todas las noticias en la BD del procesador."""
        print(f"\n==== FASE 4: EVALUACIÓN CON IA ====")
        conn = sqlite3.connect(self.processor_db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT id, titulo, contenido FROM noticias WHERE calificacion = 0")
        news_list = cursor.fetchall()

        print(f"📊 Evaluando {len(news_list)} noticias nuevas...")
        for id, titulo, contenido in news_list:
            news_dict = {"id": id, "titulo": titulo, "contenido": contenido}
            print(f"\n🔎 Evaluando ID {id}: {titulo[:80]}...")

            # _evaluate_news ahora devuelve un objeto NewsEvaluation
            evaluation = self._evaluate_news(news_dict, target_search)
            print(f"   Resultado: {evaluation.model_dump_json(indent=2)}") # Imprime el objeto validado

            # Accedemos a los atributos del objeto Pydantic
            if evaluation.accion == "eliminar":
                cursor.execute("DELETE FROM noticias WHERE id=?", (id,))
                print(f"   🗑️ Eliminado: ID {id}")
            else:
                # Usamos la calificación del objeto, con un fallback por si es None
                rating = evaluation.calificacion or 5
                cursor.execute("UPDATE noticias SET calificacion=? WHERE id=?", (rating, id))
                print(f"   ⭐ Calificado: ID {id} con {rating}")

        conn.commit()
        conn.close()

    def summarize_top_news(self, min_rating=8, limit=5):
        """Fase 5: Genera un resumen de las mejores noticias (sin cambios, no requiere salida estructurada)."""
        print(f"\n==== FASE 5: RESUMEN DE NOTICIAS DESTACADAS ====")
        conn = sqlite3.connect(self.processor_db_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT titulo, fuente, contenido FROM noticias WHERE calificacion >= ? ORDER BY calificacion DESC LIMIT ?",
            (min_rating, limit))
        articles = cursor.fetchall()
        conn.close()

        if not articles:
            print("⚠️ No hay artículos con suficiente calificación para resumir.")
            return

        resumenes = "\n---\n".join([f"Título: {t}\nFuente: {f}\nContenido: {c[:300]}..." for t, f, c in articles])
        prompt = f"Genera un resumen conciso de los puntos más importantes de estas noticias:\n{resumenes}"
        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            print("\n🧠 Top noticias relevantes:\n")
            print(response['message']['content'])
        except Exception as e:
            print(f"❌ Error al generar resumen: {e}")

    def generate_scripts(self, min_rating=9, limit=10):
        """Fase 6: Genera guiones para las noticias mejor calificadas."""
        print(f"\n==== FASE 6: GENERACIÓN DE GUIONES ====")
        conn = sqlite3.connect(self.processor_db_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT titulo, contenido FROM noticias WHERE calificacion >= ? ORDER BY calificacion DESC LIMIT ?",
            (min_rating, limit))
        articles = cursor.fetchall()
        conn.close()

        print(f"📖 Procesando {len(articles)} artículos para guion...")
        for title, content in articles:
            print(f"\n🎬 Generando guion para: {title}")
            # _generate_script ahora devuelve directamente el string del guion
            script = self._generate_script(title, content)
            
            if "Error" in script or "⚠️" in script:
                print(f"   {script}")
            else:
                conn_scripts = sqlite3.connect(self.processor_db_name)
                cursor_scripts = conn_scripts.cursor()
                cursor_scripts.execute("INSERT INTO scripts (titulo, guion) VALUES (?, ?)", (title, script))
                conn_scripts.commit()
                conn_scripts.close()
                print(f"   ✅ Guion guardado:\n   {script}")

    def run_complete_pipeline(self, search_query, target_search=None, clear_existing=True, headless_browser=True):
        if target_search is None:
            target_search = search_query

        if clear_existing:
            self.clear_all_databases()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🚀 Iniciando pipeline completo a las {timestamp}")
        print(f"🔎 Consulta: {search_query}")
        print(f"🎯 Objetivo de evaluación: {target_search}")

        self._setup_scrapers(headless=headless_browser)
        self._run_search_phase(search_query)
        self._run_extraction_phase()
        self._ingest_extracted_news()
        self.evaluate_all_news(target_search)
        self.summarize_top_news()
        self.generate_scripts()

        self.scraper_manager.close_all()
        print("\n✅ Pipeline finalizado con éxito.")

# --- Clases de soporte (sin cambios) ---
class NewsDatabase:
    """Clase de utilidad para interactuar con la BD del scraper."""
    def __init__(self, db_path="news_search.db"):
        self.db_path = db_path

    def save_search(self, query, time_filter=None, max_results=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO searches (query, time_filter, max_results) VALUES (?, ?, ?)',
                           (query, time_filter, max_results))
            conn.commit()
            return cursor.lastrowid

    def save_news_results(self, search_id, engine, results):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            news_data = []
            for result in results:
                result_dict = result.to_dict()
                news_data.append((
                    search_id, engine, result_dict.get('title'), result_dict.get('url'),
                    result_dict.get('snippet'), result_dict.get('date'),
                    result_dict.get('source'), result_dict.get('snippet')
                ))
            
            cursor.executemany('''
                INSERT OR IGNORE INTO news_results (search_id, engine, title, url, description, published_date, source, snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', news_data)
            conn.commit()


if __name__ == "__main__":
    # --- EJECUCIÓN DEL PIPELINE COMPLETO ---
    processor = NewsProcessor(
        processor_db="curated_news.db",
        scraper_db="raw_search_data.db",
        model="mistral"
    )

    query = "ultimas noticias sobre exploracion espacial y noticias de ciencia del espacio"


    processor.run_complete_pipeline(
        search_query=query,
        clear_existing=True,
        headless_browser=True
    )
