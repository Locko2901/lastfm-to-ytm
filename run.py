from src.config import Settings, configure_logging
from src.main import run as _run


def run():
    """Entry point for ytmt-sync command."""
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    _run(settings)


if __name__ == "__main__":
    run()
