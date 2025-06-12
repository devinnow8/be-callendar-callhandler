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
from src.services.posthog_service import posthog_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

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


@router.get("/test")
async def root():
    return {"message": "Twilio-ElevenLabs Integration Server"}


@router.post("/plivo/call")
async def make_outbound_call(body: OutboundCallRequest, request: Request):
    try:
        # collect the variables from the request
        call_logs_id = str(uuid.uuid4())
        customer_id = body.customer_id

        # initialize the plivo client
        plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        payload = {"call_logs_id": call_logs_id, "customer_id": customer_id}
        query_params = urlencode(payload)

        # set the answer and hangup urls
        # answer_url = f"https://{ngrok}/api/v1/plivo/outbound?{query_params}"
        # hangup_url = f"https://{ngrok}/api/v1/plivo/hangup"
        answer_url = f"https://{settings.BACKEND_HOSTNAME}/api/v1/plivo/outbound?{query_params}"
        hangup_url = f"https://{settings.BACKEND_HOSTNAME}/api/v1/plivo/hangup"

        # get the data from the campaign_calls_scheduled table
        response = (
            supabase.table("campaign_calls_scheduled")
            .select(
                "phone_number",
                "campaign_id",
                "data",
                "agent_id",
                "id",
                "total_calls",
                "timezone",
                "from_number",
            )
            .eq("id", customer_id)
            .execute()
        )
        data = response.data[0]  # Get the first dictionary from the list
        phone_number = data["phone_number"]

        # update the status of the call to in process
        res = (
            supabase.table("campaign_calls_scheduled")
            .update({"status": "In Process"})
            .eq("id", customer_id)
            .execute()
        )

        campaign = CampaignService().get_campaign_by_id(id=data["campaign_id"], fields="organisation_id")
        # Track call initiation
        posthog_service.capture_event(
            event_name="plivo_outbound_call_initiated",
            distinct_id=f"{call_logs_id} - {phone_number}",
            properties={
                "to_phone_number": phone_number,
                "from_phone_number": data["from_number"],
                "campaign_id": data["campaign_id"],
                "agent_id": data["agent_id"],
                "customer_id": customer_id,
                # "organisation_id": data["organisation_id"]
            }
        )

        # create the call on plivo
        try:
            plivo_response = plivo_client.calls.create(
                from_=data["from_number"],
                machine_detection="hangup",
                time_limit = 2700,
                to_=phone_number,
                answer_url=answer_url,
                hangup_url=hangup_url,
                answer_method="POST",
            )

        except Exception as e:
            res = (
                supabase.table("campaign_calls_scheduled")
                .update(
                    {
                        "status": "Not Initiated",
                        "retry": data.get("retry", 3) - 1,
                        "next_possible_call_date": (
                            datetime.now(pytz.utc).date() + timedelta(days=1)
                        ).strftime("%Y-%m-%d"),
                    }
                )
                .eq("id", customer_id)
                .execute()
            )
            phone_number_status = (
                supabase.table("campaign_phone_numbers_map")
                .update({"status": "available"})
                .eq("campaign_id", data["campaign_id"])
                .eq("phone_number", data["from_number"])
                .execute()
            )
            return {"message": str(e)}

            # call_at = None
            # if timezone:
            #     call_at  = get_user_timezone_schedule_time(timezone_str=timezone)

            # else:
            #     call_at_utc = datetime.now(pytz.utc) + timedelta(days=1)
            #     call_at = call_at_utc.strftime('%Y-%m-%d %H:%M:%S')

        # Insert data into call_logs table
        supabase.table("call_logs").insert(
            {
                "call_logs_id": call_logs_id,
                "customer_id": customer_id,
                "request_uuid": plivo_response["request_uuid"],
                "phone_number": phone_number,
                "usecase_id": data["campaign_id"],
                "human_name": data["data"].get("first_name", None),
                "agent_id": data["agent_id"],
                "organisation_id": campaign.get("organisation_id")
            }
        ).execute()

        # return the response payload
        response_payload = {"call_logs_id": call_logs_id}
        return response_payload

    except Exception as e:
        # Track failure
        posthog_service.capture_event(
            event_name="plivo_outbound_call_failed",
            distinct_id=f"{customer_id} - {phone_number}",
            properties={
                "error": str(e),
                "campaign_id": data["campaign_id"]
            }
        )
        # update the status of the call to failed
        res = (
            supabase.table("campaign_calls_scheduled")
            .update({"status": "Failed"})
            .eq("id", customer_id)
            .execute()
        )
        phone_number_status = (
            supabase.table("campaign_phone_numbers_map")
            .update({"status": "available"})
            .eq("campaign_id", data["campaign_id"])
            .eq("phone_number", data["from_number"])
            .execute()
        )

        # return the error message
        print("Exception occurred in make_call:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/plivo/outbound")
