from pathlib import Path
import os

APP_DIR = Path(os.environ.get("OFFTEC_HOME", Path.home() / ".offtec-ai-hunter"))
DB_PATH = APP_DIR / "offtec.sqlite3"
REPORT_DIR = APP_DIR / "reports"
EXPORT_DIR = APP_DIR / "exports"
SECRETS_PATH = APP_DIR / "secrets.json"
LOCALE_DIR = Path(__file__).resolve().parents[2] / "locales"
