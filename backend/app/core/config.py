import os

from dotenv import load_dotenv


load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "ai_resume_analyzer")
AUTH_SECRET = os.getenv("AUTH_SECRET")
APP_ENV = os.getenv("APP_ENV", "development").casefold()
AUTH_COOKIE_SECURE = APP_ENV not in {"development", "local", "test"}
FRONTEND_ORIGINS = tuple(origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if origin.strip())
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_RESUME_TEXT_CHARS = int(os.getenv("MAX_RESUME_TEXT_CHARS", "200000"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
AUTH_RATE_LIMIT = int(os.getenv("AUTH_RATE_LIMIT", "20"))
ANALYSIS_RATE_LIMIT = int(os.getenv("ANALYSIS_RATE_LIMIT", "12"))

def validate_production_config():
    """Fail fast for unsafe production deployment configuration."""
    if APP_ENV != "production":
        return
    missing = [name for name, value in (("MONGODB_URI", MONGODB_URI), ("AUTH_SECRET", AUTH_SECRET), ("GEMINI_API_KEY", GEMINI_API_KEY)) if not value]
    if missing:
        raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")
    if not FRONTEND_ORIGINS or any(origin.startswith("http://") for origin in FRONTEND_ORIGINS):
        raise RuntimeError("FRONTEND_ORIGINS must contain explicit HTTPS production origins.")
    if not AUTH_SECRET or len(AUTH_SECRET) < 32:
        raise RuntimeError("AUTH_SECRET must be at least 32 characters in production.")
    oauth_values = (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI)
    if any(oauth_values) and not all(oauth_values):
        raise RuntimeError("Google OAuth configuration must include client ID, secret, and redirect URI together.")
    if GOOGLE_OAUTH_REDIRECT_URI and not GOOGLE_OAUTH_REDIRECT_URI.startswith("https://"):
        raise RuntimeError("GOOGLE_OAUTH_REDIRECT_URI must use HTTPS in production.")
