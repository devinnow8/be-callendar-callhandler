from typing import Dict, Any
from fastapi import HTTPException
from src.services.auth import auth_service
from src.schemas.auth import TokenResponse
from fastapi.responses import RedirectResponse
from src.core.config import settings

class AuthController:
    @staticmethod
    async def initialize_google_auth(redirect_url: str) -> Dict[str, str]: # front end uri after authentication
        try:
            return auth_service.get_google_auth_url(redirect_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def handle_oauth_callback(code: str):
        try:
            result = auth_service.exchange_code_for_session(code)
            # saving from result our provider token and provider accesstoken, then return
            auth_token = result["access_token"]
            return RedirectResponse(url=f"{settings.URL_UI}/callback?auth_token={auth_token}")

        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    async def refresh_token(refresh_token: str) -> TokenResponse:
        try:
            result = auth_service.refresh_session(refresh_token)
            return TokenResponse(
                access_token=result["access_token"],
                refresh_token=result["refresh_token"]
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    async def sign_out(refresh_token: str) -> Dict[str, str]:
        try:
            auth_service.sign_out(refresh_token)
            return {"message": "Successfully signed out"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

auth_controller = AuthController()