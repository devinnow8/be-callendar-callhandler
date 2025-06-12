import requests
from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse
from datetime import datetime
from src.services.auth import auth_service
from src.core.config import settings  # Assuming settings contains GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
from src.core.config import settings



def get_provider_access_token(user_id: str) -> str:
    """
    Fetch or refresh the provider access token from the database.
    Validate its validity by making a lightweight API call.
    Refresh if invalid, otherwise re-login.
    """
    try:
        # Fetch tokens from the database
        tokens = (
            auth_service.client.table("oauth_tokens")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="OAuth tokens not found"
            )
        provider_access_token = tokens.data.get("provider_access_token")
        provider_refresh_token = tokens.data.get("provider_refresh_token")


        # Validate the provider access token
        if provider_access_token:
            validate_url = "https://www.googleapis.com/oauth2/v1/tokeninfo"
            response = requests.get(validate_url, params={"access_token": provider_access_token})

            if response.status_code == 200:

                return provider_access_token  # Token is still valid
            else:
                # Token is expired or invalid; refresh it
                if provider_refresh_token:
                    refresh_url = "https://oauth2.googleapis.com/token"
                    payload = {
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": provider_refresh_token,
                        "grant_type": "refresh_token",
                    }
                    refresh_response = requests.post(refresh_url, data=payload)

                    if refresh_response.status_code == 200:
                        refreshed_tokens = refresh_response.json()
                        new_access_token = refreshed_tokens["access_token"]
                        # Update the database with the new access token
                        auth_service.client.table("oauth_tokens").update({
                            "provider_access_token": new_access_token,
                        }).eq("user_id", user_id).execute()

                        return new_access_token

        # If no valid token and refreshing fails, force re-login
        raise RedirectResponse(f"{settings.URL_UI}/login")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch or refresh provider access token: {str(e)}"
        )


