import os
import sqlite3
import requests
import json
from duckduckgo_search import DDGS
from newspaper import Article
from bs4 import BeautifulSoup
import ollama
from datetime import datetime


class NewsProcessor:
    def __init__(self, db_name="data.db", model="mistral"):
        self.db_name = db_name
        self.model_name = model
        self._initialize_database()

    def _initialize_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # Create tables if they don't exist
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

    def clear_tables(self):
        """Optionally clear tables before starting"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM noticias")
        cursor.execute("DELETE FROM scripts")
        print("🧹 Tables 'noticias' and 'scripts' cleared.")
        conn.commit()
        conn.close()

    def _save_news(self, titulo, fuente, fecha, url, contenido):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO noticias (titulo, fuente, fecha, url, contenido)
            VALUES (?, ?, ?, ?, ?)
        """, (titulo, fuente, fecha, url, contenido))
        conn.commit()
        conn.close()

    def _save_script(self, titulo, guion):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO scripts (titulo, guion) VALUES (?, ?)", (titulo, guion))
        conn.commit()
        conn.close()

    def _extract_content_newspaper(self, url):
        try:
            articulo = Article(url)
            articulo.download()
            articulo.parse()
            return articulo.text[:2000]
        except Exception as e:
            print(f"Newspaper extraction failed: {e}")
            return None

    def _extract_content_soup(self, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            respuesta = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(respuesta.text, "html.parser")
            parrafos = soup.find_all("p")
            contenido = " ".join([p.get_text() for p in parrafos[:10]])
            return contenido[:2000]
        except Exception as e:
            print(f"BeautifulSoup extraction failed: {e}")
            return "No se pudo extraer contenido"

    def _improve_search_query(self, query):
        prompt = f"""
        Mejora este título de búsqueda de noticias: "{query}".
        Devuelve la respuesta en formato JSON con dos claves:
        1. 'titulo_mejorado': El título mejorado para la búsqueda
        2. 'keywords': Una lista de 5-8 palabras clave relevantes que ayudarán a encontrar resultados más precisos
        Ejemplo de respuesta:
        {{
            "titulo_mejorado": "Últimas noticias sobre avances tecnológicos en exploración espacial",
            "keywords": ["NASA", "SpaceX", "telescopio espacial", "misión Mars", "astronomía", "satélites", "exoplanetas"]
        }}
        """
        try:
            respuesta = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            return json.loads(respuesta['message']['content'])
        except Exception as e:
            print(f"Error improving search query: {e}")
            return {"titulo_mejorado": query, "keywords": []}

    def _evaluate_news(self, noticia, target_search):
        titulo = noticia["titulo"]
        contenido = noticia["contenido"]
        fuente = noticia["fuente"]
        fecha = noticia["fecha"]
        prompt = f"""
        Eres un analista de noticias. Evalúa la relevancia del siguiente contenido con algun tipo de relacion con la búsqueda objetivo "{target_search}" y determina si se trata de una noticia de carácter internacional/global. También verifica si el artículo es una lista o ranking.
        Título: "{titulo}"
        Fuente: "{fuente}"
        Fecha: "{fecha}"
        Contenido: "{contenido}"
        Si el contenido tiene errores, es irrelevante, local o una lista/ranking, responde:
        {{ "accion": "eliminar" }}
        Si es válido, responde con:
        {{ "accion": "mantener", "calificacion": 1-10 }}
        """
        try:
            respuesta = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            return json.loads(respuesta['message']['content'])
        except Exception as e:
            print(f"Error in evaluation: {e}")
            return {"accion": "mantener", "calificacion": 5}

    def _generate_script(self, title, content):
        if not content or len(content) < 50:
            return "⚠️ Contenido insuficiente para generar un guion."
        prompt = f"""
        Genera un fragmento de guion para un video a partir del contenido de la siguiente noticia: "{content}".
        Devuelve un JSON con la clave 'guion'. No incluyas saludos, introducciones ni menciones a que es un video.
        El guion debe ser corto, directo, en minúsculas y en un solo párrafo.
        Además:
        - Si hay siglas (como NASA o ISS), sepáralas con espacios para que se lean letra por letra (ej. "I S S").
        - Si hay unidades como "cm", "km/h" o "kg", reemplázalas por su pronunciación completa en español ("centímetros", "kilómetros por hora", "kilogramos", etc).

        Ejemplo:
        {{
            "guion": "francia ha logrado un hito histórico al mantener el plasma activo por 22 minutos a cien millones de grados celsius..."
        }}
        """
        try:
            response = ollama.chat(model=self.model_name, messages=[{'role': 'user', 'content': prompt}])
            data = json.loads(response['message']['content'])
            return data.get("guion", "⚠️ Guion no encontrado en la respuesta.")
        except Exception as e:
            return f"Error al generar guion: {e}"

    def _evaluate_script_quality(self, title, script):
        prompt = f"""
        Evalúa el siguiente guion generado a partir de una noticia:
        Título: {title}
        Guion: "{script}"
        Verifica si tiene sentido, es coherente y está bien redactado.
        Si está bien: {{ "accion": "mantener" }}
        Si es mejorable: {{ "accion": "reescribir", "nuevo_guion": "..." }}
        Si no sirve: {{ "accion": "eliminar" }}
        """
        try:
            response = ollama.chat(model=self.model_name, messages=[{'role': 'user', 'content': prompt}])
            return json.loads(response['message']['content'])
        except Exception as e:
            print(f"❌ Error evaluando guion: {e}")
            return {"accion": "mantener"}

    def fetch_top_rated_news(self, min_rating=9, limit=25):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, titulo, contenido, fuente, fecha
            FROM noticias
            WHERE calificacion >= ?
            ORDER BY calificacion DESC
            LIMIT ?
        """, (min_rating, limit))
        articles = cursor.fetchall()
        conn.close()
        return articles

    def search_and_save_news(self, query, num_results=25):
        print(f"🔍 Searching for news about: {query}")
        improved = self._improve_search_query(query)
        improved_query = improved.get('titulo_mejorado', query)
        improved_query = f"{improved_query}"
        keywords = improved.get('keywords', [])
        keywords = ' intitle:'.join(keywords)
        print(f"📝 Improved query: {improved_query}")
        print(f"🔑 Keywords: {keywords}")
        with DDGS() as ddgs:
            results = list(
                ddgs.news(improved_query, safesearch="off", region="wt-wt", max_results=num_results, timelimit="w"))
        for news in results:
            url = news["url"]
            titulo = news["title"]
            fuente = news["source"]
            fecha = news["date"]
            print(f"\n🔍 Processing: {titulo}")
            print(f"🔗 URL: {url}")
            contenido = self._extract_content_newspaper(url)
            if not contenido:
                print("⚠️ Newspaper3k failed, trying BeautifulSoup...")
                contenido = self._extract_content_soup(url)
            print(f"📝 Content: {contenido[:100]}...")
            self._save_news(titulo, fuente, fecha, url, contenido)

    def evaluate_all_news(self, target_search):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT id, titulo, fuente, fecha, url, contenido FROM noticias")
        news_list = cursor.fetchall()
        print(f"📊 Evaluating {len(news_list)} news articles...")
        for news in news_list:
            id, titulo, fuente, fecha, url, contenido = news
            news_dict = {
                "id": id,
                "titulo": titulo,
                "fuente": fuente,
                "fecha": fecha,
                "url": url,
                "contenido": contenido
            }
            print(f"\nEvaluating news ID {id}: {titulo}")
            evaluation = self._evaluate_news(news_dict, target_search)
            print(f"Evaluation result: {evaluation}")
            if evaluation.get("accion") == "eliminar":
                cursor.execute("DELETE FROM noticias WHERE id=?", (id,))
                print(f"🗑️ Deleted: ID {id}")
            else:
                rating = evaluation.get("calificacion", 5)
                cursor.execute("UPDATE noticias SET calificacion=? WHERE id=?", (rating, id))
                print(f"⭐ Rated: ID {id} with {rating}")
            conn.commit()
        conn.close()

    def summarize_top_news(self, min_rating=8, limit=5):
        articles = self.fetch_top_rated_news(min_rating, limit)
        if not articles:
            print("⚠️ No hay artículos para resumir.")
            return
        resumenes = "\n".join([f"Título: {t}\nFuente: {f}\nFecha: {d}\nContenido: {c[:300]}..."
                               for _, t, c, f, d in articles])
        prompt = f"""
        A partir de las siguientes noticias, genera un resumen con los puntos más relevantes en formato de ranking (Top 5) basado en su relevancia internacional, evita incluir en el ranking noticias repetidas:
        {resumenes}
        Devuelve un texto con los 5 titulares más destacados y por qué son importantes.
        """
        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            resumen = response['message']['content']
            print("\n🧠 Top noticias relevantes:\n")
            print(resumen)
        except Exception as e:
            print(f"❌ Error al generar resumen: {e}")

    def generate_scripts(self, min_rating=9, limit=5):
        articles = self.fetch_top_rated_news(min_rating, limit)
        print(f"📖 Processing {len(articles)} articles with rating >= {min_rating}...")
        scripts_saved = 0
        for article_id, title, content, *_ in articles:
            print(f"🔍 Generating script for: {title}")
            script = self._generate_script(title, content)
            if script.startswith("Error") or script.startswith("⚠️"):
                print(script)
                continue
            evaluation = self._evaluate_script_quality(title, script)
            accion = evaluation.get("accion", "mantener")
            if accion == "mantener":
                self._save_script(title, script)
                scripts_saved += 1
                print(f"✅ Script saved: {title}")
                print(f"📜 Script:\n{script}\n{'=' * 80}")
            elif accion == "reescribir":
                nuevo_guion = evaluation.get("nuevo_guion", script)
                self._save_script(title, nuevo_guion)
                scripts_saved += 1
                print(f"✏️ Script reescrito: {title}")
                print(f"📜 Script:\n{nuevo_guion}\n{'=' * 80}")
            else:
                print(f"🗑️ Script descartado: {title}")
        print(f"📊 Done: {scripts_saved} scripts saved.")

    def run_complete_pipeline(self, search_query, target_search=None, clear_existing=True):
        if target_search is None:
            target_search = search_query

        if clear_existing:
            self.clear_tables()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🚀 Starting pipeline at {timestamp}")
        print(f"🔎 Query: {search_query}")
        print(f"🎯 Evaluation Target: {target_search}")

        print("\n==== STEP 1: SEARCH AND SAVE ====")
        self.search_and_save_news(search_query)

        print("\n==== STEP 2: EVALUATE NEWS ====")
        self.evaluate_all_news(target_search)

        print("\n==== STEP 3: TOP RELEVANT NEWS SUMMARY ====")
        self.summarize_top_news()

        print("\n==== STEP 4: GENERATE SCRIPTS ====")
        self.generate_scripts()

        print("\n✅ Pipeline finished successfully!")