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
from src.services.supabase_service import CampaignService, AgentSupabaseService, CallLogService, CampaignPhoneNumberService, OrgService
from src.services.twilio import get_twilio_service
from src.services.twilio_audio_interface import TwilioAudioInterface
import os
from src.services.posthog_service import posthog_service

router = APIRouter()

# ngrok_url = "caribou-open-mistakenly.ngrok-free.app"
ngrok_url = "mongrel-absolute-mongrel.ngrok-free.app"


class TwilioOutboundCallRequest(BaseModel):
    customer_id: str


@router.post("/twilio/outbound/call")
async def make_outbound_call(
    body: TwilioOutboundCallRequest,
    request: Request,
    campaign_service: CampaignService = Depends(),
    agent_supabase_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
    call_log_service: CallLogService = Depends(),
):
    """Handle outbound call initiation for Twilio"""
    try:
        # Generate unique call logs ID
        call_logs_id = str(uuid.uuid4())
        customer_id = body.customer_id
        # hostname = request.url.hostname

        # Get campaign call data
        response = campaign_service.get_campaign_call_by_id(
            id = customer_id,
            fields="phone_number, campaign_id, data, agent_id, id, total_calls, from_number",
        )
        if not response:
            raise HTTPException(status_code=404, detail="Campaign call not found")

        # get the campaign data
        campaign_data = campaign_service.get_campaign_by_id(
            id=response["campaign_id"],
            fields="id,  organisation_id",
        )   

        if not campaign_data:
            raise HTTPException(status_code=404, detail="Campaign not found")

        data = response
        to_number = data["phone_number"]

        # Update call status to In Process
        campaign_service.update_campaign_scheduled_call(
            id=customer_id, data={"status": "In Process"}
        )

        try:
            # Make the Twilio call
            twilio_service = get_twilio_service(org_id=campaign_data["organisation_id"])
            call = twilio_service.client.calls.create(
                to=to_number,
                from_=data["from_number"],
                time_limit=2700,
                # machine_detection="Enable",
                # Use the answer webhook URL
                # url=f"https://{ngrok_url}/api/v1/twilio/outbound/answer/{call_logs_id}",
                # status_callback=f"https://{ngrok_url}/api/v1/twilio/outbound/hangup",
                url=f"https://{settings.BACKEND_HOSTNAME}/api/v1/twilio/outbound/answer/{call_logs_id}",
                status_callback=f"https://{settings.BACKEND_HOSTNAME}/api/v1/twilio/outbound/hangup",
                status_callback_event=["completed"],
            )

        except Exception as e:
            # Handle failed call initiation
            campaign_service.update_campaign_scheduled_call(
                id=customer_id,
                data={
                    "status": "Not Initiated",
                    "retry": data.get("retry", 3) - 1,
                    "next_possible_call_date": (
                        datetime.now(pytz.utc).date() + timedelta(days=1)
                    ).strftime("%Y-%m-%d"),
                },
            )
            return {"message": "Call initiation failed"}

        # Create call log entry
        call_log_service.insert_call_log_to_supabase(
            {
                "call_logs_id": call_logs_id,
                "customer_id": customer_id,
                "request_uuid": call.sid,
                "phone_number": to_number,
                "usecase_id": data["campaign_id"],
                "human_name": data["data"].get("first_name", None),
                "agent_id": data["agent_id"],
                "organisation_id": campaign_data["organisation_id"],
                "type": "outbound",
            }
        )

        # Track outbound call initiation
        posthog_service.capture_event(
            event_name="twilio_outbound_call_initiated",
            distinct_id=f"{call_logs_id} - {to_number}",
            properties={
                "call_logs_id": call_logs_id,
                "customer_id": customer_id,
                "to_number": to_number,
                "from_number": data["from_number"],
                "campaign_id": data["campaign_id"],
                "agent_id": data["agent_id"],
                "organisation_id": campaign_data["organisation_id"]
            }
        )

        return {"call_logs_id": call_logs_id}

    except Exception as e:
        # Track failure
        posthog_service.capture_event(
            event_name="twilio_outbound_call_failed",
            distinct_id=f"{customer_id} - {to_number if 'to_number' in locals() else 'unknown'}",
            properties={
                "error": str(e),
                "campaign_id": data["campaign_id"] if 'data' in locals() else None
            }
        )
        print(f"Error in make_outbound_call: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/twilio/outbound/answer/{call_logs_id}")
