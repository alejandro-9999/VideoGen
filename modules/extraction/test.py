import ollama
from pydantic import BaseModel

class Pais(BaseModel):
    nombre: str
    capital: str
    idiomas: list[str]

response = ollama.chat(
    model='mistral',
    messages=[
        {
            'role': 'user',
            'content': 'Dime sobre Cuba.'
        }
    ],
    format=Pais.model_json_schema() # Aquí pasas el esquema JSON
)

# Puedes validar y usar la respuesta con Pydantic
pais_data = Pais.model_validate_json(response['message']['content'])
print(pais_data.nombre)
print(pais_data.capital)
print(pais_data.idiomas)