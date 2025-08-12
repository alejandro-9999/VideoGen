from Controller.ScriptsController import ScriptsController
from Generator.AiServices.AiScriptWriter import AIScriptWriter
from Generator.Database.Manager import Manager


def main():
    # Initialize your database manager and AI script service
    db_manager = Manager(db_path="../data/data.db")
    ai_script_service = AIScriptWriter(model_name="gemma3:12b")
    config = {}  # Add any necessary configuration

    # Create the controller
    scripts_controller = ScriptsController(db_manager, ai_script_service)

    # Generate scripts for all news items
    scripts_controller.generate_scripts_for_news()

if __name__ == "__main__":
    main()