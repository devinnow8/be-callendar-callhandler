from fastapi import APIRouter
from src.middleware.auth_middleware import get_current_user
from fastapi import Depends
from src.services.auth import auth_service
from fastapi import HTTPException


router = APIRouter()

@router.get("/credits")
async def get_credits(user_data= Depends(get_current_user)):
    try:
        user_id = user_data["user"].user.id
        credits = auth_service.client.table("credits").select("*").eq("user_id", user_id).execute()
        return {"credits": credits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@router.post("/credits") # test this route
async def add_credits(
    target_user_id: str,  # The user_id to which credits will be assigned
    credits: int,  # Number of credits to assign
    user_data=Depends(get_current_user)  # Current logged-in user details
):
    """
    Add credits to a specific user_id if the current user is an admin.
    """
    try:
        # Fetch the current user's ID
        current_user_id = user_data["user"].user.id

        # Check if the current user is an admin
        admin_check = auth_service.client.table("roles").select("*").eq("user_id", current_user_id).eq("role", "admin").single().execute()

        if not admin_check.data:
            raise HTTPException(status_code=403, detail="You do not have permission to assign credits.")

        # Assign credits to the target user_id
        auth_service.client.table("credits").upsert({
            "user_id": target_user_id,
            "credits": credits
        }).execute()

        return {"message": f"{credits} credits successfully assigned to user_id {target_user_id}"}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
