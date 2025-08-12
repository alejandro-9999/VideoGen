# Generator/AiServices/AiScriptWriter.py
import ollama

from Generator.Models.Script import Script
import json


class AIScriptWriter:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def create_script(self, query: str) -> Script:

        print(f"🚀 INICIANDO procesamiento de query: '{query[:50]}...'")

        prompt = f"""
            A partir del siguiente contenido:
            {query}
            Genera un texto para un narrador de noticias. El texto debe ser extenso según sea necesario, directo, en minúsculas y en un solo párrafo.No incluyas saludos ya que hay mas noticias, Reemplaza siglas como NASA por N A S A. El texto resultante debe ser únicamente el que debe decir el narrador, ya que se utilizará para un sistema de texto a voz. Ejemplo de formato: 'científicos investigan un parásito que manipula el cerebro suprimiendo el miedo, como en roedores infectados que pierden el miedo instintivo a los gatos'
        """

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=Script.model_json_schema()
            )
            script = Script.model_validate_json(response['message']['content'])

            print(f"📋 Guion generado: '{script.text[:100]}...'")
            return script
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error al mejorar la consulta: {e}. Usando la consulta original.")
            return Script(guion=query)