async def handle_outbound_answer(request: Request, call_logs_id: str):
    """Handle Twilio call answer webhook"""
    try:    
        # Create TwiML response with WebSocket stream
        response = VoiceResponse()
        connect = Connect()
        stream = connect.stream(
            # url=f"wss://{ngrok_url}/api/v1/twilio/outbound/media-stream/{call_logs_id}"
            url=f"wss://{settings.BACKEND_HOSTNAME}/api/v1/twilio/outbound/media-stream/{call_logs_id}"
        )   
        response.append(connect)

        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as e:
        print(f"Error in handle_outbound_answer: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle outbound call")


@router.websocket("/twilio/outbound/media-stream/{call_logs_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_logs_id: str,
    agent_supabase_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
    campaign_service: CampaignService = Depends(),
    call_log_service: CallLogService = Depends(),
    org_service: OrgService = Depends(),
):
    """Handle WebSocket media stream for Twilio calls"""
    await websocket.accept()
    print("WebSocket connection opened")

    audio_interface = TwilioAudioInterface(websocket)
    try:
        # get the call log data
        call_log = call_log_service.get_call_log_by_id(
            id=call_logs_id, fields="agent_id, customer_id, organisation_id"
        )
        
        # get the campaign call data
        campaign_call = campaign_service.get_campaign_call_by_id(
            id=call_log["customer_id"], fields="data, campaign_id, id, agent_id, phone_number, from_number"
        )

        payload = campaign_call["data"]

        # get the agent data
        agent = agent_supabase_service.get_agent_by_id(
            id=campaign_call["agent_id"], fields="id, elevenlabs_agent_id"
        )

        # Configure and start conversation
        config = ConversationConfig(dynamic_variables=campaign_call["data"])
        conversation = Conversation(
            client=elevenlabs_service.client,
            config=config,
            agent_id=agent["elevenlabs_agent_id"],
            requires_auth=True,
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )

        conversation.start_session()
        print("Conversation started")

        # Track conversation start
        posthog_service.capture_event(
            event_name="twilio_outbound_conversation_started",
            distinct_id=f'{call_logs_id} - {campaign_call["phone_number"]}',
            properties={
                "call_logs_id": call_logs_id,
                "agent_id": agent["id"],
                "elevenlabs_agent_id": agent["elevenlabs_agent_id"],
                "customer_id": call_log["customer_id"],
                "campaign_id": campaign_call["campaign_id"],
                "organisation_id": call_log["organisation_id"],
                "to_number": campaign_call["phone_number"],
                "from_number": campaign_call["from_number"]
            }
        )

        async for message in websocket.iter_text():
            if not message:
                continue
            await audio_interface.handle_twilio_message(json.loads(message))

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"Error in media stream: {str(e)}")
        traceback.print_exc()
    finally:
        try:
            conversation.end_session()
            conversation.wait_for_session_end()

            # Update call log with conversation data
            conversation_id = conversation._conversation_id
            conv_transcript = elevenlabs_service.get_conversation_transcript(
                conversation_id=conversation_id
            )

            call_logs = CallLogService().update_call_log_fields(
                id=call_logs_id,
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ),
                },
            )
            print("Conversation ended")

            # Track conversation end
            posthog_service.capture_event(
                event_name="twilio_outbound_conversation_ended",
                distinct_id=f'{call_logs_id} - {campaign_call["phone_number"]}',
                properties={
                    "conversation_id": conversation_id, 
                    # "duration": conv_transcript["metadata"].get("call_duration_secs") if conv_transcript else None,
                    "customer_id": call_log["customer_id"],
                    "campaign_id": campaign_call["campaign_id"],
                    "organisation_id": call_log["organisation_id"],
                    "to_number": campaign_call["phone_number"],
                    "from_number": campaign_call["from_number"],
                    "agent_id": campaign_call["agent_id"]
                }
            )

        except Exception as e:
            posthog_service.capture_event(
                event_name="twilio_outbound_conversation_end_error",
                distinct_id=f'{call_logs_id} - {campaign_call["phone_number"]}',
                properties={
                    "error": str(e)
                }
            )
            print(f"Error ending conversation: {str(e)}")
            traceback.print_exc()


