import asyncio
from datetime import datetime, timedelta
import json
import traceback
from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import HTMLResponse
import pytz
from twilio.twiml.voice_response import VoiceResponse, Connect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ConversationConfig
from starlette.websockets import WebSocketDisconnect
from fastapi import HTTPException
from pydantic import BaseModel
import uuid
from src.services.elevenlabs_service import ElevenLabsService
from src.core.config import settings
from src.services.supabase_service import (
    ScheduledCallService,
    AgentSupabaseService,
    CallLogService,
    OrgService,
)
import requests
from src.services.twilio import get_twilio_service
from src.services.twilio_audio_interface import TwilioAudioInterface
from src.services.posthog_service import posthog_service

router = APIRouter()

# ngrok_url = "caribou-open-mistakenly.ngrok-free.app"
ngrok_url = "mongrel-absolute-mongrel.ngrok-free.app"


class OutboundScheduledCallRequest(BaseModel):
    call_id: str


@router.post("/twilio/scheduled/call")
async def make_scheduled_call(
    body: OutboundScheduledCallRequest,
    request: Request,
    scheduled_call_service: ScheduledCallService = Depends(),
    agent_service: AgentSupabaseService = Depends(),
    call_log_service: CallLogService = Depends(),
):
    try:
        # extract the call_id from the body
        call_id = body.call_id
        call_logs_id = str(uuid.uuid4())
        print("==================== call_logs_id ==================", call_logs_id)
        # hostname = request.url.hostname
        # hostname = ngrok_url

        # get the scheduled call from the database
        scheduled_call = scheduled_call_service.get_scheduled_call_by_call_id(
            call_id, fields="to_number, agent_id, organisation_id, from_number"
        )
        print(scheduled_call)
        if not scheduled_call:
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        # extract the to_number and agent_id from the scheduled call
        to_number = scheduled_call["to_number"]
        agent_id = scheduled_call["agent_id"]
        from_number = scheduled_call["from_number"]

        # get the agent from the database
        agent = agent_service.get_agent_by_id(
            agent_id, fields="elevenlabs_agent_id, organisation_id"
        )
        print(agent)
        if not agent or agent["organisation_id"] != scheduled_call["organisation_id"]:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Make the Twilio call
        try:
            twilio_service = get_twilio_service(org_id=scheduled_call["organisation_id"])
            call = twilio_service.client.calls.create(
                to=to_number,
                from_=from_number,
                time_limit=2700,
                # machine_detection="Enable",
                # machine_detection_timeout=1,
                url=f"https://{settings.BACKEND_HOSTNAME}/api/v1/twilio/scheduled/call/answer/{call_logs_id}",
                status_callback=f"https://{settings.BACKEND_HOSTNAME}/api/v1/twilio/scheduled/call/hangup",
                status_callback_event=["completed"],
            )

        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Internal Server Error: Failed to schedule the call on Twilio: {str(e)}",
            )

        # Insert data into call_logs table
        call_log = call_log_service.insert_call_log_to_supabase(
            data={
                "call_logs_id": call_logs_id,
                "customer_id": call_id,
                "phone_number": to_number,
                "request_uuid": call.sid,
                "agent_id": agent_id,
                "organisation_id": scheduled_call["organisation_id"],
            }
        )

        # update the scheduled call status to initiated and call_logs_id
        scheduled_call_service.update_scheduled_call(
            call_id=call_id, data={"status": "In Process"}
        )

        # Add PostHog tracking after call creation
        posthog_service.capture_event(
            event_name="htt_outbound_call_initiated",
            distinct_id=f"{call_logs_id}",
            properties={
                "call_logs_id": call_log["call_logs_id"],
                "call_id": call_id,
                "to_number": to_number,
                "from_number": from_number,
                "agent_id": agent_id,
                "organisation_id": scheduled_call["organisation_id"],
                "timestamp": datetime.now().isoformat(),
            },
        )
        return {"call_logs_id": call_log["call_logs_id"]}

    except HTTPException as e:
        raise e

    except Exception as e:
        # Add error tracking
        posthog_service.capture_event(
            event_name="outbound_call_initiated_error",
            distinct_id=f"{call_logs_id}",
            properties={"error": str(e)},
        )
        print(e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/twilio/scheduled/call/answer/{call_logs_id}")
async def answer_scheduled_call(request: Request, call_logs_id: str):
    """Handle Twilio call answer webhook"""
    try:
        # hostname = request.url.hostname
        # hostname = ngrok_url

        # Create TwiML response with WebSocket stream
        response = VoiceResponse()
        response.start().detect_silence(
            silence_timeout ="15",
            silence_threshold = "500",
            action=f"https://{settings.BACKEND_HOSTNAME}/api/v1/twilio/scheduled/call/hangup"
        )
        connect = Connect()
        stream = connect.stream(
            url=f"wss://{settings.BACKEND_HOSTNAME}/api/v1/twilio/scheduled/call/media-stream/{call_logs_id}"
        )
        response.append(connect)

        # Add PostHog tracking
        posthog_service.capture_event(
            event_name="htt_outbound_call_answer",
            distinct_id=f"{call_logs_id}",
            properties={
                "call_logs_id": call_logs_id,
                "timestamp": datetime.now().isoformat(),
            },
        )
        print("\n\n\n\n\n\n\nanswer timestamp: ", datetime.now().isoformat())
        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as e:
        print(f"Error in handle_outbound_answer: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@router.websocket("/twilio/scheduled/call/media-stream/{call_logs_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_logs_id: str,
    scheduled_call_service: ScheduledCallService = Depends(),
    call_log_service: CallLogService = Depends(),
    agent_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
):
    await websocket.accept()
    print("WebSocket connection opened")
    print("websocket timestamp: ", datetime.now().isoformat())
    audio_interface = TwilioAudioInterface(websocket)

    try:
        print("==================== inside media stream ================")
        call_log = call_log_service.get_call_log_by_id(
            call_logs_id, fields="customer_id"
        )
        call_id = call_log["customer_id"]
        # fetch the call_id from the database
        scheduled_call = scheduled_call_service.get_scheduled_call_by_call_id(
            call_id, fields="agent_id, call_logs_id, data, to_number, from_number, organisation_id"
        )
        if not scheduled_call:
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        # get the agent from the database
        agent = agent_service.get_agent_by_id(
            scheduled_call["agent_id"], fields="elevenlabs_agent_id"
        )
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # create a conversation config payload
        config = {}
        conversation_config_override = {}
        if scheduled_call.get("data", None):
            if scheduled_call["data"].get("dynamic_variables"):
                config["dynamic_variables"] = scheduled_call["data"][
                    "dynamic_variables"
                ]

            if scheduled_call["data"].get("prompt", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override["agent"] = {}

                conversation_config_override["agent"]["prompt"] = {
                    "prompt": scheduled_call["data"]["prompt"]
                }

            if scheduled_call["data"].get("first_message", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override["agent"] = {}

                conversation_config_override["agent"]["first_message"] = scheduled_call[
                    "data"
                ]["first_message"]

            if scheduled_call["data"].get("language", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override["agent"] = {}

                conversation_config_override["agent"]["language"] = scheduled_call[
                    "data"
                ]["language"]

        conversation_config = {}

        if conversation_config_override:
            conversation_config["conversation_config_override"] = (
                conversation_config_override
            )

        if config:
            conversation_config["dynamic_variables"] = config["dynamic_variables"]

        print("\n\n================> conversation_config: ", conversation_config)
        # create a conversation config
        config = ConversationConfig(**conversation_config)

        # create a conversation
        conversation = Conversation(
            client=elevenlabs_service.client,
            config=config,
            agent_id=agent["elevenlabs_agent_id"],
            requires_auth=True,  # Security > Enable authentication
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )

        # start the conversation
        conversation.start_session()
        print("Conversation started")
        print("conversation timestamp: ", datetime.now().isoformat())
        # Add PostHog tracking for conversation start
        posthog_service.capture_event(
            event_name="htt_conversation_started",
            distinct_id=call_logs_id,
            properties={
                "call_logs_id": call_logs_id,
                "call_id": call_id,
                "to_number": scheduled_call["to_number"],
                "from_number": scheduled_call["from_number"],
                "agent_id": scheduled_call["agent_id"],
                "organisation_id": scheduled_call["organisation_id"],
                "timestamp": datetime.now().isoformat(),
            },
        )


        async for message in websocket.iter_text():
            if not message:
                continue
            await audio_interface.handle_twilio_message(json.loads(message))

    except WebSocketDisconnect as w:
        print("WebSocket disconnect ed")
        print("WebSocket disconnect reason: ", w.code)
        print("WebSocket disconnect reason detail: ", w.reason)

    except Exception as e:
        print("Error occurred in WebSocket handler:")
        print("Error: ", str(e))
    finally:
        try:
            conversation.end_session()
            conversation.wait_for_session_end()
            conversation_id = conversation._conversation_id
            conv_transcript = None
            try:
                conv_transcript = elevenlabs_service.get_conversation_transcript(
                    conversation_id=conversation_id
                )
            except Exception as e:
                print("Error getting conversation transcript: ", str(e))

            print("call_logs_id: ", call_logs_id)
            call_log_service.update_call_log_fields(
                id=call_logs_id,
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": (
                        conv_transcript["metadata"].get("call_duration_secs", None)
                        if conv_transcript
                        else None
                    ),
                },
            )
            print("Conversation ended")

            # Add PostHog tracking for conversation end
            posthog_service.capture_event(
                event_name="htt_conversation_ended",
                distinct_id=f"{call_logs_id}",
                properties={
                    "call_logs_id": call_logs_id,
                    "call_id": call_id,
                    "to_number": scheduled_call["to_number"],
                    "from_number": scheduled_call["from_number"],
                    "agent_id": scheduled_call["agent_id"],
                    "organisation_id": scheduled_call["organisation_id"],
                    "conversation_id": conversation_id,
                },
            )
        except Exception as e:
            posthog_service.capture_event(
                event_name="conversation_end_error",
                distinct_id=f"{call_logs_id}",
                properties={"error": str(e)},
            )


@router.post("/twilio/scheduled/call/hangup")
async def hangup_scheduled_call(
    request: Request,
    scheduled_call_service: ScheduledCallService = Depends(),
    call_log_service: CallLogService = Depends(),
    org_service: OrgService = Depends(),
):
    """Handle Twilio call status callback"""
    try:
        end_call_url = None
        call_status_map = {"completed": "Normal Hangup", "no-answer": "Busy"}
        form_data = await request.form()
        print("form_data ===>", form_data)

        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        print("call_status ===>", call_status)
        call_duration = int(form_data.get("Duration", 1)) * 60
        hangup_cause = call_status_map.get(call_status, call_status)
        await asyncio.sleep(3)  # to wait for the above websocket to be closed properly
        # Update call log
        call_log = call_log_service.update_call_log_fields_by_request_uuid(
            request_uuid=call_sid,
            update_data={
                "hangup_cause": hangup_cause,
                "duration_billed": call_duration,
            },
        )

        # Update scheduled call status
        scheduled_call = scheduled_call_service.update_scheduled_call(
            call_id=call_log["customer_id"], data={"status": "Completed"}
        )
        org_id = scheduled_call["organisation_id"]
        print("in org_id ===========>", org_id)
        # update total attended calls and total consumed call minutes
        org_calls_data = org_service.get_organisation_by_id(org_id, fields="calls_consumed, consumed_call_minutes")
        print("org_calls_data ===========>", org_calls_data)

        calls_consumed = org_calls_data.get("calls_consumed") if org_calls_data.get("calls_consumed") else 0
        consumed_call_minutes = org_calls_data.get("consumed_call_minutes") if org_calls_data.get("consumed_call_minutes") else 0
        print("calls_consumed ===========>", calls_consumed)
        print("consumed_call_minutes ===========>", consumed_call_minutes)
        duration_billed_int = int(call_duration) if call_duration else 0
        print("duration_billed_int ===========>", duration_billed_int)

        updated_data = org_service.update_organisation_by_id(id=org_id, data={
            "calls_consumed": (calls_consumed + 1) if duration_billed_int > 0 else calls_consumed,
            "consumed_call_minutes": consumed_call_minutes + int(duration_billed_int)
        })
        print("updated_data ===========>", updated_data)
        


        print("scheduled_call: ", scheduled_call)
        end_call_url = scheduled_call.get("end_call_url", None)
        print("end_call_url ===============>: ", end_call_url)
        posthog_service.capture_event(
            event_name="htt_outbound_call_completed",
            distinct_id=f"{call_log['call_logs_id']}",
            properties={
                "call_logs_id": scheduled_call["call_logs_id"],
                "call_id": scheduled_call["call_id"],
                "to_number": scheduled_call["to_number"],
                "from_number": scheduled_call["from_number"],
                "agent_id": scheduled_call["agent_id"],
                "organisation_id": scheduled_call["organisation_id"],
                "status": scheduled_call["status"],
                "hangup_cause": hangup_cause,
            },
        )
        print("==================== updated call log ==================")
        print(call_log)
    except Exception as e:
        posthog_service.capture_event(
            event_name="htt_hangup_failed ",
            distinct_id=f"{call_log['call_logs_id']}",
            properties={"error": str(e)},
        )
        print("==================== hangup error ==================")
        print(e)

    finally:
        if end_call_url:
            try:
                payload = {
                    "call_id": call_log["customer_id"],
                    "call_logs_id": call_log["call_logs_id"],
                    "to_number": scheduled_call["to_number"],
                    "from_number": scheduled_call["from_number"],
                    "agent_id": scheduled_call["agent_id"],
                    "hangup_cause": hangup_cause,
                    "duration": call_duration,
                    "elevenlabs_conversation_id": call_log[
                        "elevenlabs_conversation_id"
                    ],
                }
                response = requests.post(end_call_url, json=payload)
                print("==================== end call url ==================")

                posthog_service.capture_event(
                    event_name="htt_call_end_webhook_success ",
                    distinct_id=f"{call_log['call_logs_id']}",
                    properties={"response": response.json()},
                )

            except Exception as e:
                posthog_service.capture_event(
                    event_name="htt_call_end_webhook_failed ",
                    distinct_id=f"{call_log['call_logs_id']}",
                    properties={"error": str(e)},
                )
                print("==================== end call url error ==================")
