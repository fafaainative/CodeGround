"""
Application settings and global path configuration for CodeGround.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Storage Paths
DATA_DIR = BASE_DIR / "data"
WORKSPACE_DIR = BASE_DIR / "workspace"
CLONES_DIR = WORKSPACE_DIR / "clones"
SCHEMA_PATH = BASE_DIR / "codeground" / "database" / "schema.sql"

# Database Configuration
DATABASE_URL = os.getenv("CODEGROUND_DB_PATH", str(DATA_DIR / "codeground.db"))

# Operational Limits for Repository Ingestion
MAX_REPO_SIZE_MB = 100
SUBPROCESS_TIMEOUT_SECONDS = 200
ALLOWED_LANGUAGES = ["Python", "JavaScript", "TypeScript", "Markdown", "JSON"]

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
CLONES_DIR.mkdir(parents=True, exist_ok=True)
