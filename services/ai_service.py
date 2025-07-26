# services/ai_service.py
# ==============================================================================
# == SERVICIO DE INTERACCIÓN CON EL MODELO DE LENGUAJE (IA)
# ==============================================================================

import ollama
import json
from pydantic import ValidationError
from core.models import ImprovedQuery, NewsEvaluation, ScriptFragment


class AIService:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def improve_search_query(self, query: str) -> ImprovedQuery:
        prompt = f"""Mejora este título de búsqueda de noticias para que sea más efectivo y amplio: "{query}".
        Enfócate en términos que produzcan resultados de alta calidad y relevancia internacional, dando el resultado en español."""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=ImprovedQuery.model_json_schema()
            )
            return ImprovedQuery.model_validate_json(response['message']['content'])
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            print(f"Error al mejorar la consulta: {e}. Usando la consulta original.")
            return ImprovedQuery(titulo_mejorado=query)

    def evaluate_news_article(self, article: dict, target_search: str) -> NewsEvaluation:
        prompt = f"""Eres un analista de noticias. Evalúa la relevancia del siguiente artículo en relación con la búsqueda objetivo "{target_search}" y su importancia internacional.
        Título: "{article.get('titulo', '')}"
        Contenido: "{article.get('contenido', '')[:500]}..."
        Decide si debe 'mantener' o 'eliminar'. Si es relevante, asigna una calificación de 1 a 10."""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=NewsEvaluation.model_json_schema()
            )
            return NewsEvaluation.model_validate_json(response['message']['content'])
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            print(f"Error en la evaluación: {e}. Por defecto: 'mantener', calificación 5.")
            return NewsEvaluation(accion="mantener", calificacion=5)

    def generate_script_fragment(self, title: str, content: str) -> ScriptFragment:
        prompt = f"""Genera un fragmento de guion para un video de noticias a partir de este artículo:
        Título: "{title}"
        Contenido: "{content}"
        El guion debe ser corto, directo, en minúsculas y en un solo párrafo. Reemplaza siglas como NASA por N A S A."""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                format=ScriptFragment.model_json_schema()
            )
            return ScriptFragment.model_validate_json(response['message']['content'])
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            return ScriptFragment(guion=f"Error al generar guion: {e}")

    def summarize_top_news(self, articles: list) -> str:
        resumenes = "\n---\n".join([f"Título: {t}\nFuente: {f}\nContenido: {c[:300]}..." for t, f, c in articles])
        prompt = f"Genera un resumen conciso de los puntos más importantes de estas noticias:\n{resumenes}"
        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            return response['message']['content']
        except Exception as e:
            return f"❌ Error al generar resumen: {e}"