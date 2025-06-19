import os
import re
import torch
from TTS.api import TTS
import nltk
from nltk.tokenize import sent_tokenize
import time
from datetime import datetime


class SimpleTTSGenerator:
    def __init__(self, output_dir="audio_output",
                 model="tts_models/multilingual/multi-dataset/xtts_v2"):
        """Initialize the TTS generator."""
        self.output_dir = output_dir
        self.model_name = model

        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Try to download NLTK tokenizers if not already present
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            print("Downloading NLTK punkt tokenizer...")
            nltk.download('punkt')

        # Initialize TTS
        self._setup_tts()

    def _setup_tts(self):
        """Setup TTS model with proper configurations."""
        print("⏳ Setting up TTS model...")
        # Apply the torch.load patch to avoid weights_only issue
        torch_load = torch.load  # Save the original reference

        def safe_torch_load(*args, **kwargs):
            kwargs["weights_only"] = False  # Disable weights_only
            return torch_load(*args, **kwargs)

        # Replace torch.load temporarily
        torch.load = safe_torch_load

        # Get device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🖥️ Using device: {device}")

        # Initialize TTS model
        self.tts = TTS(self.model_name).to(device)

        # Restore torch.load to its original state
        torch.load = torch_load
        print("✅ TTS model loaded successfully!")

    def _chunk_text(self, text, max_length=239):
        """
        Split text into chunks that respect sentence boundaries and max_length.
        Uses NLTK's sentence tokenizer to avoid cutting sentences in the middle.
        """
        # Remove excessive spaces and normalize text
        text = re.sub(r'\s+', ' ', text).strip()

        # Get sentences using NLTK
        sentences = sent_tokenize(text, language='spanish')

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # If the sentence itself is too long, split it by punctuation
            if len(sentence) > max_length:
                sub_parts = re.split(r'([,:;])', sentence)

                # Rejoin the split parts with their punctuation
                parts = []
                for i in range(0, len(sub_parts) - 1, 2):
                    if i + 1 < len(sub_parts):
                        parts.append(sub_parts[i] + sub_parts[i + 1])
                    else:
                        parts.append(sub_parts[i])

                # If there's an odd number of elements, add the last one
                if len(sub_parts) % 2 != 0:
                    parts.append(sub_parts[-1])

                # Process each part
                for part in parts:
                    if len(current_chunk) + len(part) + 1 <= max_length:
                        current_chunk += " " + part if current_chunk else part
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = part

            # Normal case: try to add the whole sentence
            elif len(current_chunk) + len(sentence) + 1 <= max_length:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                chunks.append(current_chunk.strip())
                current_chunk = sentence

        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _combine_audio_files(self, input_files, output_file):
        """
        Combine multiple WAV files into one.
        Requires pydub library (pip install pydub).
        """
        try:
            from pydub import AudioSegment
            print(f"🔄 Combining {len(input_files)} audio files...")

            combined = AudioSegment.empty()
            for file in input_files:
                audio = AudioSegment.from_wav(file)
                combined += audio

            combined.export(output_file, format="wav")
            print(f"✅ Combined audio saved to: {output_file}")
            return True
        except ImportError:
            print("⚠️ pydub library not found. Install with: pip install pydub")
            return False
        except Exception as e:
            print(f"❌ Error combining audio files: {e}")
            return False

    def generate_speech(self, text, speaker_wav_path, output_filename=None, language="es",
                        force_single_file=True, max_length=None):
        """
        Generate speech from text using the provided voice sample.

        Args:
            text (str): Text to convert to speech
            speaker_wav_path (str): Path to the voice sample WAV file
            output_filename (str): Optional custom output filename
            language (str): Language code (default: "es" for Spanish)
            force_single_file (bool): If True, generates a single audio file regardless of text length
            max_length (int): Maximum text length before chunking (None = no limit when force_single_file=True)

        Returns:
            str: Path to generated audio file
        """
        # Validate inputs
        if not os.path.exists(speaker_wav_path):
            raise FileNotFoundError(f"Voice sample not found: {speaker_wav_path}")

        if not text.strip():
            raise ValueError("Text cannot be empty")

        print(f"🎙️ Using voice sample: {os.path.basename(speaker_wav_path)}")
        print(f"📝 Text length: {len(text)} characters")

        # Generate output filename if not provided
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"generated_speech_{timestamp}"

        # Remove file extension if provided
        output_filename = os.path.splitext(output_filename)[0]
        output_file = os.path.join(self.output_dir, f"{output_filename}.wav")

        # If force_single_file is True or text is within limits, generate single file
        if force_single_file or (max_length and len(text) <= max_length) or len(text) <= 239:
            print(f"🎯 Generating single audio file...")

            # Clean periods (replace with commas to improve speech flow)
            cleaned_text = re.sub(r'(?<!\d)\.(?!\d)', ',', text)

            try:
                # Generate audio directly
                self.tts.tts_to_file(
                    text=cleaned_text,
                    speaker_wav=speaker_wav_path,
                    language=language,
                    file_path=output_file
                )

                print(f"✅ Audio saved to: {output_file}")
                return output_file

            except Exception as e:
                print(f"❌ Error generating audio: {e}")
                # If single file generation fails and text is long, try chunking as fallback
                if len(text) > 239:
                    print("⚠️ Single file generation failed, falling back to chunking...")
                    return self._generate_chunked_audio(text, speaker_wav_path, output_filename, language)
                else:
                    raise e

        # If not forcing single file and text is long, use chunking
        else:
            return self._generate_chunked_audio(text, speaker_wav_path, output_filename, language)

    def _generate_chunked_audio(self, text, speaker_wav_path, output_filename, language):
        """Generate audio using chunks and combine them."""
        print(f"📏 Text exceeds recommended limit ({len(text)} chars), using chunking approach...")
        chunks = self._chunk_text(text)
        print(f"🧩 Split into {len(chunks)} chunks")

        # Generate audio for each chunk
        chunk_files = []
        for i, chunk in enumerate(chunks):
            chunk_file = os.path.join(self.output_dir, f"{output_filename}_temp_part{i + 1}.wav")
            print(f"🔊 Generating chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")

            cleaned_chunk = re.sub(r'(?<!\d)\.(?!\d)', ',', chunk)

            self.tts.tts_to_file(
                text=cleaned_chunk,
                speaker_wav=speaker_wav_path,
                language=language,
                file_path=chunk_file
            )

            chunk_files.append(chunk_file)
            time.sleep(0.5)  # Small pause between processing

        # Combine chunks into single file
        combined_file = os.path.join(self.output_dir, f"{output_filename}.wav")
        success = self._combine_audio_files(chunk_files, combined_file)

        # Clean up temporary chunk files
        for chunk_file in chunk_files:
            try:
                os.remove(chunk_file)
            except:
                pass

        if success:
            print(f"✅ Final audio saved to: {combined_file}")
            return combined_file
        else:
            raise Exception("Failed to combine audio chunks into single file")


# Ejemplo de uso
if __name__ == "__main__":
    # Inicializar el generador
    tts_gen = SimpleTTSGenerator()

    # Texto a generar (puede ser muy largo)
    text = """ !Hola eres Juan el de tinder ?!.
    """

    # Ruta al archivo de voz de referencia
    voice_sample = "./voice_sources/tatiana.wav"  # Cambia por tu archivo de voz

    try:
        # Generar el audio (siempre un solo archivo)
        result = tts_gen.generate_speech(
            text=text,
            speaker_wav_path=voice_sample,
            output_filename="mi_audio_completo",
            force_single_file=True  # Por defecto ya es True
        )

        print(f"\n🎉 ¡Audio generado exitosamente!")
        print(f"📁 Archivo de audio: {result}")

    except Exception as e:
        print(f"❌ Error: {e}")