async def outbound_call_handler(request: Request):
    """
    Handles the call by connecting it to the WebSocket stream.
    """

    try:
        print(
            "\n\n========================== inside plivo outbound =====================\n\n"
        )
        query_string = urlencode(request.query_params)

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
            .select("data", "campaign_id", "id", "agent_id", "from_number", "phone_number")
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
        posthog_service.capture_event(
            event_name="plivo_outbound_call_conversation_started",
            distinct_id=f"{call_logs_id} - {data.get('phone_number', None)}",
            properties={
                "customer_id": customer_id,
                "campaign_id": data["campaign_id"],
                # "organisation_id": data["organisation_id"],
                "to_number": data.get('phone_number', None),
                "from_number": data.get('from_number', None),
                "agent_id": data["agent_id"]
            }
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
            call_logs = supabase.table("call_logs").update(
                {
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ),
                }
            ).eq("call_logs_id", call_logs_id).execute()
            print("Conversation ended")

            posthog_service.capture_event(
                event_name="plivo_outbound_call_conversation_ended",
                distinct_id=f"{call_logs_id} - {data.get('phone_number', None)}",
                properties={
                    "customer_id": customer_id,
                    "campaign_id": data["campaign_id"],
                    "to_number": data.get('phone_number', None),
                    "from_number": data.get('from_number', None),
                    "agent_id": data["agent_id"],
                    "org_id": call_logs.data[0]["organisation_id"]
                }
            )
        except Exception:
            print("Error ending conversation session:")
            traceback.print_exc()


@router.post("/plivo/hangup")
async def plivo_hangup(request: Request):
    """
    Handles Plivo hangup webhook.
    """

    print("==================== inside plivo hangup =================")
    # collect the payload from the request
    payload = await request.form()
    print(payload)
    call_id = payload.get("CallUUID")
    hangup_cause = payload.get("HangupCauseName")

    duration_billed = payload.get("BillDuration")
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
            "id, total_calls, campaign_id, retry, next_possible_call_date, from_number", "phone_number","agent_id"
        )
        .eq("id", customer_id)
        .execute()
    )
    call = call.data[0]


    # campaign = supabase.table("campaigns").select("organisation_id").eq("id", call["campaign_id"]).execute().data[0]    # remove later when org ids are properly mapped with call logs
    # update the campaign call status based on the hangup cause
    if hangup_cause == "Normal Hangup":
        print("==================== inside plivo Normal Hangup =================")
        posthog_service.capture_event(
            event_name="plivo_outbound_call_completed",
            distinct_id=f"{call_log.data[0]['call_logs_id']} - {call['from_number']}",
            properties={
                "call_logs_id": call_log.data[0]["call_logs_id"],
                "customer_id": customer_id,
                "campaign_id": call["campaign_id"],
                "organisation_id": call_log.data[0]["organisation_id"],
                "to_phone_number": call["phone_number"],
                "from_phone_number": call["from_number"],
                "hangup_cause": hangup_cause,
                "agent_id": call["agent_id"],
                # "duration_billed": duration_billed,
                # "total_cost": total_cost,
            }
        )

        supabase.table("campaign_calls_scheduled").update(
            {
                "status": "Completed",
                "retry": call.get("retry", 0) - 1,
                "total_calls": call.get("total_calls", 0) + 1,
            }
        ).eq("id", customer_id).execute()

    # update the campaign call status to not initiated with next possible call date to tomorrow
    else:
        print("==================== inside plivo hangup else =================")
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

        posthog_service.capture_event(
            event_name=f"plivo_outbound_call_{hangup_cause.lower()}",
            distinct_id=f"{call_log.data[0]['call_logs_id']} - {call['from_number']}",
            properties={
                "call_logs_id": call_log.data[0]["call_logs_id"],
                "customer_id": customer_id,
                "campaign_id": call["campaign_id"],
                "organisation_id": call_log.data[0].get("organisation_id"),
                "to_phone_number": call["phone_number"],
                "from_phone_number": call["from_number"],
                "hangup_cause": hangup_cause,
                "agent_id": call["agent_id"],
                # "duration_billed": duration_billed,
                # "total_cost": total_cost,
            }
        )


    # call_log = call_log.data[0]
    org_id = call_log.data[0].get("organisation_id")
    print("org_id ===========>", org_id)
    
    # Check if organisation_id exists and is valid before proceeding
    if org_id:
        try:
            # update total attended calls and total consumed call minutes
            org_calls_data = supabase.table("organisations").select("calls_consumed, consumed_call_minutes").eq("id", org_id).execute().data[0]    

            calls_consumed = org_calls_data.get("calls_consumed") if org_calls_data.get("calls_consumed") else 0
            consumed_call_minutes = org_calls_data.get("consumed_call_minutes") if org_calls_data.get("consumed_call_minutes") else 0
            
            duration_billed_int = int(duration_billed) if duration_billed else 0

            updated_data = supabase.table("organisations").update(
                {
                    "calls_consumed": (calls_consumed + 1) if duration_billed_int > 0 else calls_consumed,
                    "consumed_call_minutes": consumed_call_minutes + int(duration_billed_int)
                }
            ).eq("id", org_id).execute()
        except Exception as e:
            print("Error updating organisation data:", str(e))
    else:
        print("Warning: No valid organisation_id found in call_log")


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
