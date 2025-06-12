from datetime import datetime
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request, WebSocket
from pyparsing import Optional
from fastapi import HTTPException
from pydantic import BaseModel
from src.services.posthog_service import posthog_service
from src.core.config import settings
from src.services.supabase_service import (
    CampaignService,
    CallLogService,
    CampaignPhoneNumberService,
    ScheduledCallService,
)

from src.services.call_handler import OutboundCallHandler, get_call_handler

from fastapi import Query, Request
from src.services.call_handler import InboundCallHandler, OutboundCallHandler
load_dotenv()


class OutboundCallRequest(BaseModel):
    customer_id: str
    service: str
    type: str


router = APIRouter()


@router.post("/call/trigger")
async def trigger_outbound_call(
    body: OutboundCallRequest,
    request: Request,
    campaign_service: CampaignService = Depends(),
    call_log_service: CallLogService = Depends(),
    scheduled_call_service: ScheduledCallService = Depends(),
):
    """Unified endpoint for making outbound calls"""
    try:
        # create call handler instance
        call_handler = OutboundCallHandler(
            type=body.type,
            provider=body.service
        )

        # trigger call
        call_details = await call_handler.handle_call_trigger(
            customer_id=body.customer_id
        )
        call_details["type"] = body.type
        call_details["service"] = body.service
        # capture event
        posthog_service.capture_event(
            event_name="outbound_call_initiated",
            distinct_id=call_details["call_logs_id"],
            properties={
                "call_id": call_details["customer_id"],
                "type": body.type,
                "service": body.service,
                "call_logs_id": call_details["call_logs_id"],
                "to_number": call_details["to_number"],
                "from_number": call_details["from_number"],
                "agent_id": call_details["agent_id"],
                "organisation_id": call_details["organisation_id"],
                "timestamp": datetime.now().isoformat() 
            }
        )

        return call_details

    except HTTPException as e:
        posthog_service.capture_event(
            event_name="outbound_call_trigger_failed",
            distinct_id=body.customer_id,
            properties={
                "error": e.detail,
                "type": body.type,
                "service": body.service,
                "call_id": body.customer_id,
            }
        )
        raise e

    except Exception as e:
        print(f"Error in outbound call trigger: {str(e)}")
        posthog_service.capture_event(
            event_name="outbound_call_trigger_failed",
            distinct_id=body.customer_id,
            properties={
                "error": str(e),
                "type": body.type,
                "service": body.service,
                "call_id": body.customer_id,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to create call")


@router.post("/call/answer")
async def handle_call_answer(
    request: Request,
    call_logs_id: str = Query(None, description="Call logs id"),
    provider: str = Query(..., description="Provider name"),
    type: str = Query(..., description="Type of call")
):
    try:
        print(
            f"\n\n================== handling call answer ================================\n\n"
        )
        print("call answer on provider: ", provider)
        print("call answer on type: ", type)

        # check if call logs id is provided
        if type != "inbound" and not call_logs_id:
            raise HTTPException(
                status_code=400, detail="Call logs id is required for outbound calls"
            )
        call_handler = get_call_handler(type, provider=provider)
        answer = await call_handler.handle_call_answer(request=request)

        # capture event
        posthog_service.capture_event(
            event_name="call_answered",
            distinct_id=answer["call_logs_id"],
            properties={
                "type": type,
                "service": provider,
                "call_logs_id":answer["call_logs_id"],
                "timestamp": datetime.now().isoformat()
            }
        )
        return answer['answer']

    except HTTPException as e:
        posthog_service.capture_event(
            event_name="call_answered_failed",
            distinct_id= call_logs_id or "unknown",
            properties={
                "error": e.detail,
                "type": type,
                "service": provider,
                "timestamp": datetime.now().isoformat()
            }
        )
        raise e

    except Exception as e:
        print(f"Error in handle call answer: {str(e)}")
        posthog_service.capture_event(
            event_name="call_answered_failed",
            distinct_id=call_logs_id or "unknown",
            properties={
                "error": e.detail,
                "type": type,
                "service": provider,
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to create call")


@router.websocket("/call/media-stream/{provider}/{type}/{call_logs_id}")
async def handle_media_stream(
    websocket: WebSocket,
    provider: str,
    type: str,
    call_logs_id: str
):
    """Unified media stream handler"""
    await websocket.accept()

    # Create call handler instance
    call_handler = get_call_handler(type, provider=provider)

    try:
        print(f"inside media stream")
        # Handle the call stream
        await call_handler.handle_call_stream(call_logs_id, websocket)
    except HTTPException as e:
        print(f"HTTP Error in media stream: {str(e)}")
        posthog_service.capture_event(
            event_name="call_media_stream_failed",
            distinct_id=call_logs_id,
            properties={
                "error": e.detail,
                "type": type,   
                "service": provider,
                "call_logs_id": call_logs_id,
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise e
    except Exception as e:
        print(f"Error in media stream: {str(e)}")
        posthog_service.capture_event(
            event_name="call_media_stream_failed",
            distinct_id=call_logs_id,
            properties={
                "error": e.detail,
                "type": type,
                "service": provider,
                "call_logs_id": call_logs_id,
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/call/hangup")
async def handle_hangup(
    request: Request,
    provider: str = Query(..., description="Provider name"),
    type: str = Query(..., description="Type of call"),
    call_log_service: CallLogService = Depends(),
    campaign_service: CampaignService = Depends(),
    campaign_phone_service: CampaignPhoneNumberService = Depends(),
):
    """Unified hangup webhook handler"""
    try:
        # create call handler instance
        call_handler = get_call_handler(type, provider=provider)
        call_details = await call_handler.handle_call_hangup(request=request)
        # capture event
        posthog_service.capture_event(
            event_name="call_ended",
            distinct_id=call_details["call_logs_id"],
            properties={
                "type": type,
                "service": provider,
                "call_logs_id": call_details["call_logs_id"],
                "hangup_cause": call_details["hangup_cause"],
                "timestamp": datetime.now().isoformat(),
            },
        )
        return call_details
    
    except Exception as e:
        print(f"Error in handle hangup: {str(e)}")
        posthog_service.capture_event(
            event_name="call_hangup_failed",
            distinct_id="unknown",
            properties={
                "error": str(e),
                "type": type,
                "service": provider,
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))
