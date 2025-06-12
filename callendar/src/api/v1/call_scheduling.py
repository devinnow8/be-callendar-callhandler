import boto3
import json

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from src.schemas.calls_scheduling import ScheduleCallRequest
from src.services.supabase_service import SupabaseService
from src.core.config import settings
  


router = APIRouter()

# AWS Step Functions Client
step_client = boto3.client("stepfunctions", region_name="ap-south-1")

# Step Function ARN (from deployment script)
STEP_FUNCTION_ARN = settings.STEP_FUNCTION_ARN


@router.post("/schedule_ai_call")
async def schedule_ai_call(request: ScheduleCallRequest):
    """ Schedule an AI call via AWS Step Functions and insert it into Supabase """

    try:
        call_time_utc = request.get_utc_datetime()

        call_time_utc_date = datetime.fromisoformat(call_time_utc.replace("Z", "+00:00"))

        # Get current UTC time
        current_time_utc = datetime.now(timezone.utc)

        # Check if the scheduled time is in the past
        if call_time_utc_date < current_time_utc:
            raise HTTPException(status_code=400, detail="Call time cannot be in the past. Please select a future time.")


    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


    # Insert Scheduled Call into Supabase
    supabase_service = SupabaseService()
    call_id = supabase_service.insert_call_to_supabase(
        request.id,
        request.first_name,
        request.last_name,
        request.call_date,
        request.call_time,
        request.call_timezone,
        call_time_utc)

    # Prepare execution input
    execution_input = {
        "call_id": call_id,
        "first_name": request.first_name,
        "last_name": request.last_name,
        "call_time": call_time_utc
    }

    try:
        response = step_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps(execution_input)
        )
        return {"message": "Call scheduled successfully", "executionArn": response["executionArn"]}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start Step Functions execution: {str(e)}")