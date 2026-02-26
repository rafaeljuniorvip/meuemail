import os

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "meugmail-secret-change-in-production")
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "rafaeljrssg@gmail.com")
APP_URL = os.getenv("APP_URL", "http://localhost:8467")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 72
