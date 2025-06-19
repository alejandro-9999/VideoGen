import requests
from bs4 import BeautifulSoup
import ollama
import time
import random
from urllib.parse import quote_plus, urljoin
import json


class MultiSearchEngine:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def search_duckduckgo(self, query):
        """Búsqueda en DuckDuckGo"""
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'DuckDuckGo',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'DuckDuckGo', 'html': '', 'status': 'error', 'error': str(e)}

    def search_bing(self, query):
        """Búsqueda en Bing"""
        try:
            url = f"https://www.bing.com/search?q={quote_plus(query)}"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'Bing',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'Bing', 'html': '', 'status': 'error', 'error': str(e)}

    def search_yandex(self, query):
        """Búsqueda en Yandex"""
        try:
            url = f"https://yandex.com/search/?text={quote_plus(query)}"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'Yandex',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'Yandex', 'html': '', 'status': 'error', 'error': str(e)}

    def search_startpage(self, query):
        """Búsqueda en Startpage"""
        try:
            url = f"https://www.startpage.com/sp/search?query={quote_plus(query)}"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'Startpage',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'Startpage', 'html': '', 'status': 'error', 'error': str(e)}

    def search_searx(self, query, instance="https://searx.be"):
        """Búsqueda en SearX (motor de búsqueda libre)"""
        try:
            url = f"{instance}/search?q={quote_plus(query)}&format=html"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'SearX',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'SearX', 'html': '', 'status': 'error', 'error': str(e)}

    def search_yahoo(self, query):
        """Búsqueda en Yahoo"""
        try:
            url = f"https://search.yahoo.com/search?p={quote_plus(query)}"
            response = self.session.get(url, timeout=10)
            return {
                'engine': 'Yahoo',
                'html': response.text,
                'status': 'success'
            }
        except Exception as e:
            return {'engine': 'Yahoo', 'html': '', 'status': 'error', 'error': str(e)}


def ask_mistral_for_selector(html, engine_name):
    """Solicita a Mistral el selector CSS apropiado para cada motor de búsqueda"""
    prompt = f"""
            Eres un experto en análisis de HTML. Necesito extraer enlaces de noticias de los resultados de búsqueda de {engine_name}.
            
            Este es el HTML de la página (primeros 5000 caracteres):
            {html[:5000]}
            
            Analiza el HTML y devuelve ÚNICAMENTE el selector CSS más apropiado para extraer los enlaces principales de los resultados de búsqueda.
            Ejemplos de selectores comunes:
            - Para DuckDuckGo: 'a.result__a'
            - Para Bing: 'h2 a'
            - Para Yahoo: 'h3 a'
            
            Responde SOLO con el selector CSS, sin explicaciones adicionales.
    """

    try:
        response = ollama.chat(model='mistral', messages=[
            {"role": "user", "content": prompt}
        ])
        return response['message']['content'].strip()
    except Exception as e:
        print(f"❌ Error al consultar Mistral: {e}")
        return None


def extract_links(html, selector, base_url=None):
    """Extrae enlaces usando el selector proporcionado"""
    if not selector or not html:
        return []

    try:
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.select(selector)

        extracted_links = []
        for link in links:
            if link.has_attr('href'):
                href = link['href']

                # Convertir enlaces relativos a absolutos si es necesario
                if base_url and href.startswith('/'):
                    href = urljoin(base_url, href)

                # Filtrar enlaces que parecen ser de noticias o contenido relevante
                if href.startswith('http') and not any(x in href.lower() for x in ['ads', 'sponsored', 'promo']):
                    extracted_links.append({
                        'url': href,
                        'title': link.get_text().strip() if link.get_text() else 'Sin título'
                    })

        return extracted_links
    except Exception as e:
        print(f"❌ Error extrayendo enlaces: {e}")
        return []


def search_all_engines(query, engines_to_use=None):
    """Busca en todos los motores de búsqueda especificados"""
    searcher = MultiSearchEngine()

    # Motores disponibles
    available_engines = {
        'duckduckgo': searcher.search_duckduckgo,
        'bing': searcher.search_bing,
        'yandex': searcher.search_yandex,
        'startpage': searcher.search_startpage,
        'searx': searcher.search_searx,
        'yahoo': searcher.search_yahoo
    }

    # Si no se especifican motores, usar todos
    if engines_to_use is None:
        engines_to_use = list(available_engines.keys())

    results = {}

    for engine_name in engines_to_use:
        if engine_name in available_engines:
            print(f"🔍 Buscando en {engine_name.upper()}...")

            # Realizar búsqueda
            search_result = available_engines[engine_name](query)

            if search_result['status'] == 'success':
                # Obtener selector de Mistral
                selector = ask_mistral_for_selector(search_result['html'], search_result['engine'])

                if selector:
                    print(f"🔎 Selector para {engine_name}: {selector}")

                    # Extraer enlaces
                    links = extract_links(search_result['html'], selector)

                    results[engine_name] = {
                        'engine': search_result['engine'],
                        'selector': selector,
                        'links': links,
                        'count': len(links)
                    }

                    print(f"✅ {engine_name}: {len(links)} enlaces encontrados")
                else:
                    print(f"❌ No se pudo obtener selector para {engine_name}")
            else:
                print(f"❌ Error en {engine_name}: {search_result.get('error', 'Unknown error')}")

            # Pausa entre búsquedas para evitar rate limiting
            time.sleep(random.uniform(1, 3))

    return results


def display_results(results):
    """Muestra los resultados de forma organizada"""
    total_links = 0

    print("\n" + "=" * 80)
    print("📊 RESUMEN DE RESULTADOS")
    print("=" * 80)

    for engine_name, data in results.items():
        print(f"\n🔍 Motor: {data['engine']}")
        print(f"📋 Selector: {data['selector']}")
        print(f"🔗 Enlaces encontrados: {data['count']}")

        if data['links']:
            print("\n📰 Primeros 5 enlaces:")
            for i, link in enumerate(data['links'][:5], 1):
                print(f"   {i}. {link['title'][:80]}...")
                print(f"      🔗 {link['url']}")

        total_links += data['count']
        print("-" * 40)

    print(f"\n🎯 Total de enlaces encontrados: {total_links}")


# Ejemplo de uso principal
if __name__ == "__main__":
    # Configurar búsqueda
    query = "noticias sobre inteligencia artificial 2025"

    # Puedes especificar qué motores usar
    engines_to_search = ['duckduckgo', 'bing', 'yahoo']  # o None para todos

    print(f"🚀 Iniciando búsqueda: '{query}'")
    print(f"🎯 Motores seleccionados: {engines_to_search or 'Todos'}")

    # Realizar búsqueda
    results = search_all_engines(query, engines_to_search)

    # Mostrar resultados
    display_results(results)

    # Opcional: Guardar resultados en JSON
    with open('search_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Resultados guardados en 'search_results.json'")