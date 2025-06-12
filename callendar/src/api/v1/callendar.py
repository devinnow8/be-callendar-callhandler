from src.services.auth import auth_service
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from src.middleware.auth_middleware import get_current_user
from src.utils.google_utils import get_provider_access_token
from pydantic import BaseModel, Field
from typing import Optional, List
from fastapi import Query
import requests

router = APIRouter()

@router.get("/callendar/events")
async def create_calendar_event(
    #agent_id: str,
    #summary: str = Query(...),
    #location: str = Query(None),
    #description: str = Query(None),
    start_date_time: str = Query(...),  # ISO8601 format, e.g., "2025-01-22T10:00:00Z"
    time_zone: str = Query("UTC"),
    attendee_email: Optional[str] = Query(None),
    event_details: Optional[str] = Query(...)
):
    """
    Create a new event in the Google Calendar for the user associated with the agent.
    """
    try:
        # Validate and fetch the user associated with the given agent_id
        # agent_response = auth_service.client.table("agents").select("user_id").eq("agent_id", agent_id).single().execute()
        # if not agent_response.data:
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail="Agent not found or not associated with any user.",
        #     )
        # user_id = agent_response.data["user_id"]

        user_id = "76607efb-aebf-41f3-99b5-237e700f15b3"
        print("reached point 1 in api call")

        # Fetch a valid provider access token for Google
        access_token_response = get_provider_access_token(user_id)
        print("access_token_response",access_token_response)
        print("start_date_time",start_date_time)
        print("attendee_email",attendee_email)
        print("event_details",event_details)

        #if not access_token_response.data:
        #    raise HTTPException(
        #        status_code=status.HTTP_403_FORBIDDEN,
        #        detail="Failed to fetch a valid provider access token.",
        #    )
#
        #print("access token is",access_token_response)
        # Parse the start time and calculate the end time as 10 minutes later
        try:
            start_datetime = datetime.fromisoformat(start_date_time.replace("Z", "+00:00"))
            end_datetime = start_datetime + timedelta(minutes=10)
            end_date_time = end_datetime.isoformat()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid 'start_date_time' format. Please provide an ISO8601 format (e.g., '2025-01-22T10:00:00Z'). Error: {str(e)}",
            )

        # Define the Google Calendar API URL
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

        # Add Authorization header
        headers = {
            "Authorization": f"Bearer {access_token_response}",
            "Content-Type": "application/json",
        }

        # Prepare the structured event body for Google Calendar
        structured_event = {
             "summary": event_details,
            # "location": location,
            "description": event_details,
            "start": {
                "dateTime": start_date_time,
                "timeZone": time_zone,
            },
            "end": {
                "dateTime": end_date_time,
                "timeZone": time_zone,
            },
            "attendees": [{"email": attendee_email}] if attendee_email else [],
            # "reminders": {"useDefault": True},
        }

        # Make the request to create the event in Google Calendar
        response = requests.post(url, headers=headers, json=structured_event)

        # Handle potential errors
        if response.status_code not in [200, 201]:
            try:
                error_detail = response.json()
            except Exception:
                error_detail = response.text
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to create calendar event: {error_detail}",
            )

        return {"message": "Calendar event created successfully.", "event_details": response.json()}

    except HTTPException as e:
        print(f"HTTPException: {e.detail}")
        raise e
    except requests.exceptions.RequestException as e:
        print(f"RequestException: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create calendar event: Request error: {str(e)}",
        )
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create calendar event: {str(e)}",
        )

@router.get("/callendar/check_events")
async def get_calendar_events(
    user_data=Depends(get_current_user),
    time_min: str = None,
    time_max: str = None,
):
    """
    Fetch events from the user's Google Calendar.
    """
    try:
        # Extract the user ID from the authenticated user
        user_id = user_data["user"].user.id

        # Fetch a valid provider access token
        access_token = get_provider_access_token(user_id)

        # Default time range: next 7 days
        time_min = time_min or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = time_max or (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Prepare the API call
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        # Make the request to fetch events
        response = requests.get(url, headers=headers, params=params)

        # Handle potential errors
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch calendar events: {response.json()}",
            )

        return response.json()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch calendar events: {str(e)}",
        )