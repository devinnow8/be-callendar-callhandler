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
from src.services.supabase_service import CallLogService, AgentSupabaseService, OrgService, InboundCampaignPhoneNumberService, InboundCampaignService
from src.services.twilio_audio_interface import TwilioAudioInterface
import uuid
from fastapi import FastAPI
from twilio.rest import Client as TwilioClient
from src.core.config import settings
from src.core.log_config import logger
from src.services.supabase_service import InboundCampaignService
from fastapi import HTTPException
from src.services.twilio import get_twilio_service
from src.services.posthog_service import posthog_service
from src.middleware.stripe_middleware import validate_stripe_subscription
router = APIRouter()

# ngrok = "caribou-open-mistakenly.ngrok-free.app"
ngrok = "mongrel-absolute-mongrel.ngrok-free.app"

@router.post("/twilio/inbound/answer/{campaign_id}")
async def handle_incoming_call( 
    request: Request,
    campaign_id: str,
    call_log_supabase_service: CallLogService = Depends(),
    inbound_campaign_service: InboundCampaignService = Depends(),
):
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "Unknown")
        from_number = form_data.get("From", "Unknown")
        to_number = form_data.get("To", "Unknown")
        
        # Track inbound call received
        posthog_service.capture_event(
            event_name="twilio_inbound_call_received",
            distinct_id=f"{call_sid} - {from_number}",
            properties={
                "campaign_id": campaign_id,
                "from_number": from_number,
                "to_number": to_number,
                "call_sid": call_sid
            }
        )

        print(f"Incoming call: CallSid={call_sid}, From={from_number}")

        # get campaign details
        campaign = await inbound_campaign_service.get_inbound_campaign_by_id(campaign_id)
        print("campaign ===========>", campaign)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # validate stripe subscription
        is_subscription_valid = await validate_stripe_subscription(org_id=campaign["organisation_id"])
        print("is_subscription_valid ===========>", is_subscription_valid)
        if not is_subscription_valid:
            # update the campaign status to stopped
            print("stopping the campaign ------------------------------")
            await inbound_campaign_service.stop_inbound_campaign(campaign_id=campaign_id, org_id=campaign["organisation_id"])
            print("campaign stopped ------------------------------")
            raise HTTPException(status_code=403, detail="Stripe subscription has no remaining calls or minutes")

        # insert call to service
        call = await call_log_supabase_service.insert_call_log_to_supabase(
            {
                "usecase_id": campaign_id,
                "agent_id": campaign["agent_id"],
                "phone_number": from_number,
                "request_uuid": call_sid,
                "organisation_id": campaign["organisation_id"],
                "type": "inbound"
            }
        )
        print("calll ===>", call)

        # Track inbound call initiated
        posthog_service.capture_event(
            event_name="twilio_inbound_call_initiated",
            distinct_id=f"{call['call_logs_id']} - {from_number}",
            properties={
                "call_logs_id": call["call_logs_id"],
                "campaign_id": campaign_id,
                "agent_id": campaign["agent_id"],
                "customer_id": call["customer_id"],
                "from_number": from_number,
                "to_number": to_number,
                "organisation_id": campaign["organisation_id"],
            }
        )

        response = VoiceResponse()
        connect = Connect()
        connect.stream(
            # url=f"wss://{ngrok}/api/v1/twilio/inbound/media-stream-eleven/{call['call_logs_id']}"
            url=f"wss://{settings.BACKEND_HOSTNAME}/api/v1/twilio/inbound/media-stream-eleven/{call['call_logs_id']}"
        )
        response.append(connect)
        return HTMLResponse(content=str(response), media_type="application/xml")
    
    except HTTPException as e:
        posthog_service.capture_event(
            event_name="twilio_inbound_stripe_subscription_error",
            distinct_id=f"{call_sid} - {from_number}",
            properties={
                "error": str(e),
            }
        )
        raise e

    except Exception as e:
        posthog_service.capture_event(
            event_name="twilio_inbound_call_error",
            distinct_id=f"{call['call_logs_id']} - {from_number}",
            properties={
                "error": str(e),
                "campaign_id": campaign_id,
                "from_number": from_number,
                "to_number": to_number,
                "call_sid": call_sid
            }
        )
        logger.error(f"Error handling incoming call: {e}")
        raise HTTPException(status_code=500, detail=f"Error handling incoming call: {str(e)}")


