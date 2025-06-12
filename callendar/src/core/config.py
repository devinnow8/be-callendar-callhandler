from typing import List
from clerk_backend_api import Optional
from pydantic_settings import BaseSettings
import os
import dotenv

dotenv.load_dotenv()

class Settings(BaseSettings):
    API_V1_STR: str = os.getenv("API_V1_STR")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME")
    PROJECT_VERSION: str = os.getenv("PROJECT_VERSION")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY")

    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY")

    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID") 
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN")

    BACKEND_BASE_ENDPOINT: str = os.getenv('BACKEND_BASE_ENDPOINT')
    BACKEND_HOSTNAME: str = os.getenv('BACKEND_HOSTNAME')
    FRONTEND_BASE_ENDPOINT: str = os.getenv('FRONTEND_BASE_ENDPOINT')


    # PLIVO
    PLIVO_AUTH_ID :str=os.getenv("PLIVO_AUTH_ID")
    PLIVO_AUTH_TOKEN :str=os.getenv("PLIVO_AUTH_TOKEN")

    # PostHog Settings
    POSTHOG_API_KEY: str = os.getenv("POSTHOG_API_KEY", "")
    POSTHOG_HOST: Optional[str] = os.getenv("POSTHOG_HOST", "https://us.posthog.com")
    POSTHOG_DEBUG: bool = bool(os.getenv("POSTHOG_DEBUG", False))


settings = Settings()
