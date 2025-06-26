import os
import sys
import argparse
from datetime import datetime

# Import our modules
from news_processor import NewsProcessor
from audio_generator import ScriptAudioGenerator
from video_generator import VideoGenerator


def print_header():
    """Print a nice header for the application"""
    print("\n" + "=" * 60)
    print("🌟 NEWS SCRIPT & AUDIO-VIDEO GENERATOR 🌟".center(60))
    print("=" * 60)
    print("\nUtility to search news, generate scripts, and convert to audio/video")
    print("-" * 60 + "\n")


def get_user_choice():
    """Interactive menu to get user choice"""
    print("\nOptions:")
    print("1. Search news and generate scripts")
    print("2. Generate audio from existing scripts")
    print("3. Generate videos from audio")
    print("4. Full pipeline (news → scripts → audio → video)")
    print("0. Exit")

    while True:
        try:
            choice = int(input("\nEnter your choice (0-4): "))
            if 0 <= choice <= 4:
                return choice
            else:
                print("Invalid choice. Please enter a number between 0 and 4.")
        except ValueError:
            print("Please enter a valid number.")


def get_yes_no_input(prompt):
    """Get a yes/no answer from the user"""
    while True:
        response = input(prompt + " (y/n): ").lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' or 'n'.")


def search_news_and_generate_scripts():
    """Function to search news and generate scripts"""
    print("\n📰 NEWS SEARCH AND SCRIPT GENERATION")
    print("-" * 60)

    # Get search query
    search_query = input("\nEnter search query (e.g., 'Noticias sobre ciencia y espacio'): ")
    if not search_query:
        search_query = "Noticias sobre ciencia, el universo, el espacio y exploracion espacial"
        print(f"Using default query: '{search_query}'")

    # Get the LLM model to use
    model = input("\nEnter LLM model to use (default: mistral): ") or "mistral"

    # Ask if we should clear existing data
    clear_data = get_yes_no_input("Clear existing database data?")

    # Initialize the news processor
    processor = NewsProcessor(model=model)

    # Run the pipeline
    processor.run_complete_pipeline(search_query, clear_existing=clear_data)

    print("\n✅ News search and script generation completed!")
    return True


def generate_audio():
    """Function to generate audio from existing scripts"""
    print("\n🔊 AUDIO GENERATION")
    print("-" * 60)

    # Check for voice sources
    voice_dir = "./voice_sources"
    if not os.path.exists(voice_dir):
        print(f"⚠️ Voice sources directory not found: {voice_dir}")
        create_dir = get_yes_no_input("Create directory?")
        if create_dir:
            os.makedirs(voice_dir)
            print(f"Created directory: {voice_dir}")
            print("⚠️ Please add voice samples before continuing.")
            print("   Place .wav files in the voice_sources directory.")
            return False
        else:
            return False

    # Check for voice samples
    voice_files = [f for f in os.listdir(voice_dir) if f.endswith('.wav')]
    if not voice_files:
        print("⚠️ No voice samples (.wav files) found in voice_sources directory.")
        print("   Please add voice samples before continuing.")
        return False

    # Show available voices
    print("\nAvailable voice samples:")
    for i, file in enumerate(voice_files):
        print(f"  {i + 1}. {file}")

    # Get output directory
    output_dir = input("\nEnter output directory (default: audio_output): ") or "audio_output"

    # Ask about combining chunks
    combine_chunks = get_yes_no_input("Combine audio chunks into a single file?")

    # Initialize the audio generator
    voice_paths = [os.path.join(voice_dir, f) for f in voice_files]
    generator = ScriptAudioGenerator(
        output_dir=output_dir,
        voice_sources=voice_paths
    )

    # Generate audio
    print("\n⏳ Generating audio from scripts...")
    generator.process_all_scripts(combine_chunks=combine_chunks)

    print("\n✅ Audio generation completed!")
    return True


