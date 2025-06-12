from typing import List, Optional
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

    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET")

    URL: str = os.getenv("URL")
    URL_UI: str = os.getenv("URL_UI")

    ENVIRONMENT: str = os.getenv("ENVIRONMENT")

    STEP_FUNCTION_ARN: str = os.getenv('STEP_FUNCTION_ARN')

    # Ashram Settings
    ASHRAM_INBOUND_AGENT_ID: str = os.getenv("ASHRAM_INBOUND_AGENT_ID")
    ASHRAM_CONTACT: str = os.getenv("ASHRAM_CONTACT")
    ASHRAM_SMTP_USERNAME: str = os.getenv("ASHRAM_SMTP_USERNAME")
    ASHRAM_SMTP_PASSWORD: str = os.getenv("ASHRAM_SMTP_PASSWORD")
    ASHRAM_TWILIO_ACCOUNT_SID: str = os.getenv("ASHRAM_TWILIO_ACCOUNT_SID")
    ASHRAM_TWILIO_AUTH_TOKEN: str = os.getenv("ASHRAM_TWILIO_AUTH_TOKEN")

    # ODE SPA
    ODE_SPA_AGENT_ID: str = os.getenv("ODE_SPA_AGENT_ID")
    ODESPA_PHONE_NUMBERS: List = [
        ph_no for ph_no in os.getenv("ODE_SPA_PHONE_NUMBERS", "").split(",") if ph_no
    ]

    BLACKLIST_ORG_SUBDOMAINS: str = os.getenv('BLACKLIST_ORG_SUBDOMAINS')
    BACKEND_BASE_ENDPOINT: str = os.getenv('BACKEND_BASE_ENDPOINT')
    BACKEND_HOSTNAME: str = os.getenv('BACKEND_HOSTNAME')
    FRONTEND_BASE_ENDPOINT: str = os.getenv('FRONTEND_BASE_ENDPOINT')

    # Plivo Settings
    PLIVO_AUTH_ID: str = os.getenv("PLIVO_AUTH_ID")
    PLIVO_AUTH_TOKEN: str = os.getenv("PLIVO_AUTH_TOKEN")
    PLIVO_PHONE_NUMBER: str = os.getenv("PLIVO_PHONE_NUMBER")

    # PostHog Settings
    POSTHOG_API_KEY: str = os.getenv("POSTHOG_API_KEY", "")
    POSTHOG_HOST: Optional[str] = os.getenv("POSTHOG_HOST", "https://us.posthog.com")
    POSTHOG_DEBUG: bool = bool(os.getenv("POSTHOG_DEBUG", False))

    # Email Settings
    EMAIL_SMTP_SERVER: str = os.getenv("EMAIL_SMTP_SERVER")
    EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT"))
    EMAIL_SMTP_USERNAME: str = os.getenv("EMAIL_SMTP_USERNAME")
    EMAIL_SMTP_PASSWORD: str = os.getenv("EMAIL_SMTP_PASSWORD")

settings = Settings()
