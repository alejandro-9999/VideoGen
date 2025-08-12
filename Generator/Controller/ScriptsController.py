# Generator/Controller/ScriptsController.py
from Generator.AiServices import AiScriptWriter
from Generator.Database.Manager import Manager


class ScriptsController:
    def __init__(self, db_manager: Manager, ai_script_service: AiScriptWriter):
        self.db_manager = db_manager
        self.ai_script_service = ai_script_service
        self.db_manager.clear_all_databases()
        self.db_manager.initialize_databases()

    def generate_scripts_for_news(self):
        # 1. Get news from the database
        with self.db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, text FROM news")
            news_items = cursor.fetchall()

        scripts = []
        # 2. Generate script for each news item
        for news_item in news_items:
            news_id, news_text = news_item
            script = self.ai_script_service.create_script(news_text)
            scripts.append((news_id, script.text))

        # 3. Save the scripts in the database
        with self.db_manager._get_connection() as conn:
            cursor = conn.cursor()
            for news_id, script_text in scripts:
                cursor.execute(
                    "INSERT INTO scripts (news_id, script) VALUES (?, ?)",
                    (news_id, script_text)
                )
            conn.commit()