def generate_videos():
    """Function to generate videos from existing scripts and audio"""
    print("\n🎬 VIDEO GENERATION")
    print("-" * 60)

    # Check if we have audio files
    audio_dir = "./audio_output"
    if not os.path.exists(audio_dir) or not any(f.endswith('.wav') for f in os.listdir(audio_dir)):
        print("⚠️ No audio files found in audio_output directory.")
        print("   Please generate audio files first.")
        return False

    # Get output directory
    output_dir = input("\nEnter output directory for videos (default: video_output): ") or "video_output"

    # Get the LLM model to use for image search queries
    model = input("\nEnter LLM model to use for image search (default: mistral): ") or "mistral"

    # Ask about combining videos
    combine_videos = get_yes_no_input("Combine individual videos into a single file?")

    # Initialize video generator
    video_gen = VideoGenerator(
        output_dir=output_dir,
        audio_dir=audio_dir,
        model=model
    )

    # Generate videos
    print("\n⏳ Generating videos from scripts and audio...")
    videos = video_gen.process_scripts_to_videos()

    # Combine videos if requested
    if videos and combine_videos:
        print("\n⏳ Combining videos into a single file...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        combined_file = os.path.join(output_dir, f"news_compilation_{timestamp}.mp4")
        result = video_gen.combine_videos(videos, combined_file)
        if result:
            print(f"\n✅ Combined video saved to: {result}")

    print("\n✅ Video generation completed!")
    return True


def run_full_pipeline():
    """Function to run the complete pipeline: news → scripts → audio → video"""
    print("\n🚀 FULL PIPELINE (NEWS → SCRIPTS → AUDIO → VIDEO)")
    print("-" * 60)

    # First part: News search and script generation
    print("\n== PART 1: NEWS SEARCH AND SCRIPT GENERATION ==")
    search_query = input("\nEnter search query (e.g., 'Noticias sobre ciencia y espacio'): ")
    if not search_query:
        search_query = "Noticias sobre ciencia, el universo, el espacio y exploracion espacial"
        print(f"Using default query: '{search_query}'")

    model = input("\nEnter LLM model to use (default: mistral): ") or "mistral"
    clear_data = get_yes_no_input("Clear existing database data?")

    # Initialize and run the news processor
    news_processor = NewsProcessor(model=model)
    news_processor.run_complete_pipeline(search_query, clear_existing=clear_data)

    # Second part: Audio generation
    print("\n== PART 2: AUDIO GENERATION ==")

    # Check for voice sources
    voice_dir = "./voice_sources"
    if not os.path.exists(voice_dir) or not any(f.endswith('.wav') for f in os.listdir(voice_dir)):
        print("⚠️ No voice samples found. Cannot proceed with audio generation.")
        print("   Please add .wav files to the voice_sources directory and try again.")
        return False

    # Show available voices
    voice_files = [f for f in os.listdir(voice_dir) if f.endswith('.wav')]
    print("\nAvailable voice samples:")
    for i, file in enumerate(voice_files):
        print(f"  {i + 1}. {file}")

    output_dir = input("\nEnter output directory for audio (default: audio_output): ") or "audio_output"
    combine_chunks = get_yes_no_input("Combine audio chunks into a single file?")

    # Initialize and run the audio generator
    voice_paths = [os.path.join(voice_dir, f) for f in voice_files]
    audio_generator = ScriptAudioGenerator(
        output_dir=output_dir,
        voice_sources=voice_paths
    )

    audio_generator.process_all_scripts(combine_chunks=combine_chunks)

    # Third part: Video generation
    print("\n== PART 3: VIDEO GENERATION ==")

    # Get output directory for videos
    video_output_dir = input("\nEnter output directory for videos (default: video_output): ") or "video_output"

    # Initialize video generator
    video_generator = VideoGenerator(
        output_dir=video_output_dir,
        audio_dir=output_dir,
        model=model
    )

    # Generate videos
    videos = video_generator.process_scripts_to_videos()

    # Ask about combining videos
    if videos:
        combine_videos = get_yes_no_input("Combine individual videos into a single compilation?")
        if combine_videos:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            combined_file = os.path.join(video_output_dir, f"news_compilation_{timestamp}.mp4")
            result = video_generator.combine_videos(videos, combined_file)
            if result:
                print(f"\n✅ Combined video saved to: {result}")

    print("\n✅ Full pipeline completed successfully!")
    return True


def main():
    """Main function to run the application"""
    print_header()

    # Check for command line arguments
    parser = argparse.ArgumentParser(description="News Script & Audio-Video Generator")
    parser.add_argument("--news", action="store_true", help="Run news search and script generation")
    parser.add_argument("--audio", action="store_true", help="Run audio generation")
    parser.add_argument("--video", action="store_true", help="Run video generation")
    parser.add_argument("--full", action="store_true", help="Run full pipeline")
    args = parser.parse_args()

    # If command line arguments are provided, run the specified function
    if args.news:
        search_news_and_generate_scripts()
        return
    elif args.audio:
        generate_audio()
        return
    elif args.video:
        generate_videos()
        return
    elif args.full:
        run_full_pipeline()
        return

    # Otherwise, show the interactive menu
    while True:
        choice = get_user_choice()

        if choice == 0:
            print("\nExiting application. Goodbye! 👋")
            break
        elif choice == 1:
            search_news_and_generate_scripts()
        elif choice == 2:
            generate_audio()
        elif choice == 3:
            generate_videos()
        elif choice == 4:
            run_full_pipeline()

        # Ask if user wants to continuerew
        if not get_yes_no_input("\nDo you want to perform another operation?"):
            print("\nExiting application. Goodbye! 👋")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nAn unexpected error occurred: {e}")
        sys.exit(1)