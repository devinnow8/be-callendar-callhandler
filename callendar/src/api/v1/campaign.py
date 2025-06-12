import csv
import io
import time
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
import httpx
from src.core.config import settings
from src.services.supabase_service import  CampaignService,  CampaignPhoneNumberService, OrganisationContactsService
from datetime import datetime, timedelta
import pytz
from src.middleware.stripe_middleware import validate_stripe_subscription

router = APIRouter()


# def get_user_timezone_schedule_time(timezone_str, start_time):
#     """
#     Calculates the next day's scheduled call time in UTC based on the user's timezone and start time.

#     :param timezone_str: The user's timezone as a string (e.g., "America/New_York").
#     :param start_time: The desired start time as a string in HH:MM format (e.g., "07:30").
#     :return: The scheduled call time in UTC as a formatted string (YYYY-MM-DD HH:MM:SS).
#     """
#     try:
#         # Convert string input ("HH:MM") to time object
#         start_hour, start_minute = map(int, start_time.split(":"))
#         start_time_obj = time(start_hour, start_minute)

#         user_timezone = pytz.timezone(timezone_str)
#         user_time = datetime.now(user_timezone)

#         # Schedule for the next day at the specified start time
#         next_day_user_time = user_time.replace(
#             hour=start_time_obj.hour, minute=start_time_obj.minute, second=0, microsecond=0
#         ) + timedelta(days=1)

#         # Convert to UTC
#         call_at_utc = next_day_user_time.astimezone(pytz.utc)
#         return call_at_utc.strftime('%Y-%m-%d %H:%M:%S')

#     except Exception as e:
#         print(f"Error determining scheduled call time: {str(e)}")
#         return None

# def is_within_call_window(phone_number, timezone_str, start_time, end_time):
#     """
#     Checks if the current time in the given timezone is within the allowed call window (9 AM - 8 PM).

#     :param phone_number: The phone number being checked (for logging purposes).
#     :param timezone_str: The timezone associated with the phone number.
#     :return: True if within allowed call window, False otherwise.
#     """
#     try:
#         # Convert string inputs ("HH:MM") to time objects
#         start_hour, start_minute = map(int, start_time.split(":"))
#         end_hour, end_minute = map(int, end_time.split(":"))
#         start_time_obj = time(start_hour, start_minute)
#         end_time_obj = time(end_hour, end_minute)

#         # Get the current time in the provided timezone
#         user_timezone = pytz.timezone(timezone_str)
#         user_time = datetime.now(user_timezone)

#         # Check if current time falls within the allowed window
#         if start_time_obj <= user_time.hour < end_time_obj:
#             print(f" Allowed: Calling {phone_number} at {user_time.strftime('%Y-%m-%d %H:%M:%S')} in {timezone_str}")
#             return True
#         else:
#             print(f" Not Allowed: Cannot call {phone_number} now ({user_time.strftime('%Y-%m-%d %H:%M:%S')}) in {timezone_str}")
#             return False

#     except Exception as e:
#         print(f" Error determining call time for {phone_number}: {str(e)}")
#         return False


def get_next_available_call(campaign_id):
    print("fetching the next available call")
    campaign = CampaignService().get_campaign_by_id(
        id=campaign_id,
        fields="id, status, organisation_id, availability_start_time, availability_end_time",
    )
    if not campaign:
        return "Campaign Not Found"

    if campaign["status"] != "Running":
        return "Campaign is not running"

    # Convert string times to time objects
    try:
        current_time = datetime.now(pytz.utc).time()
        avail_start = datetime.strptime(
            campaign["availability_start_time"], "%H:%M:%S"
        ).time()
        avail_end = datetime.strptime(
            campaign["availability_end_time"], "%H:%M:%S"
        ).time()

        if avail_start > current_time or current_time > avail_end:
            return "Campaign is not available to call"
    except Exception as e:
        print(f"Time conversion error: {str(e)}")
        return "Invalid time format"

    # Rest of the function remains same
    campaign_phone_numbers = CampaignPhoneNumberService().get_campaign_available_phone_numbers(
        campaign_id=campaign["id"], fields="phone_number, status"
    )
    if not campaign_phone_numbers:
        return "No Phone number available to call"

    campaign_sequence = CampaignService().get_priority_campaign_scheduled_call(
        campaign_id=campaign_id, fields="id"
    )
    print("campaign_sequence ====>", campaign_sequence)
    
    if not campaign_sequence:
        # check if all the calls are completed or out of retry
        campaign_calls = CampaignService().get_count_for_pending_campaign_calls(campaign_id=campaign_id)
        print("campaign_calls ====>", campaign_calls)
        if campaign_calls:
            return "No call to schedule"
        else:
            # update the campaign status to completed
            CampaignService().update_campaign(campaign_id=campaign_id, data={"status": "Completed"})
            return "All calls are completed or out of retry"


    # fetch the phone number details
    phone_number_details = OrganisationContactsService().get_orgnisation_number(phone_number=campaign_phone_numbers[0]["phone_number"], fields="phone_number, service")
    if not phone_number_details:
        return "Phone number not found"
    
    return {
            "campaign_sequence_id": campaign_sequence["id"],
            "from_number": campaign_phone_numbers[0]["phone_number"],
            "service": phone_number_details["service"],
        }
   


