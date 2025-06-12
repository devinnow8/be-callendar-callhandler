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
from src.services.supabase_service import CampaignService, AgentSupabaseService
from supabase import create_client, Client as SupabaseClient
from src.services.plivo_audio_interface import PlivoAudioInterface


load_dotenv()


class OutboundCallRequest(BaseModel):
    customer_id: str


SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# NGROK_URL = os.getenv("NGROK_URL")
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
AGENT_ID = settings.ODE_SPA_AGENT_ID
PLIVO_PHONE_NUMBER = settings.PLIVO_PHONE_NUMBER
PLIVO_AUTH_ID = settings.PLIVO_AUTH_ID
PLIVO_AUTH_TOKEN = settings.PLIVO_AUTH_TOKEN
# ngrok = "caribou-open-mistakenly.ngrok-free.app"
ngrok = "mongrel-absolute-mongrel.ngrok-free.app"
router = APIRouter()

@router.post("/plivo/inbound/answer")
async def plivo_inbound_answer_webhook(request: Request):
    """
    Handles the call by connecting it to the WebSocket stream.
    """

    try:
        print(
            "\n\n========================== inside plivo inbound =====================\n\n"
        )
        payload = await request.form()
        call_id = payload.get("CallUUID")
        
        query_string = urlencode(request.query_params)
        # hostname = request.url.hostname
        # websocket_url = f"wss://{ngrok}/api/v1/plivo/media-stream-eleven/{request.query_params['customer_id']}?{query_string}"
        websocket_url = f"wss://{settings.BACKEND_HOSTNAME}/api/v1/plivo/media-stream-eleven/{request.query_params['customer_id']}?{query_string}"
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

        return HTMLResponse(
            content=str(xml_response), status_code=200, media_type="text/xml"
        )

    except Exception as e:
        print(f"Error handling outbound call: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@router.websocket("/plivo/media-stream-eleven/{customer_id}")
async def handle_media_stream(
    websocket: WebSocket,
    customer_id: str,
    agent_supabase_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
):
    await websocket.accept()
    print("WebSocket connection opened")

    audio_interface = PlivoAudioInterface(websocket)
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    try:
        print("==================== inside media stream ================")
        # customer_id = websocket.query_params.get("customer_id")
        call_logs_id = websocket.query_params.get("call_logs_id")
        print("call_log_id ===========>", call_logs_id)
        response = (
            supabase.table("campaign_calls_scheduled")
            .select("data", "campaign_id", "id", "agent_id")
            .eq("id", customer_id)
            .execute()
        )
        data = response.data[0]
        # first_name = data["data"]["first_name"]
        # experience = data["data"]["experience"]
        # venue = data["data"]["venue"]
        # payload = {'first_name': first_name, 'experience': experience, 'venue': venue}

        print("campaign calll data =====>", data)
        payload = data["data"]
        agent = agent_supabase_service.get_agent_by_id(
            id=data["agent_id"], fields="id, elevenlabs_agent_id"
        )
        print("agent =====>", agent)
        config = ConversationConfig(dynamic_variables=payload)

        conversation = Conversation(
            client=eleven_labs_client,
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
            supabase.table("call_logs").update(
                {
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ),
                }
            ).eq("call_logs_id", call_logs_id).execute()
            print("Conversation ended")

        except Exception:
            print("Error ending conversation session:")
            traceback.print_exc()


@router.post("/plivo/inbound/hangup")
async def plivo_hangup(request: Request):
    """
    Handles Plivo hangup webhook.
    """

    # collect the payload from the request
    payload = await request.form()
    print(payload)
    call_id = payload.get("CallUUID")
    hangup_cause = payload.get("HangupCauseName")
    duration_billed = payload.get("Duration")
    total_cost = payload.get("TotalRate")

    # update the call log
    call_log = (
        supabase.table("call_logs")
        .update(
            {
                "hangup_cause": hangup_cause,
                "duration_billed": duration_billed,
                "total_cost": total_cost,
            }
        )
        .eq("request_uuid", call_id)
        .execute()
    )

    # collect the customer id
    customer_id = call_log.data[0]["customer_id"]

    print("==================== updated call log =================")

    # collect the campaign call data
    call = (
        supabase.table("campaign_calls_scheduled")
        .select(
            "id, total_calls, campaign_id, retry, next_possible_call_date, from_number"
        )
        .eq("id", customer_id)
        .execute()
    )
    call = call.data[0]

    # update the campaign call status based on the hangup cause
    if hangup_cause == "Normal Hangup":
        supabase.table("campaign_calls_scheduled").update(
            {
                "status": "Completed",
                "retry": call.get("retry", 0) - 1,
                "total_calls": call.get("total_calls", 0) + 1,
            }
        ).eq("id", customer_id).execute()

    # update the campaign call status to not initiated with next possible call date to tomorrow
    else:
        response = (
            supabase.table("campaign_calls_scheduled")
            .update(
                {
                    "status": "Not Initiated",
                    "retry": call.get("retry", 0) - 1,
                    "total_calls": call.get("total_calls", 0) + 1,
                    "next_possible_call_date": (
                        datetime.now(pytz.utc).date() + timedelta(days=1)
                    ).strftime("%Y-%m-%d"),
                }
            )
            .eq("id", customer_id)
            .execute()
        )
        print("campaing call update response ============>", response.data)

    # update the phone number status to available
    phone_number_status = (
        supabase.table("campaign_phone_numbers_map")
        .update({"status": "available"})
        .eq("campaign_id", call["campaign_id"])
        .eq("phone_number", call["from_number"])
        .execute()
    )
    # Fire and forget the scheduling function
    asyncio.create_task(schedule_campaign_call(call.get("campaign_id")))
