from src.config import Settings, configure_logging
from src.main import run

if __name__ == "__main__":
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    run(settings)
