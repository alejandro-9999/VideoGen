# Generator/Database/Manager.py

import sqlite3

class Manager:

    def __init__(self, db_path: str):
        self.db_path = db_path
        print(f"DatabaseManager inicializado para operar en '{self.db_path}'")

    def _get_connection(self):
            return sqlite3.connect(self.db_path)

    def initialize_databases(self):
        """Crea todas las tablas necesarias en la base de datos si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
             ''')

            cursor.execute('''
                 CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER, -- Added this line to define the news_id column
                    script TEXT NOT NULL,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (news_id) REFERENCES news(id)
                )
             ''')

            conn.commit()
        print(f"✅ Esquema de base de datos en '{self.db_path}' asegurado.")


    def clear_all_databases(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            tables = ["scripts"]
            for table in tables:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                except sqlite3.OperationalError:
                    pass  # Table does not exist, ignore
                try:
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
                except sqlite3.OperationalError:
                    pass  # Sequence does not exist, ignore
            conn.commit()
        print(f"🧹 All tables in '{self.db_path}' have been cleared.")



    def save_scripts(self, scripts):
        with self._get_connection() as conn:
            news_data = [
                (r.news_id, r.script)
                for r in scripts
            ]
            conn.executemany('''
                INSERT OR IGNORE INTO news_results (news_id, script)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', news_data)
            conn.commit()

