import os
import json
import sqlite3
import requests
import random
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import *
from duckduckgo_search import DDGS
from io import BytesIO
import ollama


class VideoGenerator:
    def __init__(self, db_name="data.db", output_dir="video_output",
                 audio_dir="audio_output", images_dir="images_cache",
                 model="mistral"):
        """Initialize the video generator with database and directory settings."""
        self.db_name = db_name
        self.output_dir = output_dir
        self.audio_dir = audio_dir
        self.images_dir = images_dir
        self.model_name = model

        # Create necessary directories if they don't exist
        for directory in [output_dir, images_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

        # Font for captions
        try:
            # Try to load a font that supports Spanish characters
            self.font_path = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf")
            if not os.path.exists(self.font_path):
                # Create fonts directory if it doesn't exist
                os.makedirs(os.path.dirname(self.font_path), exist_ok=True)
                # Use a system font as fallback
                system_fonts = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                    "/Library/Fonts/Arial.ttf",  # MacOS
                    "C:\\Windows\\Fonts\\Arial.ttf"  # Windows
                ]
                for font in system_fonts:
                    if os.path.exists(font):
                        self.font_path = font
                        break
        except Exception as e:
            print(f"⚠️ Font loading error: {e}. Will use default font.")
            self.font_path = None

    def _fetch_scripts_with_audio(self):
        """Fetch scripts that have corresponding audio files."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT id, titulo, guion FROM scripts")
        scripts = cursor.fetchall()
        conn.close()

        scripts_with_audio = []
        for script_id, title, text in scripts:
            # Look for either combined audio or individual chunks
            safe_title = self._sanitize_filename(title)
            base_filename = f"{script_id}_{safe_title[:30]}"

            # Check for combined file first
            combined_pattern = f"{script_id}_{safe_title[:30]}_combined.wav"
            combined_files = [f for f in os.listdir(self.audio_dir)
                              if f.startswith(f"{script_id}_") and "_combined.wav" in f]

            if combined_files:
                audio_path = os.path.join(self.audio_dir, combined_files[0])
                scripts_with_audio.append((script_id, title, text, audio_path))
            else:
                # Look for individual chunks
                chunk_files = sorted([f for f in os.listdir(self.audio_dir)
                                      if f.startswith(f"{script_id}_{safe_title[:30]}_part")])
                if chunk_files:
                    audio_paths = [os.path.join(self.audio_dir, f) for f in chunk_files]
                    scripts_with_audio.append((script_id, title, text, audio_paths))

        return scripts_with_audio

    def _sanitize_filename(self, filename):
        """Create a safe filename from a title."""
        # Remove invalid characters and replace spaces with underscores
        safe_name = ''.join(c if c.isalnum() or c in ' -_' else '' for c in filename)
        safe_name = safe_name.replace(' ', '_').lower()
        return safe_name

    def _search_images(self, query, num_images=3):
        """Search for images related to the script topic."""
        print(f"🔍 Searching for images: {query}")

        # Generate search keywords based on the script
        search_query = self._generate_image_search_query(query)

        # Create cache subdirectory for this query
        query_hash = str(abs(hash(search_query)))[:10]
        cache_subdir = os.path.join(self.images_dir, query_hash)
        if not os.path.exists(cache_subdir):
            os.makedirs(cache_subdir)

        # Check if we already have images for this query
        cached_images = [os.path.join(cache_subdir, f) for f in os.listdir(cache_subdir)
                         if f.endswith(('.jpg', '.jpeg', '.png'))]

        if len(cached_images) >= num_images:
            print(f"✅ Found {len(cached_images)} cached images")
            # Return random selection if we have more than we need
            if len(cached_images) > num_images:
                return random.sample(cached_images, num_images)
            return cached_images

        # We need to search for new images
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(
                    search_query,
                    safesearch="on",
                    size=None,  # Any size
                    type_image=None,  # Any type
                    layout=None,  # Any layout
                    license_image=None,  # Any license
                    max_results=num_images * 2  # Get more than we need to account for failures
                ))

            print(f"📊 Found {len(results)} image results")

            # Download and save images
            downloaded_images = []
            for idx, result in enumerate(results):
                if len(downloaded_images) >= num_images:
                    break

                try:
                    image_url = result["image"]
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    response = requests.get(image_url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        # Validate it's actually an image
                        try:
                            img = Image.open(BytesIO(response.content))
                            # Save the image to our cache directory
                            img_path = os.path.join(cache_subdir, f"img_{idx + 1}.jpg")
                            img.save(img_path)
                            downloaded_images.append(img_path)
                            print(f"✅ Downloaded image {len(downloaded_images)}/{num_images}")
                        except Exception as e:
                            print(f"⚠️ Invalid image format: {e}")
                            continue
                    else:
                        print(f"⚠️ Failed to download image: HTTP {response.status_code}")
                except Exception as e:
                    print(f"⚠️ Error downloading image: {e}")

                # Small pause to avoid overloading servers
                time.sleep(0.5)

            if downloaded_images:
                return downloaded_images

            # If we couldn't download any images, use placeholder images
            print("⚠️ Could not download any images, using placeholders")
            return self._generate_placeholder_images(query, num_images, cache_subdir)

        except Exception as e:
            print(f"❌ Image search failed: {e}")
            return self._generate_placeholder_images(query, num_images, cache_subdir)

    def _generate_image_search_query(self, script_text):
        """Generate relevant image search terms from the script text."""
        prompt = f"""
        A partir del siguiente texto de noticia, genera términos de búsqueda para encontrar imágenes relevantes.
        Texto: "{script_text}"
        Responde en formato JSON con una lista de términos de búsqueda en español, incluyendo:
        1. Un término general que describa el tema principal
        2. Términos específicos relacionados con los elementos visuales mencionados
        Ejemplo de respuesta:
        {{
            "termino_principal": "exploración espacial marte",
            "terminos_especificos": ["rover perseverance en marte", "superficie marciana", "nasa exploración"]
        }}
        """

        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            data = json.loads(response['message']['content'])

            main_term = data.get("termino_principal", "")
            specific_terms = data.get("terminos_especificos", [])

            # Return the main term and one random specific term if available
            if specific_terms:
                return f"{main_term} {random.choice(specific_terms)}"
            return main_term
        except Exception as e:
            print(f"⚠️ Error generating search terms: {e}")
            # Extract keywords as fallback
            words = script_text.split()
            if len(words) > 5:
                return " ".join(random.sample(words, 5))
            return script_text

    def _generate_placeholder_images(self, text, num_images, cache_dir):
        """Generate simple placeholder images with text."""
        image_paths = []
        colors = [(255, 200, 100), (100, 200, 255), (200, 255, 100),
                  (255, 100, 200), (100, 255, 200)]

        for i in range(num_images):
            # Create a colored background with text
            img = Image.new('RGB', (1280, 720), color=random.choice(colors))
            draw = ImageDraw.Draw(img)

            # Add some text from the script
            if self.font_path:
                try:
                    font = ImageFont.truetype(self.font_path, 40)
                    # Extract a portion of the text for the placeholder
                    words = text.split()
                    if len(words) > 10:
                        placeholder_text = " ".join(words[i * 10 % len(words):(i + 1) * 10 % len(words)])
                    else:
                        placeholder_text = text

                    # Draw text
                    draw.text((100, 300), placeholder_text, fill=(0, 0, 0), font=font)
                except Exception as e:
                    print(f"⚠️ Font error: {e}. Using default text")
                    draw.text((100, 300), f"Placeholder Image {i + 1}", fill=(0, 0, 0))
            else:
                draw.text((100, 300), f"Placeholder Image {i + 1}", fill=(0, 0, 0))

            # Save the image
            img_path = os.path.join(cache_dir, f"placeholder_{i + 1}.jpg")
            img.save(img_path)
            image_paths.append(img_path)

        return image_paths

    def _create_video(self, script_id, title, text, audio_path, output_file):
        """Create a video with the script audio and related images."""
        print(f"\n🎬 Creating video for script {script_id}: {title}")

        # Get images related to the script
        images = self._search_images(text, num_images=5)
        if not images:
            print("❌ No images available for video creation")
            return None

        # Load the audio file(s)
        if isinstance(audio_path, list):
            # Multiple audio chunks
            print(f"🔊 Loading {len(audio_path)} audio chunks")
            audio_clips = [AudioFileClip(path) for path in audio_path]
            audio_clip = concatenate_audioclips(audio_clips)
        else:
            # Single audio file
            print(f"🔊 Loading audio: {os.path.basename(audio_path)}")
            audio_clip = AudioFileClip(audio_path)

        # Calculate total duration of the audio
        audio_duration = audio_clip.duration
        print(f"⏱️ Audio duration: {audio_duration:.2f} seconds")

        # Calculate how long each image should be shown
        num_images = len(images)
        image_duration = audio_duration / num_images

        # Create image clips
        image_clips = []
        for i, img_path in enumerate(images):
            try:
                # Calculate start and end times for this image
                start_time = i * image_duration
                end_time = (i + 1) * image_duration
                if i == num_images - 1:
                    # Make sure the last image extends to the end of the audio
                    end_time = audio_duration

                # Create ImageClip with proper duration
                img_clip = ImageClip(img_path).set_duration(end_time - start_time)

                # Resize to 1280x720 (16:9) maintaining aspect ratio
                img_clip = img_clip.resize(height=720)
                # If width is greater than 1280, crop to 1280
                if img_clip.size[0] > 1280:
                    img_clip = img_clip.crop(x1=(img_clip.size[0] - 1280) // 2, y1=0,
                                             x2=(img_clip.size[0] + 1280) // 2, y2=720)
                # If width is less than 1280, pad with black
                elif img_clip.size[0] < 1280:
                    # Create a black background
                    bg = ColorClip(size=(1280, 720), color=(0, 0, 0))
                    bg = bg.set_duration(img_clip.duration)
                    # Position the image in the center
                    img_clip = img_clip.set_position(('center', 'center'))
                    img_clip = CompositeVideoClip([bg, img_clip])

                # Add a title caption to the first image
                if i == 0:
                    txt_clip = TextClip(title, fontsize=30, color='white', bg_color='rgba(0,0,0,0.5)',
                                        font=self.font_path if self.font_path else None)
                    txt_clip = txt_clip.set_position(('center', 'bottom')).set_duration(end_time - start_time)
                    img_clip = CompositeVideoClip([img_clip, txt_clip])

                # Set the position to match the audio timing
                img_clip = img_clip.set_start(start_time)

                image_clips.append(img_clip)
                print(f"✅ Added image {i + 1}/{num_images}")

            except Exception as e:
                print(f"❌ Error processing image {img_path}: {e}")
                continue

        if not image_clips:
            print("❌ No valid image clips to create video")
            return None

        # Create final video
        try:
            video = CompositeVideoClip(image_clips)
            video = video.set_audio(audio_clip)

            # Add a fade in/out effect
            video = video.fadein(0.5).fadeout(0.5)

            # Write the final video file
            print(f"💾 Rendering video to {output_file}")
            video.write_videofile(output_file, fps=24, codec='libx264',
                                  audio_codec='aac', preset='medium')

            # Close clips to free memory
            video.close()
            audio_clip.close()
            for clip in image_clips:
                clip.close()

            print(f"✅ Video saved to: {output_file}")
            return output_file

        except Exception as e:
            print(f"❌ Error creating video: {e}")
            return None

    def process_scripts_to_videos(self):
        """Process all scripts with audio files and create videos for each."""
        scripts = self._fetch_scripts_with_audio()

        if not scripts:
            print("⚠️ No scripts with audio found")
            return []

        print(f"🎯 Found {len(scripts)} scripts with audio to process")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.output_dir, f"video_generation_log_{timestamp}.txt")

        videos_created = []

        with open(log_file, "w", encoding="utf-8") as log:
            log.write(f"Video Generation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'=' * 80}\n\n")

            for script_id, title, text, audio_path in scripts:
                log.write(f"Script {script_id}: {title}\n")

                # Create output filename
                safe_title = self._sanitize_filename(title)
                output_file = os.path.join(self.output_dir, f"video_{script_id}_{safe_title[:30]}.mp4")

                # Create video
                result = self._create_video(script_id, title, text, audio_path, output_file)

                if result:
                    log.write(f"✅ Video created: {result}\n")
                    videos_created.append(result)
                else:
                    log.write(f"❌ Failed to create video\n")

                log.write(f"{'-' * 80}\n\n")

        print(f"📋 Video processing log saved to: {log_file}")
        print(f"🎥 Created {len(videos_created)} videos successfully!")

        return videos_created

    def combine_videos(self, videos_list, output_file=None):
        """Combine multiple videos into a single video."""
        if not videos_list:
            print("⚠️ No videos to combine")
            return None

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.output_dir, f"combined_videos_{timestamp}.mp4")

        try:
            print(f"🔄 Combining {len(videos_list)} videos...")

            # Load each video
            clips = [VideoFileClip(video) for video in videos_list]

            # Concatenate all clips
            final_clip = concatenate_videoclips(clips)

            # Add a short fade between clips
            # This is more complex and involves creating transitions between each clip
            # For simplicity we're just concatenating them directly

            # Write the final video
            print(f"💾 Rendering combined video to {output_file}")
            final_clip.write_videofile(output_file, codec='libx264', audio_codec='aac')

            # Close clips
            final_clip.close()
            for clip in clips:
                clip.close()

            print(f"✅ Combined video saved to: {output_file}")
            return output_file

        except Exception as e:
            print(f"❌ Error combining videos: {e}")
            return None