import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


class DuckDuckGoScraper:
    def __init__(self, headless=True, wait_timeout=10):
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
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, self.wait_timeout)

    def search_news(self, query):
        """Buscar noticias en DuckDuckGo usando URL directa con parámetros"""
        # Codificar la consulta para URL
        encoded_query = quote_plus(query)

        # Construir URL con parámetros para búsqueda de noticias
        url = f"https://duckduckgo.com/?q={encoded_query}&t=h_&iar=news&ndf=w"

        try:
            print(f"Cargando búsqueda: {url}")
            self.driver.get(url)

            # Esperar a que se carguen los resultados de noticias
            self.wait.until(
                EC.presence_of_element_located((By.ID, "react-layout"))
            )


            # Esperar un poco más para que se cargue completamente
            time.sleep(3)

            # Parsear con BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            return self.extract_news_results(soup)

        except Exception as e:
            print(f"Error en búsqueda: {e}")
            return []

    def extract_news_results(self, soup):
        """Extraer títulos, enlaces y fechas de las noticias"""
        results = []

        elements_body = soup.select_one('section[data-testid="no-results-message"]')
        news_list = elements_body.find('ol')

        # Buscar resultados de noticias
        news_elements = news_list.find_all('li')

        for result in news_elements:
            # Buscar el enlace principal (el título enlazado)
            link_elem = result.select_one('a')

            if link_elem:
                title_span = link_elem.select_one('h2')
                title = title_span.get_text(strip=True) if title_span else link_elem.get_text(strip=True)
                url = link_elem['href']

                # Buscar información adicional (fecha, fuente)
                snippet_elem = result.select_one('[data-result="snippet"]')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                # Buscar fecha si está disponible
                date_elem = result.select_one('.result__timestamp, .result-snippet__date')
                date = date_elem.get_text(strip=True) if date_elem else ""

                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet,
                    'date': date
                })

        return results

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
    with DuckDuckGoScraper(headless=False) as scraper:
        # Buscar noticias directamente
        results = scraper.search_news("noticias sobre exploración espacial junio 2025")

        print(f"Encontrados {len(results)} resultados:\n")

        for i, result in enumerate(results[:10], 1):
            print(f"{i}. {result['title']}")
            print(f"URL: {result['url']}")
            if result['date']:
                print(f"Fecha: {result['date']}")
            if result['snippet']:
                print(f"Descripción: {result['snippet'][:150]}...")
            print("-" * 80)

    print("Scraping completado!")