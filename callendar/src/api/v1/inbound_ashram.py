import os
import json
import traceback
from urllib.parse import urlencode
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from starlette.websockets import WebSocketDisconnect
from fastapi import APIRouter
from src.services.elevenlabs_service import ElevenLabsService
from src.services.supabase_service import CallLogService, AgentSupabaseService
from src.services.twilio_audio_interface import TwilioAudioInterface
import uuid
from fastapi import FastAPI
from twilio.rest import Client as TwilioClient
from src.core.config import settings
from src.core.log_config import logger


load_dotenv()

ELEVEN_LABS_AGENT_ID = settings.ASHRAM_INBOUND_AGENT_ID
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY

# Twilio Credentials
# ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
# AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
ACCOUNT_SID = settings.ASHRAM_TWILIO_ACCOUNT_SID
AUTH_TOKEN = settings.ASHRAM_TWILIO_AUTH_TOKEN
twilio_client = TwilioClient(ACCOUNT_SID, AUTH_TOKEN)

router = APIRouter()

@router.post("/twilio/inbound_call")
async def handle_incoming_call(
    request: Request,
    call_log_supabase_service: CallLogService = Depends()
    ):

    form_data = await request.form()
    call_sid = form_data.get("CallSid", "Unknown")
    from_number = form_data.get("From", "+4978048549000")
    print(f"Incoming call: CallSid={call_sid}, From={from_number}")
    logger.info(f"Incoming call: CallSid={call_sid}, From={from_number}")
    # insert call to service :
    call_log_id = str(uuid.uuid4())
    call = call_log_supabase_service.insert_call_log_to_supabase(
        {
            "call_logs_id" : call_log_id,
            "phone_number": from_number,
            "request_uuid": call_sid
        }
    )
    print("calll ===>", call)
    logger.info(f"calll ===> {call}")
    # return {"message": "Webhook received"}
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{settings.BACKEND_HOSTNAME}/api/v1/twilio/media-stream-eleven/{call_log_id}")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@router.websocket("/twilio/media-stream-eleven/{call_log_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_log_id: str,
    call_log_supabase_service: CallLogService = Depends(),
    agent_supabase_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends()
    ):
    await websocket.accept()
    print("WebSocket connection opened")
    logger.info("WebSocket connection opened")
    # Retrieve the call log ID from the query parameters

    hangup_cause = 'Normal Hangup'
    audio_interface = TwilioAudioInterface(websocket)
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    try:
        call_log = call_log_supabase_service.get_call_log_by_id(id = call_log_id, fields="call_logs_id, request_uuid")
        # get agent from db
        
        db_agent_id = agent_supabase_service.get_agent_by_elevenlabs_agent_id(elevenlabs_agent_id=ELEVEN_LABS_AGENT_ID, fields="id")
        if db_agent_id:
            db_agent_id = db_agent_id['id']
            
        conversation = Conversation(
            client=eleven_labs_client,
            agent_id=ELEVEN_LABS_AGENT_ID,
            requires_auth=True, # Security > Enable authentication
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )

        conversation.start_session()
        print("Conversation started")
        logger.info("Conversation started")

        async for message in websocket.iter_text():
            if not message:
                continue
            await audio_interface.handle_twilio_message(json.loads(message))

    except WebSocketDisconnect:
        hangup_cause = 'Websocket Disconnected'
        print("WebSocket disconnected")
        logger.info("CWebSocket disconnected")
    except Exception:
        hangup_cause = 'Websocket Handler Error'
        print("Error occurred in WebSocket handler:")
        logger.info("Error occurred in WebSocket handler:")
        traceback.print_exc()
    finally:
        try:
            conversation.end_session()
            conversation.wait_for_session_end()
            conversation_id = conversation._conversation_id
            call = twilio_client.calls(call_log['request_uuid']).fetch()
            conv_transcript = elevenlabs_service.get_conversation_transcript(conversation_id=conversation_id)
            
            call_log_supabase_service.update_call_log_fields(
                id = call_log_id, 
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "hangup_cause": hangup_cause,
                    "agent_id": db_agent_id,
                    "duration_billed" : call.duration,
                    "duration": conv_transcript['metadata'].get('call_duration_secs', None)
                }
                )
            logger.info("Conversation ended")
            print("Conversation ended")
        except Exception:
            call_log_supabase_service.update_call_log_fields(
                id = call_log_id, 
                update_data={
                    "hangup_cause": "End Conversation Session Error",
                    "agent_id": db_agent_id
                }
                )
            
            logger.info("Error ending conversation session:")
            print("Error ending conversation session:")
            traceback.print_exc()


@router.post("/update-phone-webhook")
def update_phone_webhook(phone_number: str, new_webhook_url: str):
    """
    Updates the Twilio webhook for all incoming calls to a phone number.
    
    Args:
        phone_number (str): The Twilio phone number (E.164 format, e.g., "+1234567890").
        new_webhook_url (str): The new Twilio webhook URL.

    Returns:
        dict: Response indicating success or failure.
    """
    try:
        phone = twilio_client.incoming_phone_numbers.list(phone_number=phone_number)
        print("phone =====>", phone)
        logger.info(f"phone =====>{phone}")
        if phone:
            print(phone[0].voice_url)
            logger.info(phone[0].voice_url)
            phone[0].update(voice_url=new_webhook_url)
            return {
                "message": "Phone webhook updated successfully",
                "phone_number": phone_number,
                "new_webhook_url": new_webhook_url,
            }
        else:
            return {"error": "Phone number not found in Twilio account"}
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}
