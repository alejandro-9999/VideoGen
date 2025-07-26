# services/database_manager.py
# ==============================================================================
# == GESTOR CENTRALIZADO DE BASES DE DATOS
# ==============================================================================

import sqlite3
import json

class DatabaseManager:
    """Gestiona todas las operaciones de las bases de datos del scraper y del procesador."""

    def __init__(self, processor_db_path, scraper_db_path):
        self.processor_db = processor_db_path
        self.scraper_db = scraper_db_path

    def _get_proc_conn(self):
        return sqlite3.connect(self.processor_db)

    def _get_scrap_conn(self):
        return sqlite3.connect(self.scraper_db)

    def initialize_databases(self):
        """Crea todas las tablas necesarias en ambas bases de datos si no existen."""
        # --- Inicializar BD del Procesador (curated_news.db) ---
        with self._get_proc_conn() as conn:
            cursor = conn.cursor()
            # <<< CORRECCIÓN: DDL completo para la BD del procesador
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
        print(f"Base de datos del procesador '{self.processor_db}' inicializada.")

        # --- Inicializar BD del Scraper (raw_search_data.db) ---
        with self._get_scrap_conn() as conn:
            cursor = conn.cursor()
            # <<< CORRECCIÓN: DDL completo para la BD del scraper
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    time_filter TEXT,
                    max_results INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER,
                    engine TEXT NOT NULL,
                    title TEXT,
                    url TEXT UNIQUE,
                    description TEXT,
                    published_date TEXT,
                    source TEXT,
                    snippet TEXT,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (search_id) REFERENCES searches (id)
                )
            ''')
            # Es buena práctica también tener la tabla de contenido extraído aquí
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS extracted_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_result_id INTEGER UNIQUE,
                    url TEXT,
                    content TEXT,
                    word_count INTEGER,
                    success BOOLEAN,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (news_result_id) REFERENCES news_results(id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_query ON searches(query)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_url ON news_results(url)')
            conn.commit()
        print(f"Base de datos de scraper '{self.scraper_db}' inicializada.")

    def clear_all_databases(self):
        """Limpia todas las tablas en ambas bases de datos."""
        # Se asume que initialize_databases() ya fue llamado
        with self._get_proc_conn() as conn:
            conn.execute("DELETE FROM noticias")
            conn.execute("DELETE FROM scripts")
            conn.commit()
        print(f"🧹 Tablas en '{self.processor_db}' limpiadas.")

        with self._get_scrap_conn() as conn:
            conn.execute("DELETE FROM searches")
            conn.execute("DELETE FROM news_results")
            conn.execute("DELETE FROM extracted_content")
            conn.commit()
        print(f"🧹 Tablas en '{self.scraper_db}' limpiadas.")

    # --- Métodos para la BD del Procesador (curated_news.db) ---

    def save_curated_news(self, title, source, date, url, content):
        with self._get_proc_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO noticias (titulo, fuente, fecha, url, contenido, calificacion)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (title, source, date, url, content))
            conn.commit()

    def get_unevaluated_news(self):
        with self._get_proc_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, titulo, contenido FROM noticias WHERE calificacion = 0")
            return cursor.fetchall()

    def update_news_evaluation(self, news_id, rating):
        with self._get_proc_conn() as conn:
            conn.execute("UPDATE noticias SET calificacion=? WHERE id=?", (rating, news_id))
            conn.commit()

    def delete_news(self, news_id):
        with self._get_proc_conn() as conn:
            conn.execute("DELETE FROM noticias WHERE id=?", (news_id,))
            conn.commit()

    def get_top_rated_news(self, min_rating, limit):
        with self._get_proc_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT titulo, fuente, contenido FROM noticias WHERE calificacion >= ? ORDER BY calificacion DESC LIMIT ?",
                (min_rating, limit)
            )
            return cursor.fetchall()

    def save_script(self, title, script):
        with self._get_proc_conn() as conn:
            conn.execute("INSERT INTO scripts (titulo, guion) VALUES (?, ?)", (title, script))
            conn.commit()

    # --- Métodos para la BD del Scraper (raw_search_data.db) ---

    def save_search(self, query, time_filter=None, max_results=None):
        with self._get_scrap_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO searches (query, time_filter, max_results) VALUES (?, ?, ?)',
                           (query, time_filter, max_results))
            conn.commit()
            return cursor.lastrowid

    def save_news_results(self, search_id, engine, results):
        with self._get_scrap_conn() as conn:
            news_data = []
            for result in results:
                result_dict = result.to_dict()
                news_data.append((
                    search_id, engine, result_dict.get('title'), result_dict.get('url'),
                    result_dict.get('snippet'), result_dict.get('date'),
                    result_dict.get('source'), json.dumps(result_dict)
                ))
            cursor = conn.cursor()
            cursor.executemany('''
                INSERT OR IGNORE INTO news_results (search_id, engine, title, url, description, published_date, source, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', news_data)
            conn.commit()

    def get_extracted_articles_for_ingestion(self):
        with self._get_scrap_conn() as conn:
            cursor = conn.cursor()
            # Asegúrate de que esta consulta coincide con los nombres de tus tablas y columnas
            cursor.execute("""
                SELECT nr.title, nr.source, nr.published_date, ec.url, ec.content
                FROM extracted_content ec
                JOIN news_results nr ON ec.news_result_id = nr.id
                WHERE ec.success = 1 AND ec.word_count > 50
            """)
            return cursor.fetchall()