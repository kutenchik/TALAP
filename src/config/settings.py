"""Minimal Django settings for the CLI-first catalog foundation."""

from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = "development-only-not-for-production"
DEBUG = False
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "admission.catalog",
    "admission.applicants",
]
MIDDLEWARE = [
    "django.middleware.csrf.CsrfViewMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES: list[dict[str, object]] = []
WSGI_APPLICATION = "config.wsgi.application"
database_path = Path(os.environ.get("ADMISSION_DB_PATH", str(BASE_DIR / ".var" / "admission.sqlite3")))
database_path.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(database_path),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
