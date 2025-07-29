# services/database_manager.py
# ==============================================================================
# == GESTOR CENTRALIZADO DE LA BASE DE DATOS ÚNICA
# ==============================================================================

import sqlite3
import json

class DatabaseManager:
    """Gestiona todas las operaciones de la base de datos única del pipeline."""

    # CAMBIO: El constructor ahora solo necesita una ruta de base de datos.
    def __init__(self, db_path: str):
        self.db_path = db_path
        print(f"DatabaseManager inicializado para operar en '{self.db_path}'")

    def _get_connection(self):
        """Devuelve una conexión a la base de datos única."""
        return sqlite3.connect(self.db_path)

    # CAMBIO: Este método ahora crea TODAS las tablas en la misma base de datos.
    def initialize_databases(self):
        """Crea todas las tablas necesarias en la base de datos si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Tabla de búsquedas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    time_filter TEXT,
                    max_results INTEGER
                )
            ''')
            # Tabla de resultados de noticias (crudo)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER,
                    engine TEXT NOT NULL,
                    title TEXT,
                    url TEXT UNIQUE,
                    snippet TEXT,
                    date TEXT,
                    source TEXT,
                    raw_data TEXT,
                    FOREIGN KEY (search_id) REFERENCES searches (id)
                )
            ''')
            # Tabla de contenido extraído
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS extracted_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_result_id INTEGER UNIQUE,
                    url TEXT,
                    title TEXT,
                    content TEXT,
                    author TEXT,
                    publish_date TEXT,
                    method_used TEXT,
                    word_count INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    extraction_time REAL,
                    FOREIGN KEY (news_result_id) REFERENCES news_results(id)
                )
            ''')
            # Tabla de noticias curadas y evaluadas
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
            # Tabla para los guiones generados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT UNIQUE,
                    guion TEXT
                )
            """)
            conn.commit()
        print(f"✅ Esquema de base de datos en '{self.db_path}' asegurado.")

    # CAMBIO: Limpia todas las tablas de la base de datos única.
    def clear_all_databases(self):
        """Limpia todas las tablas en la base de datos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            tables = ["searches", "news_results", "extracted_content", "noticias", "scripts"]
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'") # Resetea autoincrement
            conn.commit()
        print(f"🧹 Todas las tablas en '{self.db_path}' han sido limpiadas.")

    # --- Métodos de escritura y lectura (adaptados a la conexión única) ---

    def save_search(self, query, time_filter=None, max_results=None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO searches (query, time_filter, max_results) VALUES (?, ?, ?)',
                           (query, time_filter, max_results))
            conn.commit()
            return cursor.lastrowid

    def save_news_results(self, search_id, engine, results):
        with self._get_connection() as conn:
            news_data = [
                (search_id, engine, r.title, r.url, r.snippet, r.date, r.source, json.dumps(r.to_dict()))
                for r in results
            ]
            conn.executemany('''
                INSERT OR IGNORE INTO news_results (search_id, engine, title, url, snippet, date, source, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', news_data)
            conn.commit()

    def get_extracted_articles_for_ingestion(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT nr.title, nr.source, nr.date, ec.url, ec.content
                FROM extracted_content ec
                JOIN news_results nr ON ec.news_result_id = nr.id
                WHERE ec.success = 1 AND ec.word_count > 50
            """)
            return cursor.fetchall()

    def save_curated_news(self, title, source, date, url, content):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO noticias (titulo, fuente, fecha, url, contenido, calificacion)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (title, source, date, url, content))
            conn.commit()

    def get_unevaluated_news(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT id, titulo, contenido FROM noticias WHERE calificacion = 0").fetchall()

    def update_news_evaluation(self, news_id, rating):
        with self._get_connection() as conn:
            conn.execute("UPDATE noticias SET calificacion=? WHERE id=?", (rating, news_id))
            conn.commit()

    def delete_news(self, news_id):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM noticias WHERE id=?", (news_id,))
            conn.commit()

    def get_top_rated_news(self, min_rating, limit):
        with self._get_connection() as conn:
            return conn.execute(
                "SELECT titulo, fuente, contenido FROM noticias WHERE calificacion >= ? ORDER BY calificacion DESC LIMIT ?",
                (min_rating, limit)
            ).fetchall()

    def save_script(self, title, script):
        with self._get_connection() as conn:
            # Usamos INSERT OR REPLACE para actualizar el guion si ya existe uno para ese título.
            conn.execute("INSERT OR REPLACE INTO scripts (titulo, guion) VALUES (?, ?)", (title, script))
            conn.commit()