@router.websocket("/twilio/inbound/media-stream-eleven/{call_log_id}")
async def handle_media_stream(
    websocket: WebSocket,
    call_log_id: str,
    call_log_supabase_service: CallLogService = Depends(),
    agent_supabase_service: AgentSupabaseService = Depends(),
    elevenlabs_service: ElevenLabsService = Depends(),
    org_service: OrgService = Depends(),
):
    await websocket.accept()
    print("WebSocket connection opened")
    logger.info("WebSocket connection opened")
    # Retrieve the call log ID from the query parameters

    audio_interface = TwilioAudioInterface(websocket)
    try:
        call_log = call_log_supabase_service.get_call_log_by_id(
            id=call_log_id, fields="call_logs_id, request_uuid, agent_id, phone_number, to_number, organisation_id, usecase_id, customer_id"
        )
        # get agent from db
        db_agent = agent_supabase_service.get_agent_by_id(
            id=call_log["agent_id"], fields="id, elevenlabs_agent_id"
        )
        if not db_agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Track conversation start
        posthog_service.capture_event(
            event_name="twilio_inbound_conversation_started",
            distinct_id=f"{call_log['call_logs_id']} - {call_log['phone_number']}",
            properties={
                "agent_id": call_log["agent_id"],
                "call_logs_id": call_log_id,
                "campaign_id": call_log["usecase_id"],
                "from_number": call_log["phone_number"],
                "to_number": call_log["to_number"],
                "organisation_id": call_log["organisation_id"],
                "customer_id": call_log["customer_id"],
            }
        )

        # start conversation    
        conversation = Conversation(
            client=elevenlabs_service.client,
            agent_id=db_agent["elevenlabs_agent_id"],
            requires_auth=True,  # Security > Enable authentication
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
        hangup_cause = "Websocket Disconnected"
        print("WebSocket disconnected")
        logger.info("CWebSocket disconnected")
        posthog_service.capture_event(
            event_name="twilio_inbound_websocket_disconnected",
            distinct_id=f"{call_log_id} - {call_log['phone_number']}",
            properties={
                "reason": "WebSocket Disconnected"
            }
        )
    except Exception:
        hangup_cause = "Websocket Handler Error"
        print("Error occurred in WebSocket handler:")
        logger.info("Error occurred in WebSocket handler:")
        traceback.print_exc()
    finally:
        try:
            conversation.end_session()
            conversation.wait_for_session_end()
            conversation_id = conversation._conversation_id

            org_id = call_log.get("organisation_id", None)
            twilio_service = get_twilio_service(org_id=org_id)
            call = twilio_service.client.calls(call_log["request_uuid"]).fetch()
            print("call ===>", call)
            print("call dictionary ===>", call.__dict__)
            conv_transcript = elevenlabs_service.get_conversation_transcript(
                conversation_id=conversation_id
            )

            call_logs = call_log_supabase_service.update_call_log_fields(
                id=call_log_id,
                update_data={
                    "elevenlabs_conversation_id": conversation_id,
                    "duration_billed": call.duration,
                    "duration": conv_transcript["metadata"].get(
                        "call_duration_secs", None
                    ),
                },
            )
            logger.info("Conversation ended")
            print("Conversation ended")

            # Track conversation end
            posthog_service.capture_event(
                event_name="twilio_inbound_conversation_ended",
                distinct_id=f"{call_log_id} - {call_log['phone_number']}",
                properties={
                    "conversation_id": conversation_id,
                    # "duration": conv_transcript["metadata"].get("call_duration_secs") if conv_transcript else None,
                    "call_logs_id": call_log_id,
                    "campaign_id": call_log["usecase_id"],
                    "customer_id": call_log["customer_id"],
                    "from_number": call_log["phone_number"],
                    "to_number": call_log["to_number"],
                    "organisation_id": call_log["organisation_id"],
                    "agent_id": call_log["agent_id"],
                }
            )
        except Exception as e:
            call_log_supabase_service.update_call_log_fields(
                id=call_log_id,
                update_data={
                    "hangup_cause": "End Conversation Session Error"
                },
            )

            logger.info("Error ending conversation session:")
            print("Error ending conversation session:")
            traceback.print_exc()
            posthog_service.capture_event(
                event_name="twilio_inbound_conversation_end_error",
                distinct_id=f"{call_log_id} - {call_log['phone_number']}",
                properties={
                    "error": str(e),
                    "call_logs_id": call_log_id,
                    "campaign_id": call_log["usecase_id"],
                    "customer_id": call_log["customer_id"],
                    "from_number": call_log["phone_number"],
                    "to_number": call_log["to_number"],
                    "organisation_id": call_log["organisation_id"],
                    "agent_id": call_log["agent_id"],
                    "hangup_cause": "End Conversation Session Error"
                }
            )


@router.post("/twilio/inbound/hangup")
async def handle_hangup(request: Request, 
                        call_log_service: CallLogService = Depends(), 
                        org_service: OrgService = Depends(), 
                        inbound_campaign_phone_number_service: InboundCampaignPhoneNumberService = Depends(),
                        inbound_campaign_service: InboundCampaignService = Depends()):
    
    print("in handle_hangup ------------------------------")
    form_data = await request.form()
    print("form_data ===>", form_data)
    call_sid = form_data.get("CallSid", "Unknown")
    print(f"Hangup: CallSid={call_sid}")
    # Extract call status and duration from form data
    call_status = form_data.get("CallStatus", "unknown")
    call_duration = int(form_data.get("Duration", 0))*60 # convert to seconds
    phone_number_called = form_data.get("To", "Unknown")
    from_number = form_data.get("From", "Unknown")

    # update the call log
    call_log = call_log_service.update_call_log_fields_by_request_uuid(
        request_uuid=call_sid,
        update_data={
            "hangup_cause": "Normal Hangup" if call_status == "completed" else "Failed",
            "duration_billed": call_duration
        },
    )
    if not call_log:
        print("in not call_log")
        inbound_campaign_phone_number = await inbound_campaign_phone_number_service.get_active_inbound_campaign_phone_number_by_phone_number(phone_number=phone_number_called, fields="campaign_id")
        print("inbound_campaign_phone_number ===========>", inbound_campaign_phone_number)
        inbound_campaign = await inbound_campaign_service.get_inbound_campaign_by_id(inbound_campaign_phone_number["campaign_id"], fields="organisation_id")
        print("inbound_campaign ===========>", inbound_campaign)
        org_id = inbound_campaign["organisation_id"]
        print("org_id ===========>", org_id)

        posthog_service.capture_event(
            event_name="twilio_inbound_call_ended",
            distinct_id=f'{call_sid} - {from_number}',
            properties={
                "call_sid": call_sid,
                "from_number": from_number,
                "to_number": phone_number_called,
                "call_status": call_status,
                "duration": call_duration,
                "hangup_cause": "Normal Hangup" if call_status == "completed" else "Failed"
            }
        )

    else:
        print("in call_log")
        org_id = call_log["organisation_id"]
        print("org_id ===========>", org_id)

        posthog_service.capture_event(
        event_name="twilio_inbound_call_ended",
        distinct_id=f'{call_log["call_logs_id"]} - {call_log["phone_number"]}',
        properties={
            "call_logs_id": call_log["call_logs_id"],
            "campaign_id": call_log["usecase_id"],
            "customer_id": call_log["customer_id"],
            "agent_id": call_log["agent_id"],
            "organisation_id": call_log["organisation_id"],
            "to_number": call_log["to_number"],
            "from_number": call_log["phone_number"],
            "call_status": call_status,
            "duration": call_duration,
            "hangup_cause": "Normal Hangup" if call_status == "completed" else "Failed"
        }
    )

    if org_id:
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
    else:
        print("Warning: No valid organisation_id found in call_log")


    return {"message": "Hangup received"}
