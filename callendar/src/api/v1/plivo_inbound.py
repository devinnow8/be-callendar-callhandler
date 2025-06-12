from datetime import datetime, timedelta
import os
import json
import traceback
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
import pytz
from twilio.twiml.voice_response import VoiceResponse, Connect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ConversationConfig
from starlette.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketDisconnect, WebSocketState
from twilio.rest import Client
from fastapi import HTTPException
from pydantic import BaseModel
from urllib.parse import urlencode
import base64
from xml.sax.saxutils import escape
import plivo
from fastapi.responses import PlainTextResponse, JSONResponse
from urllib.parse import urlencode
import logging
import uuid
import httpx
import asyncio
from src.api.v1.campaign import schedule_campaign_call
from src.services.elevenlabs_service import ElevenLabsService
from src.core.config import settings
from src.services.supabase_service import AgentSupabaseService, InboundCampaignPhoneNumberService, CallLogService, InboundCampaignService, OrgService
from supabase import create_client, Client as SupabaseClient
from src.services.plivo_audio_interface import PlivoAudioInterface
from src.services.posthog_service import posthog_service
from src.middleware.stripe_middleware import validate_stripe_subscription


# ngrok = "caribou-open-mistakenly.ngrok-free.app"
ngrok = "mongrel-absolute-mongrel.ngrok-free.app"

# BASE_ENDPOINT = os.getenv("BACKEND_BASE_ENDPOINT").split("://")[1]

router = APIRouter()

@router.post("/plivo/inbound/answer")
async def plivo_inbound_answer_webhook(
    request: Request,
    inbound_campaign_phone_number_service: InboundCampaignPhoneNumberService = Depends(),
    inbound_campaign_service: InboundCampaignService = Depends(),
    call_log_service: CallLogService = Depends(),
    ):
    """
    Handles the call by connecting it to the WebSocket stream.
    """

    try:
        print(
            "\n\n========================== inside plivo inbound =====================\n\n"
        )
        payload = await request.form()
        print("payload", payload)
        call_id = payload.get("CallUUID")
        from_number = payload.get('From')
        to_number = payload.get('To')

        # fetch campaign associated with phone number
        campaign_phone_number_map = (
            await inbound_campaign_phone_number_service.get_inbound_campaign_phone_number_map_by_phone_number(to_number, fields="campaign_id")
        )

        if not campaign_phone_number_map:   
            raise HTTPException(status_code=404, detail="Campaign phone number map not found")

        # get campaign details from campaign id
        campaign_id = campaign_phone_number_map.get("campaign_id")
        campaign = await inbound_campaign_service.get_inbound_campaign_by_id(campaign_id)

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # validate stripe subscription
        is_subscription_valid = await validate_stripe_subscription(org_id=campaign["organisation_id"])
        if not is_subscription_valid:
            # update the campaign status to stopped
            await inbound_campaign_service.stop_inbound_campaign(campaign_id=campaign_id, org_id=campaign["organisation_id"])
            raise HTTPException(status_code=403, detail="Stripe subscription has no remaining calls or minutes")

        # create a call log
        call_log_data = {
            "usecase_id": campaign_id,
            "phone_number": from_number,
            "request_uuid": call_id,
            "organisation_id": campaign.get("organisation_id"),
            "agent_id": campaign.get("agent_id"),
            "type" : "inbound"
        }

        log = call_log_service.insert_call_log_to_supabase(call_log_data)
        # hostname = request.url.hostname
        # websocket_url = f"wss://{ngrok}/api/v1/plivo/inbound/media-stream-eleven/{log['call_logs_id']}"
        websocket_url = f"wss://{settings.BACKEND_HOSTNAME}/api/v1/plivo/inbound/media-stream-eleven/{log['call_logs_id']}"
        escaped_websocket_url = escape(websocket_url)
        print("debug escape " + escaped_websocket_url)
        xml_response = (
            f"<Response>"
            f"<Stream bidirectional='true' contentType='audio/x-l16;rate=8000' keepCallAlive='true'>"
            f"{escaped_websocket_url}"
            f"</Stream>"
            f"</Response>"
        )
        print("debug response " + xml_response)

        # Track inbound call
        posthog_service.capture_event(
            event_name="plivo_inbound_call_received",
            distinct_id=f'{log["call_logs_id"]} - {to_number}',
            properties={
                "call_logs_id": log["call_logs_id"],
                "campaign_id": campaign_id,
                "from_number": from_number,     # user number
                "to_number": to_number,
                "agent_id": campaign["agent_id"],
                "organisation_id": campaign["organisation_id"],
            }
        )

        return HTMLResponse(
            content=str(xml_response), status_code=200, media_type="text/xml"
        )

    except Exception as e:
        print(f"Error handling inbound call: {str(e)}")
        posthog_service.capture_event(
            event_name="plivo_inbound_call_error",
            distinct_id=f'{log["call_logs_id"]} - {to_number}',
            properties={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@router.websocket("/plivo/inbound/media-stream-eleven/{call_logs_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_logs_id: str,
    call_log_service: CallLogService = Depends(),
    agent_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
    org_service: OrgService = Depends(),
):
    await websocket.accept()
    print("WebSocket connection opened")

    audio_interface = PlivoAudioInterface(websocket)
    try:
        call_log = call_log_service.get_call_log_by_id(call_logs_id, fields="agent_id")
        if not call_log:
            raise HTTPException(status_code=404, detail="Call log not found")

        agent_id = call_log["agent_id"]
        # get agent from db
        agent = agent_service.get_agent_by_id(agent_id, fields="elevenlabs_agent_id")
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # set the conversation
        config = ConversationConfig()

        conversation = Conversation(
            client=elevenlabs_service.client,
            config=config,
            agent_id=agent["elevenlabs_agent_id"],
            requires_auth=True,  # Security > Enable authentication
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )

        conversation.start_session()
        print("Conversation started")

        async for message in websocket.iter_text():
            if not message:
                continue
            await audio_interface.handle_plivo_message(json.loads(message))

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception:
        print("Error occurred in WebSocket handler:")
        traceback.print_exc()
    finally:
        try:

            conversation.end_session()
            conversation.wait_for_session_end()
            conversation_id = conversation._conversation_id
            conv_transcript = elevenlabs_service.get_conversation_transcript(
                conversation_id=conversation_id
            )
            call_logs = call_log_service.update_call_log_fields(
                id=call_logs_id,
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ),
                },
            )
            print("Conversation ended")

            # # update total attended calls and total consumed call minutes
            # org_calls_data = org_service.get_organisation_by_id(call_logs["organisation_id"], fields="calls_consumed, consumed_call_minutes") 
            
            # org_service.update_organisation(id=call_logs["organisation_id"], data={
            #         "calls_consumed": org_calls_data["calls_consumed"] + 1,
            #         "consumed_call_minutes": org_calls_data["consumed_call_minutes"] + call_logs.get("duration", 0) / 60
            #     }
            # )
        except Exception:
            print("Error ending conversation session:")
            traceback.print_exc()