async def initiate_call(next_call):
    campaign_sequence_id = next_call["campaign_sequence_id"]
    from_number = next_call["from_number"]
    service = next_call["service"]
    print("service to initiate call ====>", service)
    if service == "plivo":
        print("plivo service ====>")
        api_url = f"{settings.BACKEND_BASE_ENDPOINT}/api/v1/plivo/call"
        # api_url = "https://caribou-open-mistakenly.ngrok-free.app/api/v1/plivo/call"
        # api_url = "https://mongrel-absolute-mongrel.ngrok-free.app/api/v1/plivo/call"

    elif service == "twilio":
        print("twilio service ====>")
        api_url = f"{settings.BACKEND_BASE_ENDPOINT}/api/v1/twilio/outbound/call"
        # api_url = "https://caribou-open-mistakenly.ngrok-free.app/api/v1/twilio/outbound/call"
        # api_url = "https://mongrel-absolute-mongrel.ngrok-free.app/api/v1/twilio/outbound/call"

    else:
        print("invalid service ====>")
        return "Invalid service"

    payload = {"customer_id": campaign_sequence_id}
    print("api_url ====>", api_url)

    print("makin the call in progress")
    res = CampaignService().update_campaign_scheduled_call(
        id=campaign_sequence_id,
        data={"status": "In Process", "from_number": from_number},
    )

    print("updated campaign scheduled call ====>", res)

    print("marking the phone number as unavailable")
    phone_number_status = CampaignPhoneNumberService().update_campaign_ph_no_status(
        campaign_id=res["campaign_id"],
        phone_number=res["from_number"],
        data={"status": "unavailable"},
    )
    print("unavailable phone number status ====>", phone_number_status)

    print("posting the request to this")
    async with httpx.AsyncClient() as client:
        try:
            print("posting the request to this")
            await client.post(api_url, json=payload)  # No need to capture response
            return "Call Secheduled successfully"

        except Exception as e:
            print("\n\n\n ================================================\n\n\n")
            print(f"Error in scheduling the call API request: {e}")
            print("\n\n\n ================================================\n\n\n")

            print("updating the campaign scheduled call status to failed")
            res = CampaignService().update_campaign_scheduled_call(
                id=campaign_sequence_id, data={"status": "Failed"}
            )

            print("marking the phone number as available")
            phone_number_status = (
                CampaignPhoneNumberService().update_campaign_ph_no_status(
                    campaign_id=res["campaign_id"],
                    phone_number=res["from_number"],
                    data={"status": "available"},
                )
            )
            return "Call Secheduling Failed"

    return "Something went wrong"

async def schedule_campaign_call(campaign_id: str):
    while True:
        print("in schedule campaign call..............")
        campaign = CampaignService().get_campaign_by_id(id=campaign_id, fields="organisation_id")
        print("campaign ====>", campaign)
        is_subscription_valid = await validate_stripe_subscription(org_id=campaign["organisation_id"])
        print("is_subscription_valid", is_subscription_valid)
        if not is_subscription_valid:
            # stop the campaign
            await CampaignService().update_campaign_stop_status(campaign_id=campaign_id, data={"status": "Stopped"})
            print("campaign stopped ------------------------------")
            return None
        
        print("scheduling the campaign call ------------------------------")
        next_call = get_next_available_call(campaign_id)
        print("\n\nnext_call ====>", next_call)
        if not next_call or not isinstance(next_call, dict):
            print("no next call found ------------------------------")
            return None
        # return None
        print("initiating the call ------------------------------")
        res = await initiate_call(next_call)
        print("\n\nres ====>", res)
        time.sleep(5)  # Wait before checking again


@router.get("/campaign/start/{campaign_id}")
async def schedule_first_campaign_call(campaign_id: str):
    response = await schedule_campaign_call(campaign_id)
    return {"message": response}


@router.post("/campaign/calls")
async def upload_camaign_calls(
    file: UploadFile = File(...),
    agent_id: str = Form(...),  # Accept agent_id from form-data
    campaign_id: str = Form(...),  # Accept campaign_id from form-data
    campaign_supabase_service: CampaignService = Depends(),
):
    """
    API to upload a CSV file and process its contents, adding metadata from JSON.
    """
    try:
        # Read CSV file into memory
        contents = await file.read()
        file_stream = io.StringIO(contents.decode("utf-8"))

        # Read CSV rows into a list of dictionaries
        csv_reader = csv.DictReader(file_stream)
        # Print CSV headers
        print("CSV Headers:", csv_reader.fieldnames)
        campaign_calls = [
            {
                "agent_id": agent_id,
                "campaign_id": campaign_id,
                "status": "Not Initiated",
                "phone_number": row.pop("phone_number", None),
                "data": row,
                "retry": row.pop("retry", 3),
                "timezone": row.pop("timezone", "Asia/Kolkata"),
            }
            for row in csv_reader
        ]

        # Ensure we have data to insert
        if not campaign_calls:
            raise HTTPException(status_code=400, detail="CSV file is empty.")
        # Insert data into Supabase
        response = campaign_supabase_service.bulk_add_campaign_calls(
            calls=campaign_calls
        )
        # Log and return response
        return {
            "message": "Data inserted successfully!",
            "inserted_rows": len(response),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/campaign/{action}/{id}")
async def stop_or_start_a_campaign(
    id: str, # campaign_id 
    action: str, # stop /start
    campaign_Subabase_service: CampaignService = Depends()
):
    '''
        API TO STOP OR START A CAMPAIGN CALLING
    '''
    try:
        response = None
        if action == "start":
            response = campaign_Subabase_service.bulk_update_campaign_scheduled_call_status_by_campaign_id_and_status(campaign_id=id, status="Stopped", data = {"status": "Not Initiated"})
        elif action == "stop":
            response = campaign_Subabase_service.bulk_update_campaign_scheduled_call_status_by_campaign_id_and_status(campaign_id=id, status="Not Initiated", data = {"status": "Stopped"})
        else:
            raise HTTPException(status_code=404, detail='Page Not Found')
        
        if not response:
            response = []

        return {"message": f"Changed the status of {len(response)} calls"}

    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    except Exception as e:
        raise HTTPException(status_code=500, detail="Something went wrong")
