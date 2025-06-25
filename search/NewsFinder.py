"""
News Scraper Library with Dependency Injection
Librería modular y desacoplada para scraping de noticias
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Protocol
import time
import random
from urllib.parse import quote_plus, urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
import urllib.parse



# ============================================================================
# INTERFACES Y PROTOCOLOS
# ============================================================================

class NewsResult:
    """Modelo de datos para resultados de noticias"""

    def __init__(self, title: str, url: str, snippet: str = "",
                 date: str = "", source: str = "", search_engine: str = ""):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.date = date
        self.source = source
        self.search_engine = search_engine

    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'url': self.url,
            'snippet': self.snippet,
            'date': self.date,
            'source': self.source,
            'search_engine': self.search_engine
        }


class WebDriverProvider(Protocol):
    """Protocolo para proveedores de WebDriver"""

    def get_driver(self, headless: bool = True) -> webdriver.Chrome:
        ...

    def configure_options(self, headless: bool = True) -> Options:
        ...


class NewsScraperInterface(ABC):
    """Interface para scrapers de noticias"""

    @abstractmethod
    def search_news(self, query: str, **kwargs) -> List[NewsResult]:
        """Buscar noticias con la consulta especificada"""
        pass

    @abstractmethod
    def close(self):
        """Cerrar recursos del scraper"""
        pass


# ============================================================================
# PROVEEDORES DE WEBDRIVER
# ============================================================================

class ChromeDriverProvider:
    """Proveedor de ChromeDriver con configuraciones específicas"""

    def __init__(self, wait_timeout: int = 15):
        self.wait_timeout = wait_timeout

    def get_driver(self, headless: bool = True) -> webdriver.Chrome:
        """Crear y configurar una instancia de ChromeDriver"""
        options = self.configure_options(headless)
        driver = webdriver.Chrome(options=options)
        self._configure_anti_detection(driver)
        return driver

    def configure_options(self, headless: bool = True) -> Options:
        """Configurar opciones básicas de Chrome"""
        chrome_options = Options()

        if headless:
            chrome_options.add_argument("--headless")

        # Configuraciones básicas
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        return chrome_options

    def _configure_anti_detection(self, driver: webdriver.Chrome):
        """Configurar medidas anti-detección"""
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")


class GoogleChromeDriverProvider(ChromeDriverProvider):
    """Proveedor especializado para Google con anti-detección avanzada"""

    def configure_options(self, headless: bool = True) -> Options:
        options = super().configure_options(headless)

        # Anti-detección específica para Google
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")

        # User agent aleatorio
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        options.add_argument(f"--user-agent={random.choice(user_agents)}")

        return options

    def _configure_anti_detection(self, driver: webdriver.Chrome):
        super()._configure_anti_detection(driver)

        # Configuraciones adicionales para Google
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]

        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": random.choice(user_agents)
        })


# ============================================================================
# SCRAPERS BASE
# ============================================================================

class BaseNewsScraper(NewsScraperInterface):
    """Clase base para scrapers de noticias"""

    def __init__(self, driver_provider: WebDriverProvider, headless: bool = True):
        self.driver_provider = driver_provider
        self.headless = headless
        self.driver = None
        self.wait = None
        self._setup_driver()

    def _setup_driver(self):
        """Configurar el driver usando el proveedor"""
        self.driver = self.driver_provider.get_driver(self.headless)
        self.wait = WebDriverWait(self.driver, getattr(self.driver_provider, 'wait_timeout', 15))

    def human_like_delay(self, min_delay: float = 1, max_delay: float = 3):
        """Añadir delays aleatorios para simular comportamiento humano"""
        time.sleep(random.uniform(min_delay, max_delay))

    def close(self):
        """Cerrar el driver"""
        if self.driver:
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# IMPLEMENTACIONES ESPECÍFICAS
# ============================================================================

class GoogleNewsScraper(BaseNewsScraper):
    """Scraper para Google News"""

    def search_news(self, query: str, time_filter: str = "w", max_results: int = 20) -> List[NewsResult]:
        """Buscar noticias en Google News"""
        try:
            # Establecer sesión con Google
            self.driver.get("https://www.google.com")
            self.human_like_delay(2, 4)

            # Construir URL
            encoded_query = quote_plus(query)
            url = f"https://www.google.com/search?q={encoded_query}&tbm=nws&tbs=qdr:{time_filter}"

            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.ID, "search")))
            self.human_like_delay(3, 5)

            # Scroll para cargar contenido
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            self.human_like_delay(1, 2)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            return self._extract_google_results(soup, max_results)

        except Exception as e:
            print(f"Error en búsqueda de Google: {e}")
            return []

    def _extract_google_results(self, soup: BeautifulSoup, max_results: int) -> List[NewsResult]:
        """Extraer resultados de Google News"""
        results = []
        search_container = soup.find('div', {'id': 'search'})

        if not search_container:
            return results

        # Selectores para diferentes elementos
        result_selectors = ['div[data-hveid]', 'div.SoaBEf', 'div.MgUUmf', 'div.NiLAwe', 'article', 'div.g']

        news_elements = []
        for selector in result_selectors:
            elements = soup.select(selector)
            if elements:
                valid_elements = [elem for elem in elements if elem.find('a', href=True)]
                if valid_elements:
                    news_elements = valid_elements
                    break

        for i, result in enumerate(news_elements[:max_results]):
            try:
                news_result = self._extract_google_article(result)
                if news_result:
                    results.append(news_result)
            except Exception as e:
                print(f"Error procesando resultado {i}: {e}")
                continue

        return results

    def _extract_google_article(self, result) -> Optional[NewsResult]:
        """Extraer información de un artículo individual de Google"""
        # Buscar título y URL
        title_selectors = ['h3 a', 'a[data-ved]', 'div[role="heading"] a', 'a.JheGif', 'a.WlydOe', 'a.mCBkyc']

        link_elem = None
        for selector in title_selectors:
            link_elem = result.select_one(selector)
            if link_elem:
                break

        if not link_elem:
            link_elem = result.find('a', href=True)

        if not link_elem:
            return None

        title = link_elem.get_text(strip=True)
        url = link_elem.get('href', '')

        # Procesar URL de Google
        if url.startswith('/url?'):
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            if 'q' in parsed:
                url = parsed['q'][0]
        elif url.startswith('/'):
            url = urljoin('https://www.google.com', url)

        # Extraer snippet
        snippet_selectors = ['div.VwiC3b', 'span.st', 'div.s', 'div.IsZvec', 'div.aCOpRe', 'span.aCOpRe']
        snippet = ""
        for selector in snippet_selectors:
            snippet_elem = result.select_one(selector)
            if snippet_elem:
                snippet_text = snippet_elem.get_text(strip=True)
                if len(snippet_text) > 20 and snippet_text != title:
                    snippet = snippet_text
                    break

        # Extraer fecha
        date_selectors = ['span.r0bn4c', 'span.f', 'div.slp', 'span.LEwnzc', 'div.OSrXXb', 'span.MUxGbd']
        date = ""
        for selector in date_selectors:
            date_elem = result.select_one(selector)
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                time_words = ['hace', 'ago', 'hour', 'day', 'week', 'month', 'año', 'mes', 'día', 'hora']
                if any(word in date_text.lower() for word in time_words):
                    date = date_text
                    break

        # Extraer fuente
        source_selectors = ['span.VuuXrf', 'div.XTjFC', 'cite', 'span.qzEoUe']
        source = ""
        for selector in source_selectors:
            source_elem = result.select_one(selector)
            if source_elem:
                source = source_elem.get_text(strip=True)
                break

        if title and url and len(title) > 10 and 'google.com' not in url:
            return NewsResult(
                title=title,
                url=url,
                snippet=snippet,
                date=date,
                source=source if source else 'Google News',
                search_engine='Google'
            )

        return None


class YahooNewsScraper(BaseNewsScraper):
    """Scraper para Yahoo News"""

    def search_news(self, query: str, **kwargs) -> List[NewsResult]:
        """Buscar noticias en Yahoo News"""
        try:
            encoded_query = quote_plus(query)
            url = f"https://co.search.yahoo.com/search?p={encoded_query}&fr=uh3_news_web&fr2=time&btf=w&tsrc=uh3_news_web"

            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.ID, "web")))
            time.sleep(5)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            return self._extract_yahoo_results(soup)

        except Exception as e:
            print(f"Error en búsqueda de Yahoo: {e}")
            return []

    def _extract_yahoo_results(self, soup: BeautifulSoup) -> List[NewsResult]:
        """Extraer resultados de Yahoo News"""
        results = []
        main_content = soup.find('div', {'id': 'web'})

        if not main_content:
            return results

        result_selectors = ['div[data-bck="result"]', '.algo', '.Sr', 'div.algo-sr', 'li[data-algo-crid]']

        news_elements = []
        for selector in result_selectors:
            elements = soup.select(selector)
            if elements:
                news_elements = elements
                break

        if not news_elements:
            news_elements = soup.find_all('div', class_=lambda x: x and ('result' in x.lower() or 'algo' in x.lower()))

        for result in news_elements:
            try:
                news_result = self._extract_yahoo_article(result)
                if news_result:
                    results.append(news_result)
            except Exception as e:
                continue

        return results

    def _extract_yahoo_article(self, result) -> Optional[NewsResult]:
        """Extraer información de un artículo individual de Yahoo"""
        link_selectors = ['h3 a', '.ac-21th a', 'a[data-pmd]', 'a.ac-algo-fz']

        link_elem = None
        for selector in link_selectors:
            link_elem = result.select_one(selector)
            if link_elem:
                break

        if not link_elem:
            link_elem = result.find('a', href=True)

        if not link_elem:
            return None

        title = link_elem.get_text(strip=True)
        url = link_elem.get('href', '')

        if url.startswith('/'):
            url = 'https://co.search.yahoo.com' + url

        # Extraer snippet
        snippet_selectors = ['.ac-21th', '.compText', 'span.fc-2nd', 'p']
        snippet = ""
        for selector in snippet_selectors:
            snippet_elem = result.select_one(selector)
            if snippet_elem and snippet_elem != link_elem:
                snippet_text = snippet_elem.get_text(strip=True)
                if len(snippet_text) > 20:
                    snippet = snippet_text
                    break

        # Extraer fecha
        date_selectors = ['.fc-3rd', '.s-time', 'span[data-age]', '.timestamp']
        date = ""
        for selector in date_selectors:
            date_elem = result.select_one(selector)
            if date_elem:
                date = date_elem.get_text(strip=True)
                break

        if title and url and len(title) > 10:
            return NewsResult(
                title=title,
                url=url,
                snippet=snippet,
                date=date,
                source='Yahoo News',
                search_engine='Yahoo'
            )

        return None


class DuckDuckGoNewsScraper(BaseNewsScraper):
    """Scraper para DuckDuckGo News"""

    def search_news(self, query: str, **kwargs) -> List[NewsResult]:
        """Buscar noticias en DuckDuckGo"""
        try:
            encoded_query = quote_plus(query)
            url = f"https://duckduckgo.com/?q={encoded_query}&t=h_&iar=news&ndf=w"

            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.ID, "react-layout")))
            time.sleep(3)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            return self._extract_duckduckgo_results(soup)

        except Exception as e:
            print(f"Error en búsqueda de DuckDuckGo: {e}")
            return []

    def _extract_duckduckgo_results(self, soup: BeautifulSoup) -> List[NewsResult]:
        """Extraer resultados de DuckDuckGo News"""
        results = []

        try:
            elements_body = soup.select_one('section[data-testid="no-results-message"]')
            news_list = elements_body.find('ol')
            news_elements = news_list.find_all('li')

            for result in news_elements:
                link_elem = result.select_one('a')
                if link_elem:
                    title_span = link_elem.select_one('h2')
                    title = title_span.get_text(strip=True) if title_span else link_elem.get_text(strip=True)
                    url = link_elem['href']

                    snippet_elem = result.select_one('[data-result="snippet"]')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    date_elem = result.select_one('.result__timestamp, .result-snippet__date')
                    date = date_elem.get_text(strip=True) if date_elem else ""

                    results.append(NewsResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        date=date,
                        source='DuckDuckGo News',
                        search_engine='DuckDuckGo'
                    ))
        except Exception as e:
            print(f"Error extrayendo resultados de DuckDuckGo: {e}")

        return results

class DDGApiScraper(NewsScraperInterface):
    """Scraper usando la librería DDGS de DuckDuckGo"""

    def __init__(self, headless: bool = True):
        pass  # No requiere driver

    def search_news(self, query: str, time_filter: str = "w", max_results: int = 20) -> List[NewsResult]:
        """Buscar noticias usando la API no oficial de DuckDuckGo"""
        try:
            results = []
            with DDGS() as ddgs:
                response = ddgs.news(query, safesearch="off", region="wt-wt", max_results=max_results, timelimit=time_filter)

                for r in response:
                    title = r.get("title", "")
                    url = r.get("url", "")
                    source = r.get("source", "")
                    date = r.get("date", "")
                    snippet = r.get("body", "")

                    if title and url:
                        results.append(NewsResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            date=date,
                            source=source or "DuckDuckGo API",
                            search_engine="DuckDuckGo API"
                        ))
        except Exception as e:
            print(f"❌ Error en DDG API: {e}")
            return []

        return results

    def close(self):
        pass  # No hay recursos que cerrar


# ============================================================================
# FACTORY Y GESTIÓN DE SCRAPERS
# ============================================================================

class NewsScraperFactory:
    """Factory para crear scrapers de noticias"""

    @staticmethod
    def create_scraper(scraper_type: str, headless: bool = True, **kwargs) -> NewsScraperInterface:
        """Crear un scraper específico"""
        scraper_type = scraper_type.lower()

        if scraper_type == 'google':
            driver_provider = GoogleChromeDriverProvider(kwargs.get('wait_timeout', 15))
            return GoogleNewsScraper(driver_provider, headless)

        elif scraper_type == 'yahoo':
            driver_provider = ChromeDriverProvider(kwargs.get('wait_timeout', 15))
            return YahooNewsScraper(driver_provider, headless)

        elif scraper_type == 'duckduckgo':
            driver_provider = ChromeDriverProvider(kwargs.get('wait_timeout', 10))
            return DuckDuckGoNewsScraper(driver_provider, headless)

        elif scraper_type == 'duckduckgo_api':
            return DDGApiScraper()

        else:
            raise ValueError(f"Tipo de scraper no soportado: {scraper_type}")


class NewsScraperManager:
    """Gestor para múltiples scrapers con estrategias de búsqueda"""

    def __init__(self):
        self.scrapers: Dict[str, NewsScraperInterface] = {}

    def add_scraper(self, name: str, scraper: NewsScraperInterface):
        """Agregar un scraper al gestor"""
        self.scrapers[name] = scraper

    def remove_scraper(self, name: str):
        """Remover un scraper del gestor"""
        if name in self.scrapers:
            self.scrapers[name].close()
            del self.scrapers[name]

    def search_with_scraper(self, scraper_name: str, query: str, **kwargs) -> List[NewsResult]:
        """Buscar usando un scraper específico"""
        if scraper_name not in self.scrapers:
            raise ValueError(f"Scraper '{scraper_name}' no encontrado")

        return self.scrapers[scraper_name].search_news(query, **kwargs)

    def search_all(self, query: str, **kwargs) -> Dict[str, List[NewsResult]]:
        """Buscar usando todos los scrapers disponibles"""
        results = {}

        for name, scraper in self.scrapers.items():
            try:
                results[name] = scraper.search_news(query, **kwargs)
            except Exception as e:
                print(f"Error en scraper {name}: {e}")
                results[name] = []

        return results

    def search_with_fallback(self, query: str, preferred_order: List[str] = None, **kwargs) -> List[NewsResult]:
        """Buscar con estrategia de fallback"""
        if preferred_order is None:
            preferred_order = list(self.scrapers.keys())

        for scraper_name in preferred_order:
            if scraper_name in self.scrapers:
                try:
                    results = self.scrapers[scraper_name].search_news(query, **kwargs)
                    if results:
                        return results
                except Exception as e:
                    print(f"Error en scraper {scraper_name}, probando siguiente...")
                    continue

        return []

    def close_all(self):
        """Cerrar todos los scrapers"""
        for scraper in self.scrapers.values():
            scraper.close()
        self.scrapers.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()