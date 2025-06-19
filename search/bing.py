import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin


class BingNewsScraper:
    def __init__(self, headless=True, wait_timeout=15):
        self.wait_timeout = wait_timeout
        self.setup_driver(headless)

    def setup_driver(self, headless):
        """Configurar el driver de Selenium con opciones anti-detección"""
        chrome_options = Options()

        # Configuraciones básicas
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        # Anti-detección
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-extensions")

        # User agents aleatorios
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")

        self.driver = webdriver.Chrome(options=chrome_options)

        # Ocultar webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        self.wait = WebDriverWait(self.driver, self.wait_timeout)

    def human_like_delay(self, min_delay=1, max_delay=3):
        """Añade delays aleatorios para simular comportamiento humano"""
        time.sleep(random.uniform(min_delay, max_delay))

    def search_news(self, query, time_filter="8"):
        """
        Buscar noticias en Bing News
        time_filter:
        - "1" = Última hora
        - "2" = Últimas 24 horas
        - "3" = Última semana
        - "4" = Último mes
        - "8" = Cualquier momento (por defecto en tu URL)
        """
        try:
            # Construir URL para Bing News
            encoded_query = quote_plus(query)
            base_url = "https://www.bing.com/news/search"
            params = f"?q={encoded_query}&qft=interval%3d%22{time_filter}%22&form=PTFTNR"
            url = base_url + params

            print(f"Cargando búsqueda: {url}")
            self.driver.get(url)

            # Esperar a que se carguen los resultados
            self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "news-card"))
            )

            self.human_like_delay(2, 4)

            # Scroll para cargar más contenido
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            self.human_like_delay(1, 2)

            # Parsear con BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            return self.extract_news_results(soup)

        except Exception as e:
            print(f"Error en búsqueda: {e}")
            return []

    def extract_news_results(self, soup):
        """Extraer títulos, enlaces y fechas de las noticias de Bing"""
        results = []

        # Bing News usa principalmente estas estructuras
        result_selectors = [
            '.news-card',  # Tarjetas de noticias principales
            '.news-card-body',  # Cuerpo de las tarjetas
            '.cardCommon',  # Tarjetas comunes
            '.na_cnt',  # Contenedor de noticias
            'article.news-card'  # Artículos específicos
        ]

        news_elements = []
        for selector in result_selectors:
            elements = soup.select(selector)
            if elements:
                news_elements = elements
                print(f"Encontrados {len(news_elements)} elementos con selector: {selector}")
                break

        # Fallback: buscar por estructura HTML más general
        if not news_elements:
            news_elements = soup.find_all('div', class_=lambda x: x and 'news' in x.lower())
            print(f"Fallback: encontrados {len(news_elements)} elementos")

        print(f"Total de elementos encontrados: {len(news_elements)}")

        for i, result in enumerate(news_elements):
            try:
                # Buscar el enlace principal (título)
                title_selectors = [
                    'a.title',
                    '.news-card-title a',
                    'h4 a',
                    'h3 a',
                    '.cardTitleLinkIdentifier',
                    'a[data-t]'
                ]

                link_elem = None
                title = ""
                url = ""

                for title_sel in title_selectors:
                    link_elem = result.select_one(title_sel)
                    if link_elem:
                        break

                # Fallback: buscar cualquier enlace con href
                if not link_elem:
                    link_elem = result.find('a', href=True)

                if link_elem:
                    title = link_elem.get_text(strip=True)
                    url = link_elem.get('href', '')

                    # Procesar URLs relativas
                    if url.startswith('/'):
                        url = urljoin('https://www.bing.com', url)
                    elif url.startswith('http') and 'bing.com' in url:
                        # Bing a veces usa URLs de redirección, extraer la URL real
                        try:
                            from urllib.parse import parse_qs, urlparse
                            parsed = urlparse(url)
                            if 'u' in parse_qs(parsed.query):
                                url = parse_qs(parsed.query)['u'][0]
                        except:
                            pass

                # Buscar snippet/descripción
                snippet_selectors = [
                    '.snippet',
                    '.news-card-body p',
                    '.cardText',
                    '.description',
                    '.caption'
                ]

                snippet = ""
                for snip_sel in snippet_selectors:
                    snippet_elem = result.select_one(snip_sel)
                    if snippet_elem:
                        snippet_text = snippet_elem.get_text(strip=True)
                        if len(snippet_text) > 20 and snippet_text != title:
                            snippet = snippet_text
                            break

                # Buscar fecha
                date_selectors = [
                    '.timestamp',
                    '.news-card-time',
                    '.source-time',
                    '.time',
                    '.age'
                ]

                date = ""
                for date_sel in date_selectors:
                    date_elem = result.select_one(date_sel)
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        # Verificar que contenga indicadores de tiempo
                        if any(time_word in date_text.lower() for time_word in
                               ['hace', 'ago', 'hour', 'day', 'week', 'month', 'min', 'h', 'd', 'w', 'm']):
                            date = date_text
                            break

                # Buscar fuente
                source_selectors = [
                    '.source',
                    '.news-source',
                    '.provider',
                    '.publisher',
                    '.attribution'
                ]

                source = ""
                for source_sel in source_selectors:
                    source_elem = result.select_one(source_sel)
                    if source_elem:
                        source_text = source_elem.get_text(strip=True)
                        # Limpiar texto de fuente
                        if source_text and len(source_text) < 100:
                            source = source_text
                            break

                # Buscar imagen si está disponible
                image_url = ""
                img_elem = result.find('img')
                if img_elem and img_elem.get('src'):
                    image_url = img_elem['src']
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url

                # Solo agregar si tenemos título y URL válidos
                if title and url and len(title) > 10 and 'bing.com/news' not in url:
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet,
                        'date': date,
                        'source': source if source else 'Bing News',
                        'image_url': image_url,
                        'search_engine': 'Bing'
                    })

                    print(f"Resultado {len(results)}: {title[:50]}...")

                    # Limitar resultados
                    if len(results) >= 25:
                        break

            except Exception as e:
                print(f"Error procesando resultado {i}: {e}")
                continue

        return results

    def search_alternative_method(self, query):
        """Método alternativo usando la página principal de Bing News"""
        try:
            encoded_query = quote_plus(query)
            url = f"https://www.bing.com/news?q={encoded_query}"

            print(f"Probando método alternativo: {url}")
            self.driver.get(url)

            self.human_like_delay(3, 5)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            results = []

            # Buscar elementos de noticias con estructura alternativa
            news_items = soup.find_all(['div', 'article'], class_=lambda x: x and any(
                keyword in x.lower() for keyword in ['news', 'card', 'item', 'story']
            ))

            for item in news_items:
                try:
                    link = item.find('a', href=True)
                    if link:
                        title = link.get_text(strip=True)
                        url = link['href']

                        if url.startswith('/'):
                            url = 'https://www.bing.com' + url

                        if title and len(title) > 10:
                            results.append({
                                'title': title,
                                'url': url,
                                'snippet': '',
                                'date': '',
                                'source': 'Bing News',
                                'image_url': '',
                                'search_engine': 'Bing'
                            })

                except Exception as e:
                    continue

            return results

        except Exception as e:
            print(f"Error en método alternativo: {e}")
            return []

    def search_with_retry(self, query, max_retries=3, time_filter="8"):
        """Buscar con reintentos en caso de error"""
        for attempt in range(max_retries):
            try:
                print(f"Intento {attempt + 1} de {max_retries}")
                results = self.search_news(query, time_filter)

                if results:
                    return results
                else:
                    print("No se encontraron resultados, probando método alternativo...")
                    alt_results = self.search_alternative_method(query)
                    if alt_results:
                        return alt_results

                    if attempt < max_retries - 1:
                        print("Reintentando...")
                        self.human_like_delay(5, 8)

            except Exception as e:
                print(f"Error en intento {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    self.human_like_delay(8, 12)

        return []

    def close(self):
        """Cerrar el driver"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Ejemplo de uso
if __name__ == "__main__":
    query = "noticias de exploración espacial"

    with BingNewsScraper(headless=False) as scraper:
        print("=== Búsqueda en Bing News ===")

        # Buscar noticias (tiempo 8 = cualquier momento, como en tu URL)
        results = scraper.search_with_retry(query, max_retries=2, time_filter="8")

        print(f"\nEncontrados {len(results)} resultados:\n")

        for i, result in enumerate(results[:15], 1):
            print(f"{i}. {result['title']}")
            print(f"URL: {result['url']}")
            if result['source']:
                print(f"Fuente: {result['source']}")
            if result['date']:
                print(f"Fecha: {result['date']}")
            if result['snippet']:
                print(f"Descripción: {result['snippet'][:200]}...")
            if result['image_url']:
                print(f"Imagen: {result['image_url']}")
            print("-" * 80)

    print("Scraping completado!")