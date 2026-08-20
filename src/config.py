from pathlib import Path

from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
REPORTS_DIR = DATA_DIR / "reports"
STATUS_DIR = DATA_DIR / "status"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "oasis.sqlite"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

load_dotenv(ROOT_DIR / ".env")

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
API_FOOTBALL_BASE_URL = os.environ.get(
    "API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io"
)