@router.post("/plivo/inbound/hangup")
async def plivo_hangup(
    request: Request,
    call_log_service: CallLogService = Depends(),
    org_service: OrgService = Depends(),
):
    """
    Handles Plivo hangup webhook.
    """
    # collect the payload from the request
    payload = await request.form()
    print(payload)
    call_id = payload.get("CallUUID")
    hangup_cause = payload.get("HangupCauseName")
    duration_billed = payload.get("BillDuration")
    total_cost = payload.get("TotalRate")
    to_number = payload.get('To')

    # update the call log
    call_log = call_log_service.update_call_log_fields_by_request_uuid(
        request_uuid=call_id,
        update_data={
            "hangup_cause": hangup_cause,
            "duration_billed": duration_billed,
            "total_cost": total_cost,
        }
    )

    org_id = call_log["organisation_id"]
    print("org_id ===========>", org_id)

    if org_id:
        print("in org_id ===========>", org_id)
        # update total attended calls and total consumed call minutes
        org_calls_data = org_service.get_organisation_by_id(org_id, fields="calls_consumed, consumed_call_minutes")
        print("org_calls_data ===========>", org_calls_data)

        calls_consumed = org_calls_data.get("calls_consumed") if org_calls_data.get("calls_consumed") else 0
        consumed_call_minutes = org_calls_data.get("consumed_call_minutes") if org_calls_data.get("consumed_call_minutes") else 0
        print("calls_consumed ===========>", calls_consumed, "consumed_call_minutes ===========>", consumed_call_minutes)
        # Handle None values safely
        # call_duration = call_log.data[0].get("duration") or 0
        duration_billed_int = int(duration_billed) if duration_billed else 0
        print("duration_billed_int ===========>", duration_billed_int)
        print("type of duration_billed_int ===========>", type(duration_billed_int), "\ntype of calls_consumed ===========>", type(calls_consumed), "\ntype of consumed_call_minutes ===========>", type(consumed_call_minutes))

        updated_data = org_service.update_organisation_by_id(id=org_id, data={
            "calls_consumed": (calls_consumed + 1) if duration_billed_int > 0 else calls_consumed,
            "consumed_call_minutes": consumed_call_minutes + int(duration_billed_int)
        })
        print("updated_data ===========>", updated_data)
    else:
        print("Warning: No valid organisation_id found in call_log")

    posthog_service.capture_event(
        event_name="plivo_inbound_call_completed",
        distinct_id=f'{call_log["call_logs_id"]} - {call_log["phone_number"]}',
        properties={
            "call_logs_id": call_log["call_logs_id"],
            "campaign_id": call_log["usecase_id"],
            "customer_id": call_log["customer_id"],
            "agent_id": call_log["agent_id"],
            "organisation_id": call_log["organisation_id"],
            "hangup_cause": hangup_cause,
            "to_number": to_number,
            "from_number": call_log["phone_number"],
            # "duration_billed": duration_billed,
            # "total_cost": total_cost,
        }
    )

