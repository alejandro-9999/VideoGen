import gradio as gr
from TTS.api import TTS
import tempfile

api = TTS(model_name="voice_conversion_models/multilingual/vctk/freevc24")

def greet(source, target):
    path = tempfile.NamedTemporaryFile(prefix="bttm_", suffix=".wav").name

    print("adio", source, target, path)
    api.voice_conversion_to_file(source_wav=source, target_wav=target, file_path=path)
    print("> Done")

    return path


