import asyncio
from datetime import datetime
from html import escape
import json
import uuid
import requests
import traceback
from urllib.parse import urlencode, parse_qs, unquote
from elevenlabs import ElevenLabs
from fastapi import Request, HTTPException, Depends
from pydantic import BaseModel
from src.services.supabase_service import ScheduledCallService, AgentSupabaseService, OrganisationContactsService, CallLogService, OrgService
from src.core.config import settings
import plivo
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect
from src.services.plivo_audio_interface import PlivoAudioInterface
from src.services.elevenlabs_service import ElevenLabsService
from elevenlabs.conversational_ai.conversation import Conversation, ConversationConfig
from elevenlabs import ConversationalConfig, AgentPlatformSettings, ElevenLabs
from src.services.posthog_service import posthog_service

PLIVO_AUTH_ID = settings.PLIVO_AUTH_ID
PLIVO_AUTH_TOKEN = settings.PLIVO_AUTH_TOKEN
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ngrok = "mongrel-absolute-mongrel.ngrok-free.app"
router = APIRouter()

class OutboundScheduledCallRequest(BaseModel):
    call_id: str


@router.post("/plivo/scheduled/call")
async def make_scheduled_call(
    body: OutboundScheduledCallRequest,
    request: Request,
    scheduled_call_service: ScheduledCallService = Depends(),
    agent_service: AgentSupabaseService = Depends(),
    org_contact_service: OrganisationContactsService = Depends(),
    call_log_service: CallLogService = Depends(),
    ):
    try:
        # extract the call_id from the body
        print("==================== body ==================", body)
        call_id = body.call_id
        call_logs_id = str(uuid.uuid4())
        print("==================== call_logs_id ==================", call_logs_id)
        # hostname = request.url.hostname

        # initialize the plivo client
        plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)

        # answer_url = f"https://{ngrok}/api/v1/plivo/scheduled/call/answer/{call_logs_id}"
        # hangup_url = f"https://{ngrok}/api/v1/plivo/scheduled/call/hangup"
        answer_url = f"https://{settings.BACKEND_HOSTNAME}/api/v1/plivo/scheduled/call/answer/{call_logs_id}"
        hangup_url = f"https://{settings.BACKEND_HOSTNAME}/api/v1/plivo/scheduled/call/hangup"

        # get the scheduled call from the database
        scheduled_call = scheduled_call_service.get_scheduled_call_by_call_id(call_id, fields="to_number, agent_id, organisation_id, from_number, status")
        print("scheduled_call ===========>", scheduled_call)
        if not scheduled_call :
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        if (scheduled_call["status"]).strip().lower() != "scheduled":
            raise HTTPException(status_code=400, detail="This call is already initiated")

        # extract the to_number and agent_id from the scheduled call
        to_number = scheduled_call["to_number"]
        agent_id = scheduled_call["agent_id"]
        from_number = scheduled_call["from_number"]

        # get the agent from the database
        agent = agent_service.get_agent_by_id(agent_id, fields="elevenlabs_agent_id, organisation_id")
        print(agent)
        if not agent or agent["organisation_id"] != scheduled_call["organisation_id"]:
            raise HTTPException(status_code=404, detail="Agent not found")

        # call the plivo api
        try:
            plivo_response = plivo_client.calls.create(
                from_=from_number,
                machine_detection="hangup",
                machine_detection_time=2000,
                time_limit = 2700,
                to_=to_number,
                answer_url=answer_url,
                hangup_url=hangup_url,
                answer_method="POST",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Internal Server Error: Failed to schedule the call on plivo: {str(e)}")

        # Insert data into call_logs table
        call_log = call_log_service.insert_call_log_to_supabase(
            data={
                "call_logs_id": call_logs_id,
                "customer_id": call_id,
                "phone_number": to_number,
                "request_uuid": plivo_response["request_uuid"],
                "organisation_id": scheduled_call["organisation_id"],
                "agent_id": agent_id,
                "organisation_id": scheduled_call["organisation_id"],
            }
        )

        # update the scheduled call status to initiated and call_logs_id
        scheduled_call_service.update_scheduled_call(call_id=call_id,  data={"status": "In Process"})
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
                "timestamp": datetime.now().isoformat() 
            }
        )
        return {"call_logs_id": call_log["call_logs_id"]}

    except HTTPException as e:
        raise e

    except Exception as e:
        print(e)
        posthog_service.capture_event(
            event_name="outbound_call_initiated_error",
            distinct_id=f"{call_logs_id}",
            properties={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/plivo/scheduled/call/answer/{call_logs_id}")
async def answer_scheduled_call(request: Request, call_logs_id: str):
    """
    Handles the call by connecting it to the WebSocket stream.
    """

    try:
        print(
            "\n\n========================== inside plivo outbound =====================\n\n"
        )
        # hostname = request.url.hostname
        # websocket_url = f"wss://{ngrok}/api/v1/plivo/scheduled/call/media-stream-eleven/{call_logs_id}"
        websocket_url = f"wss://{settings.BACKEND_HOSTNAME}/api/v1/plivo/scheduled/call/media-stream-eleven/{call_logs_id}"
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

        posthog_service.capture_event(
            event_name="htt_outbound_call_answer",
            distinct_id=f"{call_logs_id}",
            properties={
                "call_logs_id": call_logs_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

        return HTMLResponse(
            content=str(xml_response), status_code=200, media_type="text/xml"
        )

    except Exception as e:
        print(f"Error handling outbound call: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@router.websocket("/plivo/scheduled/call/media-stream-eleven/{call_logs_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_logs_id: str,
    scheduled_call_service: ScheduledCallService = Depends(),
    call_log_service: CallLogService = Depends(),
    agent_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
    org_service: OrgService = Depends(),
):
    await websocket.accept()
    print("WebSocket connection opened")
    audio_interface = PlivoAudioInterface(websocket)
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    try:
        print("==================== inside media stream ================")
        call_log = call_log_service.get_call_log_by_id(call_logs_id, fields="customer_id")
        call_id = call_log["customer_id"]
        # fetch the call_id from the database
        scheduled_call = scheduled_call_service.get_scheduled_call_by_call_id(call_id, fields="agent_id, call_logs_id, data, to_number, from_number, organisation_id")
        if not scheduled_call:
            raise HTTPException(status_code=404, detail="Scheduled call not found")

        # get the agent from the database
        agent = agent_service.get_agent_by_id(scheduled_call["agent_id"], fields="elevenlabs_agent_id")
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # create a conversation config payload
        config = {}
        conversation_config_override = {}
        if scheduled_call.get("data", None):
            if scheduled_call["data"].get("dynamic_variables"):
                config["dynamic_variables"] = scheduled_call["data"]["dynamic_variables"]

            if scheduled_call["data"].get("prompt", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override['agent'] = {}

                conversation_config_override['agent']['prompt'] = {
                    "prompt": scheduled_call["data"]["prompt"]
                }

            if scheduled_call["data"].get("first_message", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override["agent"] = {}

                conversation_config_override['agent']['first_message'] = scheduled_call["data"]["first_message"]

            if scheduled_call["data"].get("language", None):
                if not conversation_config_override.get("agent", None):
                    conversation_config_override["agent"] = {}

                conversation_config_override['agent']['language'] = scheduled_call["data"]["language"]

        conversation_config = {}

        if conversation_config_override:
            conversation_config['conversation_config_override'] = conversation_config_override

        if config:
            conversation_config['dynamic_variables'] = config['dynamic_variables']

        print("\n\n================> conversation_config: ", conversation_config)
        # create a conversation config
        config = ConversationConfig(
            **conversation_config
        )

        # create a conversation
        conversation = Conversation(
            client=eleven_labs_client,
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

        # Track conversation start
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
            await audio_interface.handle_plivo_message(json.loads(message))

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
            call_logs = call_log_service.update_call_log_fields(
                id=call_logs_id,
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ) if conv_transcript else None,
                }
            )
            print("Conversation ended")

            # Track conversation end
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
                    # "duration": conv_transcript["metadata"].get("call_duration_secs") if conv_transcript else None
                }
            )

        except Exception as e:
            print(str(e))
            print("Error ending conversation session:")
            traceback.print_exc()
            posthog_service.capture_event(
                event_name="conversation_end_error",
                distinct_id=f"{call_logs_id}",
                properties={"error": str(e)}
            )

@router.post("/plivo/scheduled/call/hangup")
async def hangup_scheduled_call(
    request: Request,
    scheduled_call_service: ScheduledCallService = Depends(),
    call_log_service: CallLogService = Depends(),
    org_service: OrgService = Depends(),
    ):
    """
    Handles Plivo hangup webhook.
    """
    try:
        
        print("in plivo scheduled call hangup...............")
        end_call_url = None
        # get the payload from the request
        payload = await request.form()
        print(payload)

        # get the hangup cause, duration billed, and total cost from the payload
        request_uuid = payload.get("CallUUID")
        hangup_cause = payload.get("HangupCauseName")
        duration_billed = payload.get("BillDuration")
        total_cost = payload.get("TotalRate")

        await asyncio.sleep(3) # to wait for the above websocket to be closed properly 
        # update the call log fields
        call_log = call_log_service.update_call_log_fields_by_request_uuid(
            request_uuid=request_uuid,
            update_data={
                "hangup_cause": hangup_cause,
                "duration_billed": duration_billed,
                "total_cost": total_cost,
            }
        )


        print("call_log...........: ", call_log)

        # get the scheduled call from the database
        scheduled_call = scheduled_call_service.update_scheduled_call(call_id=call_log["customer_id"], data={"status": "Completed"})
        print("scheduled_call: ", scheduled_call)


        # update the organisation calls consumed and consumed call minutes

        org_id = call_log["organisation_id"]
        print("org_id ===========>", org_id)

        if org_id:
            print("in org_id ===========>", org_id)
            # update total attended calls and total consumed call minutes
            org_calls_data = org_service.get_organisation_by_id(org_id, fields="calls_consumed, consumed_call_minutes")
            print("org_calls_data ===========>", org_calls_data)


            calls_consumed = org_calls_data.get("calls_consumed") if org_calls_data.get("calls_consumed") else 0
            consumed_call_minutes = org_calls_data.get("consumed_call_minutes") if org_calls_data.get("consumed_call_minutes") else 0
            duration_billed_int = int(duration_billed) if duration_billed else 0

            updated_data = org_service.update_organisation_by_id(id=org_id, data={
                "calls_consumed": (calls_consumed + 1) if duration_billed_int > 0 else calls_consumed,
                "consumed_call_minutes": consumed_call_minutes + int(duration_billed_int)
            })
            print("updated_data ===========>", updated_data)
        else:
            print("Warning: No valid organisation_id found in call_log")
        
        end_call_url = scheduled_call.get("end_call_url", None)
        print("end_call_url ===============>: ", end_call_url)
        posthog_service.capture_event(
            event_name="htt_outbound_call_completed",
            distinct_id=f"{call_log['call_logs_id']}",
            properties={
                "call_logs_id": scheduled_call['call_logs_id'],
                "call_id": scheduled_call['call_id'],
                "to_number": scheduled_call["to_number"],
                "from_number": scheduled_call["from_number"],
                "agent_id": scheduled_call["agent_id"],
                "organisation_id": scheduled_call["organisation_id"],
                "status": scheduled_call["status"],
                "hangup_cause": hangup_cause,
                # "duration_billed": duration_billed,
                # "total_cost": total_cost,
            }
        )
        print("==================== updated call log ==================")
        print(call_log)

    except Exception as e:
        posthog_service.capture_event(
            event_name="htt_call_end_webhook_failed ",
            distinct_id=f"{call_log['call_logs_id']}",
            properties={"error": str(e)}
        )
        print("==================== end call url error ==================")
        print(e)

    finally:
        print("in finally...............")
        if end_call_url:
            try:
                payload = {
                    "call_id": call_log["customer_id"],
                    "call_logs_id": call_log["call_logs_id"],
                    "to_number": scheduled_call["to_number"],
                    "from_number": scheduled_call["from_number"],
                    "agent_id": scheduled_call["agent_id"],
                    "hangup_cause": hangup_cause,
                    "duration": duration_billed,
                    "elevenlabs_conversation_id": call_log["elevenlabs_conversation_id"]
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
                    properties={"error": str(e)}
                )
                print("==================== end call url error ==================")
