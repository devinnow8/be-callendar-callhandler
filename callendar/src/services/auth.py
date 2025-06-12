from typing import Optional, Dict, Any
from supabase import create_client
from src.core.config import settings
from datetime import datetime, timezone

class AuthService:
    def __init__(self):
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY) # need to simplify this later one  client must be created and used everywhere el

    def get_google_auth_url(self, redirect_url: str) -> Dict[str, Any]:
        """Generate Google OAuth URL"""
        try:
            result = self.client.auth.sign_in_with_oauth(
                {
                    "provider": "google",
                    "options": {
                        "redirect_to": redirect_url,
                        "scopes": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/calendar.events",
                        "query_params": {
                            "access_type": "offline",
                            "prompt": "consent",
                        },
                    },
                }
            )
            return {"url": result.url}
        except Exception as e:
            raise Exception(f"Failed to generate auth URL: {str(e)}")

    def exchange_code_for_session(self, code: str) -> Dict[str, Any]:
        """Exchange OAuth code for session"""
        try:
            auth_response = self.client.auth.exchange_code_for_session({
                        "auth_code": code,
                    })  
            print("auth_response",auth_response);          
        
            session = auth_response.session
            access_token = session.access_token
            refresh_token = session.refresh_token
            provider_token = session.provider_token
            provider_refresh_token = session.provider_refresh_token
            expires_at = session.expires_at

            token_expiry = datetime.fromtimestamp(expires_at, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


            # Insert or update the token in the database
            self.client.table("oauth_tokens").upsert({
            "user_id": auth_response.user.id,  # Use the user ID from the session
            "access_token": access_token,
            "refresh_token": refresh_token,
            "provider_access_token": provider_token,
            "provider_refresh_token": provider_refresh_token,
            "token_expiry": token_expiry
        }).execute()
            
            is_credits_present = self.client.table("credits").select("*").eq("user_id", auth_response.user.id).execute()
            if is_credits_present.data:
                pass
            else:
                self.client.table("credits").insert({
                    "user_id": auth_response.user.id,
                    "credits": 0
                }).execute()

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "provider_access_token": provider_token,
                "user": auth_response.user
            }
        except Exception as e:
            print(f"Failed to exchange code: {str(e)}")
            raise Exception(f"Failed to exchange code: {str(e)}")

    def refresh_session(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh session using refresh token"""
        try:
            session = self.client.auth.refresh_session(refresh_token)

            return {
                "access_token": session.session.access_token,
                "refresh_token": session.session.refresh_token,
            }
        except Exception as e:
            raise Exception(f"Failed to refresh session: {str(e)}")

    def get_user(self, access_token: str):
        """Fetch user details using the access token."""
        try:
            user = self.client.auth.get_user(jwt=access_token)
            return user
        except Exception as e:
            raise Exception(f"Failed to fetch user: {str(e)}")

    ##def sign_out(self, refresh_token: str) -> bool:
    ##    """Sign out user"""
    ##    try:
    ##        self.client.auth.sign_out(refresh_token)
    ##        return True
    ##    except Exception as e:
    ##        raise Exception(f"Failed to sign out: {str(e)}")


# Instantiate the service
auth_service = AuthService()
