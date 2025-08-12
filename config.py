# config.py
# ==============================================================================
# == CONFIGURACIÓN CENTRALIZADA DEL PROYECTO
# ==============================================================================

# --- Rutas de Bases de Datos ---
# Se recomienda crear un directorio 'data/' para almacenarlas.
DB_PATH = "data/pipeline.db"

# --- Configuración del Modelo de IA ---
OLLAMA_MODEL = "qwen3:0.6b"

# --- Configuración del Pipeline ---
# Número máximo de resultados a buscar por motor
MAX_SEARCH_RESULTS = 25
# Límite de artículos a extraer
EXTRACTION_LIMIT = 50
# Número de hilos para la extracción
EXTRACTION_WORKERS = 5
# Calificación mínima para resumir noticias
MIN_RATING_FOR_SUMMARY = 8
# Calificación mínima para generar guiones
MIN_RATING_FOR_SCRIPT = 9
# Límite de noticias para resumir/guionizar
TOP_NEWS_LIMIT = 5

