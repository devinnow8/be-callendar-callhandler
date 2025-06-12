from fastapi import APIRouter, Depends, status, HTTPException
from src.middleware.auth_middleware import get_current_user
from src.services.auth import auth_service


router = APIRouter(prefix="/user", tags=["user"])


@router.get("/is-onboarding-completed")
async def is_onboarding_completed(user_data=Depends(get_current_user)):
    """
    Check if the onboarding process is completed for the current user.
    """
    try:
        user_id = user_data["user"].user.id
        user_profile =  auth_service.client.table("user_profiles").select("*").eq("user_id", user_id).execute()

        if user_profile:
            return {"onboarding_completed": user_profile.data[0]["onboarded"]}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )
    except HTTPException as e:
        print(f"HTTPException: {e.detail}")
        raise e
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while checking onboarding status",
        )


  

@router.post("/onboarding", status_code=status.HTTP_200_OK)
async def onboarding(details: dict, user=Depends(get_current_user)):
    """
    Endpoint to complete onboarding for the user.
    """
    try:
        user_id = user["user"].user.id
        # Insert or update the onboarding details for the user
        onboarding_data = {
            "user_id": user_id,
            "language": details.get("language", "English"),
            "business_type": details["businessType"],
            "ai_receptionists": int(details["aiReceptionists"]),
            "google_maps_url": details.get("googleMapsUrl", None),
            "website_url": details.get("websiteUrl", None),
            "social_media_url": details.get("socialMediaUrl", None),
            "employee_count": details["employeeCount"],
        }

        auth_service.client.table("onboarding_details").upsert(onboarding_data).execute()
        auth_service.client.table("user_profiles").update({"onboarded": True}).eq("user_id", user_id).execute()
        return {"message": "Onboarding completed successfully."}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to complete onboarding: {str(e)}",
        )