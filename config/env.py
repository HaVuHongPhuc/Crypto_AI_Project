"""Load environment variables from this repository's root ``.env`` file."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_project_env() -> bool:
    """Load the repo-local .env regardless of the process working directory.

    Existing process environment variables intentionally take precedence over
    values in .env, matching python-dotenv's default behavior.
    """
    if not ENV_FILE.is_file():
        return False
    return load_dotenv(dotenv_path=ENV_FILE, encoding="utf-8", override=False)
