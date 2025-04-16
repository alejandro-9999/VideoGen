import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from urllib.parse import urljoin


class WebScraper:
    def __init__(self, headless=True):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.options = webdriver.ChromeOptions()
        if headless:
            self.options.add_argument('--headless')

    def fetch_articles(self, topic, search_engine='google'):
        print(f"🔎 Buscando artículos sobre: {topic} en {search_engine.capitalize()}...")
        if search_engine == 'google':
            return self._scrape_google(topic)
        elif search_engine == 'duckduckgo':
            return self._scrape_duckduckgo(topic)
        elif search_engine == 'brave':
            return self._scrape_brave(topic)
        else:
            raise ValueError("⚠️ Motor de búsqueda no soportado. Usa 'google', 'duckduckgo' o 'brave'.")

    def _scrape_google(self, topic):
        query = f"{topic.replace(' ', '+')}&source=lnt&tbs=qdr:d&sa=X"
        url = f"https://www.google.com/search?q={query}"
        return self._scrape_with_selenium(url, 'rso', 'div', {"data-snhf": "0"}, 'h3')

    def _scrape_duckduckgo(self, topic):
        query = f"{topic.replace(' ', '+')}&t=ffab&df=d&ia=web"
        url = f"https://duckduckgo.com/?q={query}"
        return self._scrape_with_selenium(url, 'react-results--main', 'li', {"data-layout": "organic"}, 'h2',{"data-testid":"result-title-a"})

    def _scrape_brave(self, topic):
        query = f"{topic.replace(' ', '+')}&source=web&tf=pw"
        url = f"https://search.brave.com/search?q={query}"
        return self._scrape_with_requests(url, 'results', 'div', 'snippet', 'title')

    def _scrape_with_requests(self, url, results_id, result_tag, result_class, title_class, result_link=None):
        print(f"🌍 Accediendo a: {url}")
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            print(f"❌ Error {response.status_code} al acceder a la página.")
            return []

        soup = BeautifulSoup(response.content, 'lxml')
        results_container = soup.find('div', id=results_id)
        results = results_container.find_all(result_tag, class_=result_class) if results_container else []

        articles = []
        for result in results:
            title_element = result.find('div', class_=title_class)
            link_element = result.find('a', href=True) if not result_link else result.find('a', result_link)

            title = title_element.text.strip() if title_element else None
            link = urljoin(url, link_element['href']) if link_element else None

            if title and link:
                content = self.extract_article_content(link)
                articles.append({'title': title, 'link': link, 'content': content})
                print(f"✅ Artículo encontrado: {title}")

        return articles

    def _scrape_with_selenium(self, url, wait_element_class, result_tag, result_attrs, title_tag, result_link=None):
        print(f"🚀 Iniciando Selenium para: {url}")
        driver = webdriver.Chrome(options=self.options)
        articles = []
        try:
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, wait_element_class)))
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            results = soup.find_all(result_tag, result_attrs)

            for result in results:
                title_element = result.find(title_tag)
                link_element = result.find('a', href=True) if not result_link else result.find('a', result_link)

                title = title_element.text.strip() if title_element else None
                link = urljoin(url, link_element['href']) if link_element else None
                print(link)
                if title and link:
                    content = self.extract_article_content(link)
                    articles.append({'title': title, 'link': link, 'content': content})
                    print(f"✅ Artículo encontrado: {title}")

        except Exception as e:
            print(f"⚠️ Error durante la extracción: {e}")
        finally:
            driver.quit()

        return articles

    def extract_article_content(self, url):
        print(f"📄 Extrayendo contenido de: {url}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
        except (requests.RequestException, requests.Timeout) as e:
            print(f"❌ No se pudo acceder al contenido de {url} - {e}")
            return "No se pudo acceder al contenido."

        soup = BeautifulSoup(response.content, 'lxml')
        paragraphs = soup.find_all('body')
        return " ".join(p.text for p in paragraphs)

