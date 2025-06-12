import os
import json
import traceback
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
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
from plivo_audio_interface import PlivoAudioInterface
import logging
from db import insert_sample_data
import uuid

from supabase import create_client, Client as SupabaseClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("app.log"),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

load_dotenv()

class OutboundCallRequest(BaseModel):
    customer_id: str

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# NGROK_URL = os.getenv("NGROK_URL")
BACKEND_BASE_ENDPOINT = os.getenv("BACKEND_BASE_ENDPOINT")
BASE_ENDPOINT=BACKEND_BASE_ENDPOINT.split("://")[1]
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID = os.getenv("AGENT_ID")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")


app = FastAPI()

@app.get("/test")
async def root():
    return {"message": "Twilio-ElevenLabs Integration Server"}


@app.post("/plivo/call")
async def make_outbound_call(request: OutboundCallRequest):
    try:
        call_logs_id = str(uuid.uuid4())
        customer_id = request.customer_id

        plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)

        payload = {"call_logs_id":call_logs_id, "customer_id":customer_id}
        query_params = urlencode(payload)
        answer_url = f"{BACKEND_BASE_ENDPOINT}/plivo/outbound?{query_params}"
        hangup_url = f"{BACKEND_BASE_ENDPOINT}/plivo/hangup"

        response = supabase.table("campaign_numbers_sequence").select("phone_number", "campaign_id", "first_name").eq("campaign_number_id", customer_id).execute()

        data = response.data[0]  # Get the first dictionary from the list
        phone_number = data["phone_number"]

        plivo_response = plivo_client.calls.create(
            from_=PLIVO_PHONE_NUMBER,
            machine_detection="hangup",
            to_=phone_number,
            time_limit=2700,
            answer_url=answer_url,
            hangup_url=hangup_url,
            answer_method="POST",
        )
        print("###")
        print(customer_id)
        # Insert data into call_logs table
        supabase.table("call_logs").insert({
                "call_logs_id": call_logs_id,
                "customer_id": customer_id,
                "request_uuid": plivo_response["request_uuid"],
                "phone_number": phone_number,
                "usecase_id": data["campaign_id"],
                "human_name": data["first_name"]
            }).execute()

        response_payload = {"call_logs_id": call_logs_id}
        return response_payload
    except Exception as e:
        print("Exception occurred in make_call:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/plivo/outbound")
async def outbound_call_handler(request: Request):
    """
    Handles the call by connecting it to the WebSocket stream.
    """

    try:
        query_string = urlencode(request.query_params)

        websocket_url = f"wss://{BASE_ENDPOINT}/plivo/media-stream-eleven?{query_string}"
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

        return HTMLResponse(content=str(xml_response), status_code=200, media_type="text/xml")

    except Exception as e:
        print(f"Error handling outbound call: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@app.websocket("/plivo/media-stream-eleven")
async def handle_media_stream(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection opened")

    audio_interface = PlivoAudioInterface(websocket)
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    try:
        customer_id = websocket.query_params.get("customer_id")
        call_logs_id = websocket.query_params.get("call_logs_id")

        print("####")
        response = supabase.table("campaign_numbers_sequence").select("first_name", "experience", "venue", "campaign_id").eq("campaign_number_id", customer_id).execute()
        data = response.data[0]
        first_name = data["first_name"]
        experience = data["experience"]
        venue = data["venue"]

        payload = {'first_name': first_name, 'experience': experience, 'venue': venue}

        config = ConversationConfig(
            dynamic_variables=payload
        )

        conversation = Conversation(
            client=eleven_labs_client,
            config=config,
            agent_id=AGENT_ID,
            requires_auth=True, # Security > Enable authentication
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
    
            supabase.table("call_logs").update({"elevenlabs_conversation_id": conversation._conversation_id}).eq("call_logs_id", call_logs_id).execute()
            print("Conversation ended")

        except Exception:
            print("Error ending conversation session:")
            traceback.print_exc()


@app.post("/plivo/hangup")
async def plivo_hangup(request: Request):
    """
    Handles Plivo hangup webhook.
    """
    payload = await request.form()
    print(payload)
    call_id = payload.get("CallUUID")
    hangup_cause = payload.get("HangupCauseName")
    duration_billed = payload.get("Duration")
    total_cost = payload.get("TotalRate")

    supabase.table("call_logs").update({"hangup_cause": hangup_cause,
                                    "duration_billed": duration_billed,
                                    "total_cost": total_cost}).eq("request_uuid", call_id).execute()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
