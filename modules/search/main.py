import sqlite3
import json
from pprint import pprint
from modules.search.NewsFinder import NewsScraperFactory, NewsScraperManager


class NewsDatabase:
    def __init__(self, db_path="news_search.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Inicializar la base de datos y crear las tablas necesarias"""
        with sqlite3.connect(self.db_path) as conn:
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

    def save_search(self, query, time_filter=None, max_results=None):
        """Guardar información de la búsqueda y retornar el ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO searches (query, time_filter, max_results)
                VALUES (?, ?, ?)
            ''', (query, time_filter, max_results))
            return cursor.lastrowid

    def save_news_results(self, search_id, engine, results):
        """Guardar los resultados de noticias"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for result in results:
                # Convertir el resultado a diccionario si tiene el método to_dict
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                else:
                    result_dict = result

                # Extraer campos comunes (ajusta según la estructura de tus resultados)
                title = result_dict.get('title', '')
                url = result_dict.get('url', '')
                description = result_dict.get('description', '') or result_dict.get('snippet', '')
                published_date = result_dict.get('published_date', '') or result_dict.get('date', '')
                source = result_dict.get('source', '')
                snippet = result_dict.get('snippet', '')

                # Guardar datos raw como JSON
                raw_data = json.dumps(result_dict, ensure_ascii=False)

                cursor.execute('''
                    INSERT INTO news_results 
                    (search_id, engine, title, url, description, published_date, source, snippet, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (search_id, engine, title, url, description, published_date, source, snippet, raw_data))

            conn.commit()

    def get_searches(self, limit=10):
        """Obtener búsquedas recientes"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, query, search_date, time_filter, max_results
                FROM searches
                ORDER BY search_date DESC
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()

    def get_search_results(self, search_id):
        """Obtener resultados de una búsqueda específica"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT engine, title, url, description, published_date, source, raw_data
                FROM news_results
                WHERE search_id = ?
                ORDER BY created_at
            ''', (search_id,))
            return cursor.fetchall()

    def search_by_query(self, query_pattern):
        """Buscar en la base de datos por patrón de consulta"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.query, s.search_date, COUNT(nr.id) as result_count
                FROM searches s
                LEFT JOIN news_results nr ON s.id = nr.search_id
                WHERE s.query LIKE ?
                GROUP BY s.id, s.query, s.search_date
                ORDER BY s.search_date DESC
            ''', (f'%{query_pattern}%',))
            return cursor.fetchall()


def main():
    # Inicializar base de datos
    db = NewsDatabase()

    # Crear instancia del gestor
    with NewsScraperManager() as manager:
        # Crear e incluir scrapers
        manager.add_scraper("google", NewsScraperFactory.create_scraper("google", headless=True))
        manager.add_scraper("yahoo", NewsScraperFactory.create_scraper("yahoo", headless=True))
        manager.add_scraper("duckduckgo", NewsScraperFactory.create_scraper("duckduckgo", headless=False))
        manager.add_scraper("duckduckgo_api", NewsScraperFactory.create_scraper("duckduckgo_api"))

        # Configurar búsqueda
        query = "Noticias sobre tecnologia nuclear"
        time_filter = "w"
        max_results = 10

        print(f"Realizando búsqueda: '{query}'")
        print(f"Filtro de tiempo: {time_filter}, Máx resultados: {max_results}")

        # Guardar información de la búsqueda
        search_id = db.save_search(query, time_filter, max_results)
        print(f"Búsqueda guardada con ID: {search_id}")

        # Buscar usando todos los motores
        all_results = manager.search_all(query, time_filter=time_filter, max_results=max_results)

        # Procesar y guardar resultados
        total_saved = 0
        for engine, results in all_results.items():
            print(f"\n=== Resultados de {engine.capitalize()} ===")
            print(f"Encontrados: {len(results)} resultados")

            if results:
                # Guardar en base de datos
                db.save_news_results(search_id, engine, results)
                total_saved += len(results)

                # Mostrar algunos resultados
                for i, r in enumerate(results[:3], 1):  # Mostrar solo los primeros 3
                    print(f"\n--- Resultado {i} ---")
                    pprint(r.to_dict())

                if len(results) > 3:
                    print(f"... y {len(results) - 3} resultados más")

        print(f"\n=== Resumen ===")
        print(f"Total de resultados guardados: {total_saved}")
        print(f"ID de búsqueda: {search_id}")
        print(f"Base de datos: {db.db_path}")


def show_database_stats():
    """Función auxiliar para mostrar estadísticas de la base de datos"""
    db = NewsDatabase()

    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()

        # Contar búsquedas
        cursor.execute("SELECT COUNT(*) FROM searches")
        search_count = cursor.fetchone()[0]

        # Contar resultados por motor
        cursor.execute('''
            SELECT engine, COUNT(*) as count
            FROM news_results
            GROUP BY engine
            ORDER BY count DESC
        ''')
        engine_stats = cursor.fetchall()

        # Búsquedas recientes
        cursor.execute('''
            SELECT query, search_date, COUNT(nr.id) as result_count
            FROM searches s
            LEFT JOIN news_results nr ON s.id = nr.search_id
            GROUP BY s.id, query, search_date
            ORDER BY search_date DESC
            LIMIT 5
        ''')
        recent_searches = cursor.fetchall()

    print(f"\n=== Estadísticas de la Base de Datos ===")
    print(f"Total de búsquedas realizadas: {search_count}")

    print(f"\nResultados por motor de búsqueda:")
    for engine, count in engine_stats:
        print(f"  {engine}: {count} resultados")

    print(f"\nBúsquedas recientes:")
    for query, date, count in recent_searches:
        print(f"  '{query}' ({date}) - {count} resultados")


if __name__ == "__main__":
    # Ejecutar búsqueda principal
    main()

    # Mostrar estadísticas
    show_database_stats()