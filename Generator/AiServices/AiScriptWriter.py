# Generator/AiServices/AiScriptWriter.py
import ollama

from Generator.Models.Script import Script
import json


class AIScriptWriter:
    def __init__(self, model_name: str, context_window: int = 8192):
        self.model_name = model_name
        self.context_window = context_window

    def create_script(self, query: str) -> Script:

        print(f"🚀 INICIANDO procesamiento de query: '{query[:50]}...'")

        prompt = f"""
            A partir del siguiente contenido:
            {query}
            Genera un texto para un narrador de noticias resumiento el contenido. El texto debe ser extenso según sea necesario, directo, en minúsculas y en un solo párrafo.No incluyas saludos ya que hay mas noticias. El texto resultante debe ser únicamente el que debe decir el narrador, ya que se utilizará para un sistema de texto a voz. Ejemplo de formato: 'científicos investigan un parásito que manipula el cerebro suprimiendo el miedo, como en roedores infectados que pierden el miedo instintivo a los gatos'
        """

        try:
            # Configuración de opciones para aumentar la ventana de contexto
            options = {
                'num_ctx': self.context_window,  # Ventana de contexto
                'temperature': 0.7,  # Creatividad del modelo
                'top_p': 0.9,  # Diversidad de respuestas
                'top_k': 40,  # Selección de tokens
                'repeat_penalty': 1.1,  # Penalización por repetición
                'num_predict': 8192,  # Máximo de tokens en la respuesta
            }

            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=Script.model_json_schema(),
                options=options
            )

            script = Script.model_validate_json(response['message']['content'])

            print(f"📋 Guion generado: '{script.text[:100]}...'")
            return script

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error al generar el script: {e}. Usando la consulta original.")
            return Script(text=query)  # Corregido: usar 'text' en lugar de 'guion'
        except Exception as e:
            print(f"Error inesperado: {e}")
            return Script(text=query)

    def set_context_window(self, size: int):
        """Permite cambiar el tamaño de la ventana de contexto dinámicamente"""
        self.context_window = size
        print(f"🔧 Ventana de contexto ajustada a: {size}")

    def get_model_info(self):
        """Obtiene información del modelo incluyendo la ventana de contexto actual"""
        try:
            model_info = ollama.show(self.model_name)
            return {
                'model': self.model_name,
                'context_window': self.context_window,
                'model_details': model_info
            }
        except Exception as e:
            print(f"Error al obtener información del modelo: {e}")
            return {
                'model': self.model_name,
                'context_window': self.context_window,
                'error': str(e)
            }