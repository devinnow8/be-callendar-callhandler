from src.schemas.auth import RefreshTokenRequest, TokenResponse
from fastapi import APIRouter, Query, Depends
from src.controller.auth import auth_controller
from src.middleware.auth_middleware import get_current_user
from src.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/google/signin")
async def google_signin(redirect_url: str = f"{settings.URL}/api/v1/auth/callback"):
    """Initialize Google OAuth flow"""
    return await auth_controller.initialize_google_auth(redirect_url)
@router.get("/callback")
async def auth_callback(code: str = Query(...)):
    """Handle OAuth callback"""
    return await auth_controller.handle_oauth_callback(code)

@router.post("/refresh", response_model=TokenResponse)  # will not be user as a route
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token"""
    return await auth_controller.refresh_token(request.refresh_token)

@router.get("/me")
async def get_me(user = Depends(get_current_user)):
    """Get current user"""
    return user

##@router.post("/signout")  // Define it properly
##async def sign_out(
##    request: RefreshTokenRequest,
##    _=Depends(get_current_user)
##):
##    """Sign out user"""
##    return await auth_controller.sign_out(request.refresh_token)