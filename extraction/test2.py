import ollama
from pydantic import BaseModel

class ImprovedQuery(BaseModel):
    title: str


prompt = f"""
        Mejora este título de búsqueda de noticias para que sea más efectivo y amplio: Noticias sobre exploracion espacial y el espacio.
        Enfócate en términos que produzcan resultados de alta calidad y relevancia internacional, damelo en español.
        """

response = ollama.chat(
    model='llama3.2',
    messages=[
        {
            'role': 'user',
            'content': prompt
        }
    ],
    format=ImprovedQuery.model_json_schema() # Aquí pasas el esquema JSON
)

# Puedes validar y usar la respuesta con Pydantic
pais_data = ImprovedQuery.model_validate_json(response['message']['content'])
print(pais_data.title)