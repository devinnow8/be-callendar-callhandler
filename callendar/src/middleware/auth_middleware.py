from fastapi import Depends, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from src.services.supabase_service import UserService, OrgService, OrgUserService
from src.utils.jwt_utils import extract_data_from_token
from src.services.auth import auth_service  # Import your AuthService instance
from typing import Dict, Any, Union
from src.core.config import settings





def get_request_org_user(
        request: Request,
        user_supabase_service: UserService = Depends(),
        org_supabase_service: OrgService = Depends(),
        org_user_supabase_service: OrgUserService = Depends()
        ) -> Union[Dict[str, Any], JSONResponse]:
    try:
        # Extract the access token from the Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
            )
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header must start with 'Bearer '",
            )

        access_token = auth_header.split(" ")[1]
        data = extract_data_from_token(access_token)
        if data.get('error'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail= data['error'],
            )
        
        # get user from db
        user = user_supabase_service.get_user_by_id(data['id'])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail= "User not found",
            )
        
        # check if the user belongs to that org
        sub_domain = request.state.organisation
        organisation = org_supabase_service.get_organisation_by_sub_domain(sub_domain=sub_domain, fields = "id")
        if not organisation:
            raise HTTPException(status_code=400, detail="Organisation not listed")
        
        org_user_map = org_user_supabase_service.get_org_user_map(org_id=organisation['id'], user_id=user['id'])
        if not org_user_map:
            raise HTTPException(status_code=400, detail="Organisation not listed")
        
        return {"user": user, "organisation": organisation}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )

def get_current_user(request: Request) -> Union[Dict[str, Any], JSONResponse]:
    """
    Middleware to check user authentication and refresh tokens if required, with detailed error logging.
    """
    try:
        # Extract the access token from the Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            print("Error: Missing Authorization header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
            )
        if not auth_header.startswith("Bearer "):
            print("Error: Authorization header format is invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header must start with 'Bearer '",
            )

        access_token = auth_header.split(" ")[1]
        print(f"Access token extracted", access_token)

        # Use Supabase's SDK to validate and fetch the user
        try:
            user = auth_service.get_user(access_token)
            print(f"User fetched successfully")
            if user:
                return {"user": user, "new_access_token": None}  # No new token needed
        except Exception as user_fetch_error:
            print(f"Error while fetching user with access token: {user_fetch_error}")

        # If access_token is invalid or expired, refresh the session
        try:
            print("access token is", access_token)
            tokens = (
                auth_service.client.table("oauth_tokens")  # Fetch the token details
                .select("*")
                .eq("access_token", access_token)
                .single()
                .execute()
            )
            print(f"Token details fetched: {tokens}")
        except Exception as token_fetch_error:
            print(f"Error while fetching tokens: {token_fetch_error}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: Could not fetch token details",
            )

        if not tokens:
            print("Error: No tokens found in the database")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: No tokens found",
            )

        refresh_token = tokens.data.get("refresh_token")
        user_id = tokens.data.get("user_id")
        print(f"Refresh token: {refresh_token}, User ID: {user_id}")

        # Refresh session and update tokens
        try:
            session = auth_service.refresh_session(refresh_token)
            print(f"Session refreshed successfully: {session}")
        except Exception as refresh_error:
            print(f"Error while refreshing session: {refresh_error}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh session",
            )

        # Update tokens in the database
        try:
            auth_service.client.table("oauth_tokens").update({
                "access_token": session["access_token"],
                "refresh_token": session["refresh_token"],
            }).eq("user_id", user_id).execute()
            print("Tokens updated in the database")
        except Exception as token_update_error:
            print(f"Error while updating tokens in the database: {token_update_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update tokens in the database",
            )

        # Fetch user details with the refreshed access token
        try:
            user = auth_service.get_user(session["access_token"])
            print(f"User fetched with new access token")
            if user:
                return {"user": user, "new_access_token": session["access_token"]}
        except Exception as user_fetch_error:
            print(f"Error while fetching user with refreshed token: {user_fetch_error}")

        # If everything fails, redirect to login
        print("Error: All authentication attempts failed")
        raise RedirectResponse(f"{settings.URL_UI}/login")

    except HTTPException as http_error:
        print(f"HTTPException: {http_error.detail}")
        raise http_error
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )
