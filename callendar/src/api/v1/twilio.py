# from src.services.twilio import twilio_service
# from fastapi import APIRouter, Query, HTTPException, Depends
# from typing import Optional
# from src.services.auth import auth_service
# from src.middleware.auth_middleware import get_current_user


# router = APIRouter()

# @router.get("/available-numbers")
# def get_available_numbers(
#     country_code: str = Query(..., description="Two-letter country code (e.g., US, IN)"),
#     sms: Optional[bool] = Query(None, description="Filter for SMS-enabled numbers"),
#     voice: Optional[bool] = Query(None, description="Filter for Voice-enabled numbers"),
#     area_code: Optional[str] = Query(None, description="Optional area code to filter numbers"),
#     limit: int = Query(10, description="Number of results to return"),
# ):
#     """
#     Endpoint to fetch available phone numbers for a country.
#     """
#     capabilities = {"sms": sms, "voice": voice}
#     return twilio_service.get_available_numbers(
#         country_code=country_code, capabilities=capabilities, area_code=area_code, limit=limit
#     )


# @router.get("/pricing")
# def get_number_cost(country_code: str = Query(..., description="Two-letter country code (e.g., US, IN)")):
#     """
#     Endpoint to fetch phone number pricing for a specific country.
#     """
#     return twilio_service.check_number_cost(country_code)


# @router.post("/purchase-number")   # not sure if a user must be allowed to call this endpoint and how many times , either we need to make a credits system to handle such transactions
# def purchase_phone_number(
#     user_data = Depends(get_current_user),
#     phone_number: str = Query(..., description="Phone number to purchase (E.164 format, e.g., +14155552671)"),
#     sms_url: Optional[str] = Query(None, description="Webhook URL for SMS handling"), # pass your webhook URL here also
#     voice_url: Optional[str] = Query(None, description="Webhook URL for Voice handling"), # we do need to pass webhook URl here as well
#     friendly_name: Optional[str] = Query(None, description="Custom name for the purchased number"),
# ):
#     """
#     Endpoint to purchase a phone number.
#     """
#     purchased_number = twilio_service.purchase_number(
#         phone_number=phone_number, sms_url=sms_url, voice_url=voice_url, friendly_name=friendly_name
#     )
#     print("purchased number is",purchased_number)
#     user_id = user_data["user"].user.id
#     auth_service.client.table("phone_numbers").insert({
#         "phone_number": purchased_number.phone_number,
#         "user_id": user_id
#     }).execute()  # this is not tested properly yet

#     return purchased_number

# @router.post("/link-agent-phone")
# def link_phone_to_agent(
#     user_data=Depends(get_current_user),
#     phone_number: str = Query(..., description="Phone number to link (E.164 format, e.g., +14155552671)"),
#     agent_id: str = Query(..., description="Agent ID to link the phone number to"),
# ):
#     """
#     Endpoint to link a phone number to an agent.
#     """
#     try:
#         # Extract user ID from the current user data
#         user_id = user_data["user"].user.id
#         if not user_id:
#             raise HTTPException(status_code=400, detail="Invalid user data: Missing user ID.")

#         # Check if the phone number belongs to the user
#         phone_query = auth_service.client.table("phone_numbers").select("*").eq("phone_number", phone_number).eq("user_id", user_id).execute()
#         if not phone_query.data:
#             raise HTTPException(status_code=400, detail="Phone number does not belong to the current user.")

#         # Check if the agent belongs to the user
#         agent_query = auth_service.client.table("agents").select("*").eq("agent_id", agent_id).eq("user_id", user_id).execute()
#         if not agent_query.data:
#             raise HTTPException(status_code=400, detail="Agent does not belong to the current user.")

#         # Check if the phone number is already linked to the agent
#         mapping_query = auth_service.client.table("phone_agent_mapping").select("*").eq("phone_number", phone_number).eq("agent_id", agent_id).execute()
#         if mapping_query.data:
#             return {"message": "Phone number is already linked to this agent."}

#         # Link the phone number to the agent
#         auth_service.client.table("phone_agent_mapping").insert({
#             "phone_number": phone_number,
#             "agent_id": agent_id,
#             "user_id": user_id
#         }).execute()

#         return {"message": "Phone number successfully linked to the agent."}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

