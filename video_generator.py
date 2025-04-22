import os
import json
import sqlite3
import requests
import random
import time
import ffmpeg
import subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
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

    def _create_title_image(self, title, img_path, output_path):
        """Add a title overlay to the image."""
        try:
            img = Image.open(img_path)
            # Create a semi-transparent overlay
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Draw a semi-transparent rectangle at the bottom
            draw.rectangle([(0, img.height - 100), (img.width, img.height)], fill=(0, 0, 0, 128))

            # Add text if font is available
            if self.font_path:
                try:
                    font = ImageFont.truetype(self.font_path, 40)
                    # Center text
                    text_width = draw.textlength(title, font=font)
                    text_position = ((img.width - text_width) // 2, img.height - 70)

                    draw.text(text_position, title, fill=(255, 255, 255, 255), font=font)
                except Exception as e:
                    print(f"⚠️ Font error when adding title: {e}")
                    # Fallback to default text drawing
                    draw.text((img.width // 4, img.height - 70), title, fill=(255, 255, 255, 255))
            else:
                draw.text((img.width // 4, img.height - 70), title, fill=(255, 255, 255, 255))

            # Combine the original image with the overlay
            img = img.convert('RGBA')
            result = Image.alpha_composite(img, overlay)
            result = result.convert('RGB')
            result.save(output_path)

            return output_path
        except Exception as e:
            print(f"⚠️ Error adding title to image: {e}")
            return img_path  # Return original image if failed

    def _create_video(self, script_id, title, text, audio_path, output_file):
        """Create a video with the script audio and related images using ffmpeg."""
        print(f"\n🎬 Creating video for script {script_id}: {title}")

        # Get images related to the script
        images = self._search_images(text, num_images=5)
        if not images:
            print("❌ No images available for video creation")
            return None

        # Create a temp directory for processed images
        temp_dir = os.path.join(self.output_dir, f"temp_{script_id}")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Process images to have consistent dimensions
        processed_images = []
        for i, img_path in enumerate(images):
            try:
                # Open and resize the image
                img = Image.open(img_path)
                # Resize maintaining aspect ratio
                img.thumbnail((1280, 720))

                # Create a new image with black background
                new_img = Image.new('RGB', (1280, 720), (0, 0, 0))

                # Paste the resized image centered
                paste_x = (1280 - img.width) // 2
                paste_y = (720 - img.height) // 2
                new_img.paste(img, (paste_x, paste_y))

                # Add title to the first image
                if i == 0:
                    titled_img_path = os.path.join(temp_dir, f"titled_img_{i}.jpg")
                    self._create_title_image(title, img_path, titled_img_path)
                    processed_path = os.path.join(temp_dir, f"proc_img_{i}.jpg")
                    new_img.save(processed_path)
                    processed_images.append((titled_img_path, processed_path))
                else:
                    processed_path = os.path.join(temp_dir, f"proc_img_{i}.jpg")
                    new_img.save(processed_path)
                    processed_images.append((processed_path,))

                print(f"✅ Processed image {i + 1}/{len(images)}")
            except Exception as e:
                print(f"❌ Error processing image {img_path}: {e}")

        if not processed_images:
            print("❌ No processed images available")
            return None

        # Create a temporary file for the FFmpeg input
        list_file = os.path.join(temp_dir, "image_list.txt")

        # Determine total audio duration
        if isinstance(audio_path, list):
            # Multiple audio chunks that need to be concatenated
            audio_concat_list = os.path.join(temp_dir, "audio_concat.txt")
            with open(audio_concat_list, 'w') as f:
                for audio in audio_path:
                    f.write(f"file '{os.path.abspath(audio)}'\n")

            # Create a concatenated audio file
            concat_audio_path = os.path.join(temp_dir, "concat_audio.wav")
            subprocess.run([
                'ffmpeg', '-f', 'concat', '-safe', '0',
                '-i', audio_concat_list, '-c', 'copy', concat_audio_path
            ], check=True)
            audio_path = concat_audio_path

        # Get audio duration
        probe = ffmpeg.probe(audio_path)
        audio_duration = float(probe['format']['duration'])
        print(f"⏱️ Audio duration: {audio_duration:.2f} seconds")

        # Calculate duration for each image
        image_duration = audio_duration / len(processed_images)

        # Create the image sequence file for FFmpeg
        with open(list_file, 'w') as f:
            for i, img_tuple in enumerate(processed_images):
                # Use the titled image for the first one if available
                if i == 0 and len(img_tuple) > 1:
                    img_path = img_tuple[0]  # Titled image
                else:
                    img_path = img_tuple[0]  # Regular processed image

                if i < len(processed_images) - 1:
                    f.write(f"file '{os.path.abspath(img_path)}'\n")
                    f.write(f"duration {image_duration}\n")
                else:
                    # Last image doesn't need duration
                    f.write(f"file '{os.path.abspath(img_path)}'\n")

        try:
            # Create video from images
            print("🎞️ Creating video from images...")
            temp_video = os.path.join(temp_dir, "temp_video.mp4")

            # Use ffmpeg to create video from images
            subprocess.run([
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file, '-vsync', 'vfr',
                '-vf', 'fps=24,format=yuv420p',
                '-c:v', 'libx264', temp_video
            ], check=True)

            # Add audio to the video
            print("🔊 Adding audio to video...")
            subprocess.run([
                'ffmpeg', '-y',
                '-i', temp_video,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',  # End when the shortest input ends
                output_file
            ], check=True)

            print(f"✅ Video saved to: {output_file}")
            return output_file

        except Exception as e:
            print(f"❌ Error creating video: {e}")
            return None
        finally:
            # Clean up temporary files if needed
            # Uncomment if you want to delete temp files
            # import shutil
            # shutil.rmtree(temp_dir)
            pass

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

            # Create a temporary file listing all videos
            temp_dir = os.path.join(self.output_dir, "temp_combine")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            concat_list = os.path.join(temp_dir, "concat_list.txt")
            with open(concat_list, 'w') as f:
                for video in videos_list:
                    f.write(f"file '{os.path.abspath(video)}'\n")

            # Use ffmpeg to concatenate the videos
            subprocess.run([
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', concat_list,
                '-c', 'copy',  # Copy codecs without re-encoding
                output_file
            ], check=True)

            print(f"✅ Combined video saved to: {output_file}")
            return output_file

        except Exception as e:
            print(f"❌ Error combining videos: {e}")
            return None
        finally:
            # Clean up temporary files if needed
            # Uncomment if you want to delete temp files
            # import shutil
            # shutil.rmtree(temp_dir)
            pass