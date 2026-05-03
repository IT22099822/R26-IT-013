from datetime import date
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    jwt_secret: str
    google_client_id: str
    google_client_secret: str
    groq_api_key: str
    gmail_address: str = ""
    gmail_app_password: str = ""

    class Config:
        env_file = ".env"

settings = Settings()

PILOT_START_DATE = date(2026, 4, 22)