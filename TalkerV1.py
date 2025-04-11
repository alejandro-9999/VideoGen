import os
import sqlite3
import re
import torch
from TTS.api import TTS
import nltk
from nltk.tokenize import sent_tokenize
import time
from datetime import datetime

# Try to download NLTK tokenizers if not already present
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')


class ScriptAudioGenerator:
    def __init__(self, db_name="data.db", output_dir="audio_output",
                 model="tts_models/multilingual/multi-dataset/xtts_v2", voice_sources=None):
        """Initialize the audio generator with database settings."""
        self.db_name = db_name
        self.output_dir = output_dir
        self.model_name = model

        # Default voice sources if none provided
        self.voice_sources = voice_sources or [
            "./voice_sources/vocal_1.wav",
            "./voice_sources/vocal_2.wav",
            "./voice_sources/vocal_3.wav",
            "./voice_sources/vocal_4.wav"
        ]

        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

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

    def _get_scripts_from_db(self):
        """Fetch all scripts from the database."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT id, titulo, guion FROM scripts")
        scripts = cursor.fetchall()
        conn.close()
        return scripts

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

    def _generate_audio_for_script(self, script_id, title, text, voice_idx=0):
        """Generate audio for a script, chunking it if necessary."""
        print(f"\n🎬 Processing script ID {script_id}: {title}")

        # Create a unique filename for this script
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().lower()
        safe_title = re.sub(r'[-\s]+', '-', safe_title)
        base_filename = f"{script_id}_{safe_title[:30]}"

        # Select voice to use (cycling through available voices)
        speaker_wav = self.voice_sources[voice_idx % len(self.voice_sources)]
        print(f"🎙️ Using voice source: {os.path.basename(speaker_wav)}")

        # Check if text needs chunking
        if len(text) <= 239:
            print(f"📝 Text is within limit ({len(text)} chars)")
            output_file = os.path.join(self.output_dir, f"{base_filename}.wav")

            # 🧼 Limpiar puntos
            cleaned_text = re.sub(r'(?<!\d)\.(?!\d)', '', text)

            # Generate audio
            self.tts.tts_to_file(
                text=cleaned_text,
                speaker_wav=self.voice_sources,
                language="es",
                file_path=output_file
            )
            print(f"✅ Audio saved to: {output_file}")
            return [output_file]

        # If text is too long, chunk it
        print(f"📏 Text exceeds limit ({len(text)} chars), chunking...")
        chunks = self._chunk_text(text)
        print(f"🧩 Split into {len(chunks)} chunks")

        # Generate audio for each chunk
        chunk_files = []
        for i, chunk in enumerate(chunks):
            chunk_file = os.path.join(self.output_dir, f"{base_filename}_part{i + 1}.wav")
            print(f"🔊 Generating chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")

            cleaned_chunk = re.sub(r'(?<!\d)\.(?!\d)', ',', chunk)
            self.tts.tts_to_file(
                text=cleaned_chunk,
                speaker_wav=speaker_wav,
                language="es",
                file_path=chunk_file
            )

            chunk_files.append(chunk_file)

            # Small pause between processing to avoid overloading
            time.sleep(0.5)

        print(f"✅ Generated {len(chunk_files)} audio files for script {script_id}")
        return chunk_files

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

    def process_all_scripts(self, combine_chunks=True):
        """Process all scripts in the database and generate audio for each."""
        scripts = self._get_scripts_from_db()

        if not scripts:
            print("⚠️ No scripts found in the database.")
            return

        print(f"🎯 Found {len(scripts)} scripts to process")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.output_dir, f"generation_log_{timestamp}.txt")

        all_audio_files = []

        with open(log_file, "w", encoding="utf-8") as log:
            log.write(f"Audio Generation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'=' * 80}\n\n")

            for i, (script_id, title, text) in enumerate(scripts):
                log.write(f"Script {script_id}: {title}\n")
                log.write(f"Text: {text}\n")

                voice_idx = i % len(self.voice_sources)
                audio_files = self._generate_audio_for_script(script_id, title, text, voice_idx)

                if len(audio_files) > 1 and combine_chunks:
                    try:
                        import pydub
                        combined_file = os.path.join(self.output_dir,
                                                     f"{script_id}_{title[:30].replace(' ', '_')}_combined.wav")
                        success = self._combine_audio_files(audio_files, combined_file)

                        if success:
                            log.write(f"Combined audio: {combined_file}\n")
                            all_audio_files.append(combined_file)
                        else:
                            log.write(f"Failed to combine audio chunks\n")
                            all_audio_files.extend(audio_files)
                    except ImportError:
                        log.write("pydub not installed, cannot combine chunks\n")
                        all_audio_files.extend(audio_files)
                else:
                    log.write(f"Audio file(s): {', '.join(audio_files)}\n")
                    all_audio_files.extend(audio_files)

                log.write(f"{'-' * 80}\n\n")

        # 🔊 COMBINAR TODO EN UN SOLO ARCHIVO
        if all_audio_files:
            final_output_file = os.path.join(self.output_dir, f"final_combined_output_{timestamp}.wav")
            success = self._combine_audio_files(all_audio_files, final_output_file)
            if success:
                print(f"\n🎉 Final combined audio saved to: {final_output_file}")
            else:
                print("❌ Failed to create final combined audio.")

        print(f"📋 Processing log saved to: {log_file}")
        print(f"✅ Processed {len(scripts)} scripts successfully!")


if __name__ == "__main__":
    # You can customize these paths if needed
    VOICE_SOURCES = [
        "./voice_sources/vocal_1.wav",
        "./voice_sources/vocal_2.wav",
        "./voice_sources/vocal_3.wav",
        "./voice_sources/vocal_4.wav"
    ]

    # Initialize and run the generator
    generator = ScriptAudioGenerator(
        db_name="data.db",
        output_dir="audio_output",
        voice_sources=VOICE_SOURCES
    )

    # Process all scripts in the database
    generator.process_all_scripts(combine_chunks=True)