import boto3
import json

import pytz
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, WebSocket
from datetime import datetime, timezone
from src.services.supabase_service import  UserService, OrgService, OrgUserService
from src.schemas.users import CreateUserRequest
from src.core.config import settings
  
router = APIRouter()

@router.post("/users")
async def create_user(
    request: Request,
    user_supabase_service: UserService = Depends(),
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends()
    ):
    """ Register new user to our database """
    try:
        body = await request.json()
        first_name = None
        last_name = None
        email = None


        if 'host' in  body:  # todo: we will fix it later for now we have to check if the request is coming from clerk webhook or frontend
            first_name = body.get('first_name', None)
            last_name = body.get("last_name", None)
            email = body["email"]

        else:
            first_name = body['data'].get("first_name", None)
            last_name = body['data'].get("last_name", None)
            email = body['data']['email_addresses'][0]['email_address']


        user = user_supabase_service.get_user_by_email(email=email)
        data = {
            "first_name":first_name,
            "last_name":last_name,
            "email":email
        }
        if not user:
            user = user_supabase_service.insert_user_to_supabase(
                data = data
            )
            if user:
                return {**user, "organisation": None, "detail": "user created successfully"}
            
            raise HTTPException(status_code=200, detail="failed to create user")
            
        user_org= org_user_supabase_service.get_user_orgs(user_id = user['id'])
        
        if not user_org:
            return {**user, "organisation": None, "detail": "user already exsits"}
        
        
        org = org_supabase_service.get_organisation_by_id(id = user_org['organisation_id'])
        return {**user, "organisation": org, "detail": "user already exsits"}

    except HTTPException as e:
        raise HTTPException(status_code=400, detail=str(e.detail))    

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/users")
async def get_user(
    request: Request,
    user_id: str,
    user_supabase_service: UserService = Depends(),
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends()
    ):
    try:
        # TODO: will check for current user with the dependent function
        user = user_supabase_service.get_user_by_id(id = user_id)
        if not user:
            raise HTTPException(status_code=400, detail="User not found") 
        
        sub_domain = request.state.organisation
        org = org_supabase_service.get_organisation_by_sub_domain(sub_domain=sub_domain)
        
        if not org:
            raise HTTPException(status_code=400, detail="organsiation not found") 
        
        # TODO: check if user belongs to the org: it will also be handled in the same dependent function
        org_user = org_user_supabase_service.get_org_user_map(user_id=user['id'], org_id=org['id'])
        
        if not org_user:
            raise HTTPException(status_code=400, detail="Organisation not listed") 
        
        return {**user, "organisation": org}
    
    except HTTPException as e:
        raise HTTPException(status_code=400, detail=str(e.detail))

    except Exception as e:
        raise HTTPException(status_code=400, detail="failed to fetch user details")
    