@router.post("/twilio/outbound/hangup")
async def handle_call_status(request: Request, call_log_service: CallLogService = Depends(), campaign_service: CampaignService = Depends(), org_service: OrgService = Depends()):
    """Handle Twilio call status callback"""
    try:
        call_status_map = {
            "completed": "Normal Hangup",
            "no-answer": "Busy"
        }
        form_data = await request.form()
        print("form_data ===>", form_data)

        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        print("call_status ===>", call_status)
        call_duration = int(form_data.get("Duration", 0))*60 # convert to seconds

        # Get call log
        call_log = call_log_service.get_call_log_by_request_uuid(
            request_uuid=call_sid, fields="customer_id, call_logs_id, agent_id, organisation_id"
        )

        if not call_log:
            raise HTTPException(status_code=404, detail="Call log not found")

        # Update call log
        call_log_service.update_call_log_fields(
            id=call_log["call_logs_id"],
            update_data={"hangup_cause": call_status_map.get(call_status, call_status), "duration_billed": call_duration},
        )

        # get the campaign call data
        campaign_call = campaign_service.get_campaign_call_by_id(
            id=call_log["customer_id"], fields="id, total_calls, campaign_id, retry, next_possible_call_date, from_number, phone_number"
        )

        # Update campaign call status
        if call_status == "completed":
            CampaignService().update_campaign_scheduled_call(
                id=call_log["customer_id"], data={"status": "Completed", "retry": campaign_call["retry"] - 1, "total_calls": campaign_call["total_calls"] + 1}
            )
        else:
            CampaignService().update_campaign_scheduled_call(
                id=call_log["customer_id"],
                data={
                    "status": "Not Initiated",
                    "retry": campaign_call["retry"] - 1,
                    "total_calls": campaign_call["total_calls"] + 1,
                    "next_possible_call_date": (
                        datetime.now(pytz.utc).date() + timedelta(days=1)
                    ).strftime("%Y-%m-%d"),
                },
            )

        
        # make the campaign number available
        CampaignPhoneNumberService().update_campaign_ph_no_status(
            campaign_id=campaign_call["campaign_id"],
            phone_number=campaign_call["from_number"],
            data={"status": "available"},
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
            duration_billed_int = int(call_duration) if call_duration else 0

            updated_data = org_service.update_organisation_by_id(id=org_id, data={
                "calls_consumed": (calls_consumed + 1) if duration_billed_int > 0 else calls_consumed,
                "consumed_call_minutes": consumed_call_minutes + int(duration_billed_int)
            })
            print("updated_data ===========>", updated_data)
        else:
            print("Warning: No valid organisation_id found in call_log")


        # Track call completion
        posthog_service.capture_event(
            event_name="twilio_outbound_call_completed",
            distinct_id=f"{call_log['call_logs_id']} - {campaign_call['phone_number']}",
            properties={
                "call_status": call_status,
                "duration": call_duration,
                "customer_id": call_log["customer_id"],
                "campaign_id": campaign_call["campaign_id"],
                "organisation_id": call_log["organisation_id"],
                "to_number": campaign_call["phone_number"],
                "from_number": campaign_call["from_number"],
                "agent_id": call_log["agent_id"]
            }
        )

        return {"message": "Status updated successfully"}

    except Exception as e:
        posthog_service.capture_event(
            event_name="twilio_outbound_hangup_error",
            distinct_id=f"{call_log['call_logs_id']} - {campaign_call['phone_number']}",
            properties={
                "error": str(e)
            }
        )
        print(f"Error in handle_call_status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to handle call status")
