import sqlite3
import requests
import time
import json
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Librerías para web scraping
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# Librerías para parsing HTML
from bs4 import BeautifulSoup, Comment
import readability
from newspaper import Article
import trafilatura


@dataclass
class ExtractedContent:
    url: str
    title: str
    content: str
    author: str
    publish_date: str
    method_used: str
    success: bool
    error_message: str = ""
    word_count: int = 0
    extraction_time: float = 0.0


class NewsContentExtractor:
    def __init__(self, db_path="news_search.db", headless=True, timeout=30):
        self.db_path = db_path
        self.headless = headless
        self.timeout = timeout
        self.init_database()

        # Headers para requests HTTP
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        # Selectores CSS comunes para contenido principal
        self.content_selectors = [
            'article', '[role="main"]', '.article-content', '.post-content',
            '.entry-content', '.content', '.article-body', '.story-body',
            '.news-content', '.article-text', '.post-body', '.main-content',
            '.article-content-body', '.story-content', '.content-body'
        ]

        # Selectores para eliminar elementos no deseados
        self.remove_selectors = [
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            '.advertisement', '.ads', '.social-share', '.comments',
            '.related-articles', '.sidebar', '.popup', '.modal',
            '.cookie-banner', '.newsletter-signup', '.subscription',
            '[class*="cookie"]', '[id*="cookie"]', '[class*="gdpr"]',
            '[class*="consent"]', '[id*="consent"]', '.floating-bar'
        ]

    def init_database(self):
        """Inicializar tabla para contenido extraído"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS extracted_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_result_id INTEGER,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    author TEXT,
                    publish_date TEXT,
                    method_used TEXT,
                    word_count INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    extraction_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (news_result_id) REFERENCES news_results (id)
                )
            ''')
            conn.commit()

    def get_unprocessed_urls(self, limit=None) -> List[Tuple[int, str]]:
        """Obtener URLs que no han sido procesadas"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = '''
                SELECT nr.id, nr.url
                FROM news_results nr
                LEFT JOIN extracted_content ec ON nr.id = ec.news_result_id
                WHERE nr.url IS NOT NULL 
                AND nr.url != ''
                AND ec.id IS NULL
            '''
            if limit:
                query += f' LIMIT {limit}'

            cursor.execute(query)
            return cursor.fetchall()

    def create_selenium_driver(self) -> webdriver.Chrome:
        """Crear driver de Selenium con configuración anti-detección"""
        options = Options()
        if self.headless:
            options.add_argument('--headless')

        # Opciones anti-detección y rendimiento
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')  # Para evitar modales JS
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        # Bloquear recursos innecesarios
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.managed_default_content_settings.media_stream': 2,
            'profile.managed_default_content_settings.popups': 2,
            'profile.managed_default_content_settings.notifications': 2
        }
        options.add_experimental_option('prefs', prefs)

        return webdriver.Chrome(options=options)

    def extract_with_requests_bs4(self, url: str) -> ExtractedContent:
        """Método 1: Requests + BeautifulSoup (más rápido)"""
        start_time = time.time()
        try:
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(url, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Eliminar elementos no deseados
            for selector in self.remove_selectors:
                for element in soup.select(selector):
                    element.decompose()

            # Extraer contenido principal
            content = ""
            title = ""

            # Intentar extraer título
            title_tags = soup.find_all(['h1', 'title'])
            if title_tags:
                title = title_tags[0].get_text().strip()

            # Intentar extraer contenido principal
            for selector in self.content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    break

            # Si no encuentra contenido específico, usar el body completo
            if not content:
                body = soup.find('body')
                if body:
                    content = body.get_text().strip()

            # Limpiar contenido
            content = self.clean_text(content)

            return ExtractedContent(
                url=url,
                title=title,
                content=content,
                author="",
                publish_date="",
                method_used="requests_bs4",
                success=bool(content),
                word_count=len(content.split()),
                extraction_time=time.time() - start_time
            )

        except Exception as e:
            return ExtractedContent(
                url=url, title="", content="", author="", publish_date="",
                method_used="requests_bs4", success=False,
                error_message=str(e), extraction_time=time.time() - start_time
            )

    def extract_with_newspaper(self, url: str) -> ExtractedContent:
        """Método 2: Newspaper3k (mejor para artículos de noticias)"""
        start_time = time.time()
        try:
            article = Article(url)
            article.download()
            article.parse()

            return ExtractedContent(
                url=url,
                title=article.title or "",
                content=self.clean_text(article.text or ""),
                author=", ".join(article.authors) if article.authors else "",
                publish_date=str(article.publish_date) if article.publish_date else "",
                method_used="newspaper3k",
                success=bool(article.text),
                word_count=len(article.text.split()) if article.text else 0,
                extraction_time=time.time() - start_time
            )

        except Exception as e:
            return ExtractedContent(
                url=url, title="", content="", author="", publish_date="",
                method_used="newspaper3k", success=False,
                error_message=str(e), extraction_time=time.time() - start_time
            )

    def extract_with_trafilatura(self, url: str) -> ExtractedContent:
        """Método 3: Trafilatura (excelente para contenido limpio)"""
        start_time = time.time()
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                raise Exception("No se pudo descargar la página")

            content = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            title = trafilatura.extract_metadata(downloaded).title if trafilatura.extract_metadata(downloaded) else ""

            return ExtractedContent(
                url=url,
                title=title or "",
                content=self.clean_text(content or ""),
                author="",
                publish_date="",
                method_used="trafilatura",
                success=bool(content),
                word_count=len(content.split()) if content else 0,
                extraction_time=time.time() - start_time
            )

        except Exception as e:
            return ExtractedContent(
                url=url, title="", content="", author="", publish_date="",
                method_used="trafilatura", success=False,
                error_message=str(e), extraction_time=time.time() - start_time
            )

    def extract_with_selenium(self, url: str) -> ExtractedContent:
        """Método 4: Selenium (para sitios con mucho JavaScript)"""
        start_time = time.time()
        driver = None
        try:
            driver = self.create_selenium_driver()
            driver.set_page_load_timeout(self.timeout)

            # Cargar página
            driver.get(url)

            # Esperar a que cargue el contenido
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Cerrar modales de cookies si existen
            self.close_cookie_modals(driver)

            # Obtener HTML procesado
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Eliminar elementos no deseados
            for selector in self.remove_selectors:
                for element in soup.select(selector):
                    element.decompose()

            # Extraer contenido
            content = ""
            title = ""

            # Título
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                title = title_elem.get_text().strip()

            # Contenido principal
            for selector in self.content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    break

            if not content:
                body = soup.find('body')
                if body:
                    content = body.get_text().strip()

            content = self.clean_text(content)

            return ExtractedContent(
                url=url,
                title=title,
                content=content,
                author="",
                publish_date="",
                method_used="selenium",
                success=bool(content),
                word_count=len(content.split()),
                extraction_time=time.time() - start_time
            )

        except Exception as e:
            return ExtractedContent(
                url=url, title="", content="", author="", publish_date="",
                method_used="selenium", success=False,
                error_message=str(e), extraction_time=time.time() - start_time
            )
        finally:
            if driver:
                driver.quit()

    def close_cookie_modals(self, driver):
        """Cerrar modales de cookies y consentimiento"""
        cookie_selectors = [
            '[class*="cookie"] button',
            '[class*="consent"] button',
            '[id*="cookie"] button',
            '[id*="consent"] button',
            '.cookie-accept',
            '.accept-cookies',
            '.gdpr-accept',
            'button[onclick*="cookie"]',
            'button[onclick*="consent"]'
        ]

        for selector in cookie_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for button in buttons:
                    if button.is_displayed() and button.is_enabled():
                        if any(word in button.text.lower() for word in
                               ['aceptar', 'accept', 'ok', 'continuar', 'continue']):
                            button.click()
                            time.sleep(1)
                            break
            except:
                continue

    def extract_with_multiple_methods(self, news_id: int, url: str) -> ExtractedContent:
        """Intentar extracción con múltiples métodos hasta encontrar contenido"""
        methods = [
            self.extract_with_newspaper,
            self.extract_with_trafilatura,
            self.extract_with_requests_bs4,
            self.extract_with_selenium
        ]

        best_result = None
        max_words = 0

        for method in methods:
            try:
                result = method(url)

                # Si es exitoso y tiene más contenido, es mejor
                if result.success and result.word_count > max_words:
                    best_result = result
                    max_words = result.word_count

                    # Si encontramos contenido sustancial, no necesitamos más métodos
                    if result.word_count > 100:
                        break

            except Exception as e:
                print(f"Error con método {method.__name__}: {e}")
                continue

        # Si no encontramos nada bueno, devolver el último resultado
        if not best_result:
            best_result = ExtractedContent(
                url=url, title="", content="", author="", publish_date="",
                method_used="all_failed", success=False,
                error_message="Todos los métodos fallaron"
            )

        return best_result

    def clean_text(self, text: str) -> str:
        """Limpiar texto extraído"""
        if not text:
            return ""

        # Eliminar espacios excesivos
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)

        # Eliminar texto de cookies común
        cookie_patterns = [
            r'(acepto|accept).{0,50}(cookies?|política|privacidad)',
            r'este sitio.{0,50}cookies?',
            r'utilizamos cookies?',
            r'política de privacidad',
            r'términos y condiciones'
        ]

        for pattern in cookie_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    def save_extracted_content(self, news_id: int, content: ExtractedContent):
        """Guardar contenido extraído en la base de datos"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO extracted_content 
                (news_result_id, url, title, content, author, publish_date, 
                 method_used, word_count, success, error_message, extraction_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                news_id, content.url, content.title, content.content,
                content.author, content.publish_date, content.method_used,
                content.word_count, content.success, content.error_message,
                content.extraction_time
            ))
            conn.commit()

    def process_single_url(self, news_id: int, url: str) -> ExtractedContent:
        """Procesar una sola URL"""
        print(f"Procesando: {url}")
        result = self.extract_with_multiple_methods(news_id, url)
        self.save_extracted_content(news_id, result)

        status = "✓" if result.success else "✗"
        print(f"{status} {result.method_used} - {result.word_count} palabras - {result.extraction_time:.2f}s")

        return result

    def process_all_urls(self, max_workers=3, limit=None):

        """Procesar todas las URLs pendientes con threading"""
        urls = self.get_unprocessed_urls(limit)

        if not urls:
            print("No hay URLs pendientes para procesar")
            return

        print(f"Procesando {len(urls)} URLs con {max_workers} workers...")

        success_count = 0
        total_words = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Enviar tareas
            future_to_url = {
                executor.submit(self.process_single_url, news_id, url): (news_id, url)
                for news_id, url in urls
            }

            # Procesar resultados
            for future in as_completed(future_to_url):
                news_id, url = future_to_url[future]
                try:
                    result = future.result()
                    if result.success:
                        success_count += 1
                        total_words += result.word_count
                except Exception as e:
                    print(f"Error procesando {url}: {e}")

        print(f"\n=== Resumen de Extracción ===")
        print(f"URLs procesadas: {len(urls)}")
        print(f"Extracciones exitosas: {success_count}")
        print(f"Tasa de éxito: {success_count / len(urls) * 100:.1f}%")
        print(f"Total de palabras extraídas: {total_words:,}")

    def get_extraction_stats(self):
        """Obtener estadísticas de extracción"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Estadísticas generales
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(word_count) as total_words,
                    AVG(extraction_time) as avg_time
                FROM extracted_content
            ''')
            stats = cursor.fetchone()

            # Por método
            cursor.execute('''
                SELECT method_used, COUNT(*) as count, AVG(word_count) as avg_words
                FROM extracted_content 
                WHERE success = 1
                GROUP BY method_used
                ORDER BY count DESC
            ''')
            method_stats = cursor.fetchall()

            return stats, method_stats


def main():
    # Crear extractor
    extractor = NewsContentExtractor(headless=True)

    # Procesar URLs (limitar para prueba)
    extractor.process_all_urls(max_workers=2, limit=20)

    # Mostrar estadísticas
    stats, method_stats = extractor.get_extraction_stats()

    print(f"\n=== Estadísticas Generales ===")
    print(f"Total procesado: {stats[0]}")
    print(f"Exitosos: {stats[1]}")
    print(f"Tasa de éxito: {stats[1] / stats[0] * 100:.1f}%" if stats[0] > 0 else "N/A")
    print(f"Palabras totales: {stats[2]:,}")
    print(f"Tiempo promedio: {stats[3]:.2f}s" if stats[3] else "N/A")

    print(f"\n=== Por Método ===")
    for method, count, avg_words in method_stats:
        print(f"{method}: {count} extracciones, {avg_words:.0f} palabras promedio")


if __name__ == "__main__":
    main()