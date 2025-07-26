import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


class YahooNewsScraper:
    def __init__(self, headless=True, wait_timeout=15):
        self.wait_timeout = wait_timeout
        self.setup_driver(headless)

    def setup_driver(self, headless):
        """Configurar el driver de Selenium"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, self.wait_timeout)

    def search_news(self, query):
        """Buscar noticias en Yahoo News"""
        # Codificar la consulta para URL
        encoded_query = quote_plus(query)

        # Construir URL para Yahoo News
        # Estructura basada en la URL que proporcionaste
        base_url = "https://co.search.yahoo.com/search"
        params = f"?p={encoded_query}&fr=uh3_news_web&fr2=time&btf=w&tsrc=uh3_news_web"
        url = base_url + params

        try:
            print(f"Cargando búsqueda: {url}")
            self.driver.get(url)

            # Esperar a que se carguen los resultados
            self.wait.until(
                EC.presence_of_element_located((By.ID, "web"))
            )

            # Esperar un poco más para que se cargue completamente
            time.sleep(5)

            # Parsear con BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            return self.extract_news_results(soup)

        except Exception as e:
            print(f"Error en búsqueda: {e}")
            return []

    def extract_news_results(self, soup):
        """Extraer títulos, enlaces y fechas de las noticias de Yahoo"""
        results = []

        # Buscar el contenedor principal de resultados
        main_content = soup.find('div', {'id': 'web'})

        if not main_content:
            print("No se encontró el contenedor principal de resultados")
            return results

        # Buscar todos los resultados de búsqueda
        # Yahoo usa diferentes selectores, probamos varios
        result_selectors = [
            'div[data-bck="result"]',  # Selector común de Yahoo
            '.algo',  # Otro selector común
            '.Sr',  # Selector alternativo
            'div.algo-sr',  # Variante del selector
            'li[data-algo-crid]'  # Selector para listas de resultados
        ]

        news_elements = []
        for selector in result_selectors:
            elements = soup.select(selector)
            if elements:
                news_elements = elements
                print(f"Encontrados elementos con selector: {selector}")
                break

        if not news_elements:
            # Fallback: buscar enlaces que parezcan noticias
            news_elements = soup.find_all('div', class_=lambda x: x and ('result' in x.lower() or 'algo' in x.lower()))

        print(f"Total de elementos encontrados: {len(news_elements)}")

        for i, result in enumerate(news_elements):
            try:
                # Buscar el enlace principal (título)
                link_selectors = [
                    'h3 a',
                    '.ac-21th a',
                    'a[data-pmd]',
                    'a.ac-algo-fz'
                ]

                link_elem = None
                title = ""
                url = ""

                for link_sel in link_selectors:
                    link_elem = result.select_one(link_sel)
                    if link_elem:
                        break

                # Si no encontramos con selectores específicos, buscar cualquier enlace
                if not link_elem:
                    link_elem = result.find('a', href=True)

                if link_elem:
                    title = link_elem.get_text(strip=True)
                    url = link_elem.get('href', '')

                    # Yahoo a veces usa URLs de redirección
                    if url.startswith('/'):
                        url = 'https://co.search.yahoo.com' + url

                # Buscar snippet/descripción
                snippet_selectors = [
                    '.ac-21th',
                    '.compText',
                    'span.fc-2nd',
                    'p'
                ]

                snippet = ""
                for snip_sel in snippet_selectors:
                    snippet_elem = result.select_one(snip_sel)
                    if snippet_elem and snippet_elem != link_elem:
                        snippet = snippet_elem.get_text(strip=True)
                        if len(snippet) > 20:  # Solo tomar snippets con contenido sustancial
                            break

                # Buscar fecha
                date_selectors = [
                    '.fc-3rd',
                    '.s-time',
                    'span[data-age]',
                    '.timestamp'
                ]

                date = ""
                for date_sel in date_selectors:
                    date_elem = result.select_one(date_sel)
                    if date_elem:
                        date = date_elem.get_text(strip=True)
                        break

                # Solo agregar si tenemos título y URL válidos
                if title and url and len(title) > 10:
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet,
                        'date': date,
                        'source': 'Yahoo News'
                    })

                    print(f"Resultado {len(results)}: {title[:50]}...")

            except Exception as e:
                print(f"Error procesando resultado {i}: {e}")
                continue

        return results

    def search_news_alternative(self, query):
        """Método alternativo usando la sección de noticias directamente"""
        encoded_query = quote_plus(query)

        # URL alternativa para noticias específicamente
        url = f"https://news.yahoo.com/search?p={encoded_query}"

        try:
            print(f"Probando búsqueda alternativa: {url}")
            self.driver.get(url)

            time.sleep(5)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            results = []

            # Buscar artículos de noticias específicamente
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and 'story' in x.lower())

            for article in articles:
                try:
                    link_elem = article.find('a', href=True)
                    if link_elem:
                        title = link_elem.get_text(strip=True)
                        url = link_elem['href']

                        if not url.startswith('http'):
                            url = 'https://news.yahoo.com' + url

                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': '',
                            'date': '',
                            'source': 'Yahoo News Direct'
                        })

                except Exception as e:
                    continue

            return results

        except Exception as e:
            print(f"Error en búsqueda alternativa: {e}")
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
    query = "noticias del espacio junio 2025"

    with YahooNewsScraper(headless=False) as scraper:
        print("=== Búsqueda principal ===")
        results = scraper.search_news(query)

        if not results:
            print("=== Intentando método alternativo ===")
            results = scraper.search_news_alternative(query)

        print(f"\nEncontrados {len(results)} resultados:\n")

        for i, result in enumerate(results[:10], 1):
            print(f"{i}. {result['title']}")
            print(f"URL: {result['url']}")
            if result['date']:
                print(f"Fecha: {result['date']}")
            if result['snippet']:
                print(f"Descripción: {result['snippet'][:150]}...")
            print(f"Fuente: {result['source']}")
            print("-" * 80)

    print("Scraping completado!")