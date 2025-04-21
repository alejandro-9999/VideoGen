import torch
from TTS.api import TTS

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"

# List available 🐸TTS models
print(TTS().list_models())

# Forzar la carga completa del modelo
torch_load = torch.load  # Guardar la referencia original
def safe_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False  # Desactivar weights_only
    return torch_load(*args, **kwargs)

torch.load = safe_torch_load  # Reemplazar torch.load temporalmente

# Init TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Restaurar torch.load a su estado original
torch.load = torch_load


text_to_describe = "este musgo chino del desierto, el syntrichia caninervis, puede soportar temperaturas hasta -196 grados celsius y resistir mas de 5000 Gy de radiacion gamma. ademas, puede sobrevivir en condiciones de deshidratacion total y regenerarse cuando las condiciones mejoran. estas cualidades lo convierten en un posible pionero en la terraformacion marciana"

# Run TTS
# wav = tts.tts(text=text_to_describe, speaker_wav="./audio.wav", language="es")
tts.tts_to_file(text=text_to_describe,
                speaker_wav=[
                    "./voice_sources/vocal_1.wav",
                    "./voice_sources/vocal_2.wav",
                    "./voice_sources/vocal_3.wav",
                    "./voice_sources/vocal_4.wav"
                ],
                language="es",
                file_path="output.wav")
