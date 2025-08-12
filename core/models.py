# core/models.py
# ==============================================================================
# == MODELOS PYDANTIC PARA LA SALIDA ESTRUCTURADA
# ==============================================================================

from pydantic import BaseModel, Field, conint, ValidationError
from typing import Literal, Optional

class ImprovedQuery(BaseModel):
    """Define la estructura para la consulta de búsqueda mejorada por la IA."""
    titulo_mejorado: str = Field(description="El título de búsqueda de noticias mejorado y optimizado.")

class NewsEvaluation(BaseModel):
    """Define la estructura para la evaluación de una noticia."""
    accion: Literal["mantener", "eliminar"] = Field(description="La acción a tomar con el artículo.")
    calificacion: Optional[conint(ge=1, le=10)] = Field(
        default=None,
        description="Calificación de relevancia de 1 a 10, solo si la acción es 'mantener'."
    )

class ScriptFragment(BaseModel):
    """Define la estructura para el guion generado por la IA."""
    guion: str = Field(description="Fragmento de guion corto, directo, en minúsculas y en un solo párrafo, no incluyas hace cuanto fue la noticia, solo el guion")