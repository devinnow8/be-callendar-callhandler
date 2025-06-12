
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
import requests
from src.utils.jwt_utils import create_jwt_token, extract_data_from_token
from src.schemas.authentication import UserRegister, UserLogin
from fastapi import APIRouter, HTTPException, Depends
from src.services.supabase_service import  UserService, OrgService, OrgUserService
from passlib.context import CryptContext
from src.core.config import settings

router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Route for user registration
@router.post("/register")
def register(
    user: UserRegister,
    user_supabase_service: UserService = Depends(),
    ):
    existing_user = user_supabase_service.get_user_by_email(email=user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = pwd_context.hash(user.password)
    user_supabase_service.insert_user_to_supabase({"email": user.email, "password": hashed_password, "first_name": user.name})
    return {"message": "User registered successfully"}


# Route for user login
@router.post("/login")
def login(
    user: UserLogin,
    user_supabase_service: UserService = Depends(),
    ):
    user_data = user_supabase_service.get_user_by_email(email=user.email, not_password=False)
    if not user_data or not pwd_context.verify(user.password, user_data["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    token = create_jwt_token({"email": user.email, "id": str(user_data['id']), "name": user_data["first_name"]})
    return {"token": token}

# Route for user login
@router.get("/get-user")
def getuser(
    request: Request = None,
    user_supabase_service: UserService = Depends(),
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends()
    ):
    token = request.headers.get('Authorization', None)
    if not token:
        raise   HTTPException(status_code=400, detail="Auth header missing")
    
    data = extract_data_from_token(token)
    if data.get("error", None):
        raise   HTTPException(status_code=400, detail="Invalid jwt")

    user = user_supabase_service.get_user_by_id(id=data['id'])
    if not user:
        raise   HTTPException(status_code=400, detail="User not found")
    
    user_org= org_user_supabase_service.get_user_orgs(user_id = user['id'])
        
    if not user_org:
        return {**user, "organisation": None}
    
    
    org = org_supabase_service.get_organisation_by_id(id = user_org['organisation_id'])
    return {**user, "organisation": org}




# Google OAuth login
@router.get("/auth/google")
def google_auth():
    google_client_id = settings.GOOGLE_CLIENT_ID
    backend_base_endpoint = settings.BACKEND_BASE_ENDPOINT
    redirect_uri = f"{backend_base_endpoint}/api/v1/auth/google/callback"
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={google_client_id}&redirect_uri={redirect_uri}&"
        "response_type=code&scope=openid email profile"
    )
    return {"redirect_uri": google_auth_url}


@router.get("/auth/google/callback")
def google_callback(
    code: str, 
    state: str = None,
    user_supabase_service: UserService = Depends(),
    ):
    try:
        google_client_id = settings.GOOGLE_CLIENT_ID
        google_client_secret = settings.GOOGLE_CLIENT_SECRET
        backend_base_endpoint = settings.BACKEND_BASE_ENDPOINT
        frontend_base_endpoint = settings.FRONTEND_BASE_ENDPOINT
        redirect_uri = f"{backend_base_endpoint}/api/v1/auth/google/callback"
        frontend_redirect_uri = f"{frontend_base_endpoint}/verify-user"
        
        token_data = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        ).json()
        
        access_token = token_data.get("access_token")
        user_info = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        ).json()
        
        email = user_info.get("email")
        existing_user = user_supabase_service.get_user_by_email(email=email)

        if not existing_user:
            existing_user = user_supabase_service.insert_user_to_supabase(data = {"email": email, "first_name": user_info.get("name")})
        
        token = create_jwt_token({"email": email, "id": str(existing_user['id']),  "name": user_info.get("name")})
        
        # Redirect user back to frontend with token
        return RedirectResponse(url=f"{frontend_redirect_uri}?token={token}")
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))