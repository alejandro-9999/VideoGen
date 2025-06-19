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


class GoogleNewsScraper:
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

        # Anti-detección específica para Google
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins-discovery")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")

        # User agents aleatorios para evitar detección
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")

        self.driver = webdriver.Chrome(options=chrome_options)

        # Ocultar webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Configurar otras propiedades del navegador
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": random.choice(user_agents)
        })

        self.wait = WebDriverWait(self.driver, self.wait_timeout)

    def human_like_delay(self, min_delay=1, max_delay=3):
        """Añade delays aleatorios para simular comportamiento humano"""
        time.sleep(random.uniform(min_delay, max_delay))

    def search_news(self, query, time_filter="w"):
        """
        Buscar noticias en Google News
        time_filter: 'h' (última hora), 'd' (último día), 'w' (última semana), 'm' (último mes), 'y' (último año)
        """
        try:
            # Primero ir a Google para establecer cookies
            print("Estableciendo sesión con Google...")
            self.driver.get("https://www.google.com")
            self.human_like_delay(2, 4)

            # Construir URL para Google News
            encoded_query = quote_plus(query)
            base_url = "https://www.google.com/search"
            params = f"?q={encoded_query}&tbm=nws&tbs=qdr:{time_filter}"
            url = base_url + params

            print(f"Cargando búsqueda: {url}")
            self.driver.get(url)

            # Esperar a que se carguen los resultados
            self.wait.until(
                EC.presence_of_element_located((By.ID, "search"))
            )

            self.human_like_delay(3, 5)

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
        """Extraer títulos, enlaces y fechas de las noticias de Google"""
        results = []

        # Buscar el contenedor principal de resultados
        search_container = soup.find('div', {'id': 'search'})

        if not search_container:
            print("No se encontró el contenedor de búsqueda")
            return results

        # Google News usa diferentes estructuras, probamos varios selectores
        result_selectors = [
            'div[data-hveid]',  # Contenedores de resultados principales
            'div.SoaBEf',  # Contenedor específico de noticias
            'div.MgUUmf',  # Otro contenedor común
            'div.NiLAwe',  # Contenedor de artículos
            'article',  # Elementos article
            'div.g'  # Contenedor genérico de resultados
        ]

        news_elements = []
        for selector in result_selectors:
            elements = soup.select(selector)
            if elements:
                # Filtrar elementos que contengan enlaces de noticias
                valid_elements = []
                for elem in elements:
                    if elem.find('a', href=True):
                        valid_elements.append(elem)

                if valid_elements:
                    news_elements = valid_elements
                    print(f"Encontrados {len(news_elements)} elementos con selector: {selector}")
                    break

        print(f"Total de elementos encontrados: {len(news_elements)}")

        for i, result in enumerate(news_elements):
            try:
                # Buscar el enlace principal (título)
                title_selectors = [
                    'h3 a',
                    'a[data-ved]',
                    'div[role="heading"] a',
                    'a.JheGif',
                    'a.WlydOe',
                    'a.mCBkyc'
                ]

                link_elem = None
                title = ""
                url = ""

                for title_sel in title_selectors:
                    link_elem = result.select_one(title_sel)
                    if link_elem:
                        break

                # Fallback: buscar cualquier enlace
                if not link_elem:
                    link_elem = result.find('a', href=True)

                if link_elem:
                    title = link_elem.get_text(strip=True)
                    url = link_elem.get('href', '')

                    # Procesar URL de Google (pueden ser enlaces de redirección)
                    if url.startswith('/url?'):
                        # Extraer URL real del parámetro q
                        import urllib.parse
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                        if 'q' in parsed:
                            url = parsed['q'][0]
                    elif url.startswith('/'):
                        url = urljoin('https://www.google.com', url)

                # Buscar snippet/descripción
                snippet_selectors = [
                    'div.VwiC3b',
                    'span.st',
                    'div.s',
                    'div.IsZvec',
                    'div.aCOpRe',
                    'span.aCOpRe'
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
                    'span.r0bn4c',
                    'span.f',
                    'div.slp',
                    'span.LEwnzc',
                    'div.OSrXXb',
                    'span.MUxGbd'
                ]

                date = ""
                for date_sel in date_selectors:
                    date_elem = result.select_one(date_sel)
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        # Verificar que sea realmente una fecha
                        if any(time_word in date_text.lower() for time_word in
                               ['hace', 'ago', 'hour', 'day', 'week', 'month', 'año', 'mes', 'día', 'hora']):
                            date = date_text
                            break

                # Buscar fuente
                source_selectors = [
                    'span.VuuXrf',
                    'div.XTjFC',
                    'cite',
                    'span.qzEoUe'
                ]

                source = ""
                for source_sel in source_selectors:
                    source_elem = result.select_one(source_sel)
                    if source_elem:
                        source = source_elem.get_text(strip=True)
                        break

                # Solo agregar si tenemos título y URL válidos
                if title and url and len(title) > 10 and 'google.com' not in url:
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet,
                        'date': date,
                        'source': source if source else 'Google News',
                        'search_engine': 'Google'
                    })

                    print(f"Resultado {len(results)}: {title[:50]}...")

                    # Limitar el número de resultados para evitar sobrecarga
                    if len(results) >= 20:
                        break

            except Exception as e:
                print(f"Error procesando resultado {i}: {e}")
                continue

        return results

    def search_with_retry(self, query, max_retries=3, time_filter="w"):
        """Buscar con reintentos en caso de bloqueo"""
        for attempt in range(max_retries):
            try:
                print(f"Intento {attempt + 1} de {max_retries}")
                results = self.search_news(query, time_filter)

                if results:
                    return results
                else:
                    print("No se encontraron resultados, reintentando...")
                    self.human_like_delay(5, 10)

            except Exception as e:
                print(f"Error en intento {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    self.human_like_delay(10, 15)
                    # Reiniciar driver en caso de bloqueo
                    try:
                        self.driver.quit()
                        self.setup_driver(headless=True)
                    except:
                        pass

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
    query = "noticias sobre exploración espacial junio 2025"

    with GoogleNewsScraper(headless=False) as scraper:
        print("=== Búsqueda en Google News ===")

        # Buscar noticias de la última semana
        results = scraper.search_with_retry(query, max_retries=3, time_filter="w")

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
            print("-" * 80)

    print("Scraping completado!")