"""Load .env before any test so os.getenv picks up local credentials."""

from dotenv import load_dotenv

load_dotenv()
