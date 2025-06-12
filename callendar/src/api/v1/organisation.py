from typing import Optional
import boto3
import json

from fastapi import APIRouter, HTTPException, Depends, Request
from src.services.supabase_service import UserService, OrgService, OrgUserService
from src.schemas.organisation import CreateOrganisationRequest
from src.core.config import settings
import random
import string

router = APIRouter()




@router.post("/organisation")
async def create_organisation(
    request: CreateOrganisationRequest,
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends()
    ):
    """ Register new user to our database """
    try:
       name = request.name
       sub_domain = (((name.strip()).replace(" ", "_")).replace(".", "_")).lower()
       
       blacklist_subdomains = settings.BLACKLIST_ORG_SUBDOMAINS
       if sub_domain in blacklist_subdomains:
           raise HTTPException(status_code=400, detail="Subdomain blacklisted")

       # check if subdomain already present
       organisation = org_supabase_service.get_organisation_by_sub_domain(sub_domain=sub_domain, fields = "id")
       if organisation:  # if present than add a random suffix
           random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
           sub_domain = f"{sub_domain}_{random_suffix}"
       
       # create the org
       response = org_supabase_service.insert_organisation_to_supabase(
            name=name,
            sub_domain=sub_domain,
            email = request.email,
            phone_number=request.phone_number,
            company_name=request.company_name,
            website= request.website,
            address=request.address
        )
       
       if not response.data:
           raise HTTPException(status_code=400, detail=f"Failed to create org: {str(e)}")
        
       response = response.data[0]
       org_user = org_user_supabase_service.add_user_to_organisation_to_supabase(user_id=request.user_id, organisation_id=response['id'])
       return response

    except HTTPException as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/organisation/verify")
async def verify_organisation(
    request: Request,
    org_supabase_service: OrgService = Depends(),
    ):
    sub_domain = request.state.organisation
    org = org_supabase_service.get_organisation_by_sub_domain(sub_domain=sub_domain, fields='id')
    if not org:
       raise HTTPException(status_code=400, detail="Organisation not listed") 



@router.get("/organisation/user/verify")
async def verify_organisation_user(
    request: Request,
    user_supabase_service: UserService = Depends(),
    org_supabase_service: OrgService = Depends(),
    org_user_supabase_service: OrgUserService = Depends(),
    email: Optional[str] = None
    ):
    try:

        sub_domain = request.state.organisation
        org = org_supabase_service.get_organisation_by_sub_domain(sub_domain=sub_domain, fields='id')
        
        if not email:
            if not org :
                return {"success": False, "sub_domain": "onboarding", "message": "Invalid Subdomain"}
            
            return {"success": True, "sub_domain": "", "message": "Valid Organisation"}

          
        user = user_supabase_service.get_user_by_email(email=email)
        if org:
            org_user = org_user_supabase_service.get_org_user_map(user_id=user['id'], org_id=org['id'])
            if org_user:
                return {"success": True, "sub_domain": "", "message": "Valid Organisation"}
            
            user_org = org_user_supabase_service.get_user_orgs(user_id = user['id'])
            org = org_supabase_service.get_organisation_by_id(id=user_org['organisation_id'], fields="sub_domain")
            return {"success": False, "sub_domain": org['sub_domain'], "message": "Invalid subdomain"}
        
        if user:
            user_org = org_user_supabase_service.get_user_orgs(user_id = user['id'])

            if user_org:
                org = org_supabase_service.get_organisation_by_id(id=user_org['organisation_id'], fields="sub_domain")
                return {"success": False, "sub_domain": org['sub_domain'], "message": "Invalid subdomain"}


            return {"success": False, "sub_domain": "onboarding", "message": "Org not setup"}
        
        return {"success": False, "sub_domain": "onboarding", "message": "default"}

    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=400, detail="something went wrong")