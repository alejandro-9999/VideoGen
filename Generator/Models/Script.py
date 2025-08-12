# Generator/Models/Script.py
from pydantic import BaseModel, Field

class Script(BaseModel):
    """Define la estructura para el guion de la noticia"""
    text : str = Field(description="Texto a narrare , directo, en minúsculas y en un solo párrafo")
