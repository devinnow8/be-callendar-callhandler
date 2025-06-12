from datetime import datetime
import uuid
from fastapi import HTTPException, Request, WebSocket
import json
import requests
from src.services.posthog_service import posthog_service
from src.services.conversation_handler import BaseConversationHandler
from src.services.outbound import CampaignOutboundCall, ScheduledOutboundCall
from src.services.supabase_service import (
    CallLogService,
    AgentSupabaseService,
    InboundCampaignPhoneNumberService,
    InboundCampaignService,
    OrgService,
)
from src.core.config import settings
from src.services.provider_handler import PlivoHandler, TwilioHandler
from typing import Dict, Any
from src.middleware.stripe_middleware import validate_stripe_subscription

class BaseCallHandler:
    '''maintains call log details and handles call events'''
    MEDIA_STREAM_URL = f"wss://{settings.BACKEND_HOSTNAME}/api/v1/call/media-stream"
    ANSWER_URL = f"https://{settings.BACKEND_HOSTNAME}/api/v1/call/answer"
    HANGUP_URL = f"https://{settings.BACKEND_HOSTNAME}/api/v1/call/hangup"

    def __init__(self, provider: str, type: str) -> None:
        self.call_log_service = CallLogService()
        self.provider = provider
        self.provider_service = self.get_call_provider_service()
        self.type = type

    def get_call_provider_service(self) -> Any:
        """Set the call provider"""
        if self.provider == "twilio":
            return TwilioHandler()

        if self.provider == "plivo":
            return PlivoHandler()

        raise HTTPException(status_code=400, detail="Invalid call provider")

    async def get_call_log_details(self, call_logs_id: str) -> Dict:
        """Get call log details"""
        return self.call_log_service.get_call_log_by_id(id=call_logs_id)

    async def create_call_log(
        self, call_details: Dict
    ) -> Dict:
        """Create call log entry
        =========================
            call_details = {
                "call_logs_id": Optional[call_logs_id],
                "customer_id": customer_id,
                "to_number": to_number,
                "from_number": from_number,
                "usecase_id": usecase_id,
                "agent_id": agent_id,
                "organisation_id": organisation_id,
                "request_uuid": request_uuid,
                "type": type,
                "service": provider,
            }
        =========================
        """
        print("creating call log entry")
        print(f"call details: {call_details}")
        return self.call_log_service.insert_call_log_to_supabase(
            {
                "call_logs_id": call_details.get("call_logs_id", str(uuid.uuid4())),
                "customer_id": call_details["customer_id"],
                "to_number": call_details["to_number"],
                "from_number": call_details["from_number"],
                "usecase_id": call_details["usecase_id"],
                "agent_id": call_details["agent_id"],
                "organisation_id": call_details["organisation_id"],
                "request_uuid": call_details["request_uuid"],
                "type": call_details["type"],
                "service": call_details["service"],
            }
        )

    async def handle_hangup_call_log_update(
        self,
        request_uuid: str,
        hangup_cause: str,
        duration_billed: str | None = None,
        total_cost: str | None = None,
    ) -> Dict:
        """Handle hangup webhook for both Plivo and Twilio"""
        # update the call log
        print("updating call log on hangup")
        update_data = {
            "hangup_cause": hangup_cause,
            "duration_billed": duration_billed,
        }
        if total_cost:

            update_data["total_cost"] = total_cost

        call_log = self.call_log_service.update_call_log_fields_by_request_uuid(
            request_uuid=request_uuid, update_data=update_data
        )
        print(f"call log updated on hangup: {call_log}")
        return call_log

    async def handle_update_call_log_on_conversation_end(
        self, call_logs_id: str, conversation_data: Dict
    ) -> Dict | None:
        """Update call log with conversation data"""
        if not conversation_data:
            return None

        return self.call_log_service.update_call_log_fields(
            id=call_logs_id, update_data=conversation_data
        )

    async def handle_call_stream(
        self, call_logs_id: str, agent_data: Dict, websocket: WebSocket
    ) -> None:
        """Handle call stream"""
        # get audio interface
        audio_interface = await self.provider_service.get_audio_interface(websocket=websocket)

        # setup conversation handler
        conversation_handler = BaseConversationHandler(audio_interface=audio_interface)
        try:
            # setup conversation
            await conversation_handler.setup_conversation(agent=agent_data)
            # capture event
            posthog_service.capture_event(
                event_name="conversation_started",
                distinct_id=call_logs_id,
                properties={
                    "call_logs_id": call_logs_id,
                    "type": self.type,
                    "service": self.provider,
                    "timestamp": datetime.now().isoformat()
                }
            )

            # handle messages
            async for message in audio_interface.websocket.iter_text():
                if message:
                    await conversation_handler.handle_message(json.loads(message))

        except Exception as e:
            print(f"Error in call stream: {str(e)}")
            # capture event
            posthog_service.capture_event(
                event_name="conversation_error",
                distinct_id=call_logs_id,
                properties={
                    "error": str(e),
                    "type": self.type,
                    "service": self.provider,
                    "call_logs_id": call_logs_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            # end conversation and update call log
            conversation_data = await conversation_handler.end_conversation()
            
            # capture event
            posthog_service.capture_event(
                event_name="conversation_ended",
                distinct_id=call_logs_id,
                properties={
                    "call_logs_id": call_logs_id,
                    "type": self.type,
                    "service": self.provider,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            if conversation_data:
                await self.handle_update_call_log_on_conversation_end(
                    call_logs_id=call_logs_id, conversation_data=conversation_data
                )

    async def update_org_calls_consumed(self, org_id: str, duration_billed: int = 0):
        org_service = OrgService()
        org_calls_data = org_service.get_organisation_by_id(org_id, fields="calls_consumed, consumed_call_minutes")
        print("org_calls_data ===========>", org_calls_data)

        # update the org calls consumed and consumed call minutes
        calls_consumed = org_calls_data.get("calls_consumed") if org_calls_data.get("calls_consumed") else 0
        consumed_call_minutes = org_calls_data.get("consumed_call_minutes") if org_calls_data.get("consumed_call_minutes") else 0

        return org_service.update_organisation_by_id(id=org_id, data={
            "calls_consumed": calls_consumed + 1,
            "consumed_call_minutes": consumed_call_minutes + duration_billed
        })


class OutboundCallHandler(BaseCallHandler):
    async def get_call_type_outbound_service(self, customer_id: str):
        print(f"getting call type outbound service for type: {self.type} and customer id: {customer_id}")
        if self.type == "campaign_outbound":
            return CampaignOutboundCall(customer_id=customer_id)

        if self.type == "scheduled_outbound":
            return ScheduledOutboundCall(customer_id=customer_id)

        raise HTTPException(status_code=400, detail="Invalid outbound call type")

    async def handle_call_trigger(self, customer_id: str):
        """Trigger call on provider service"""
        # initialize the outbound call service
        print("triggering outbound call")
        outbound_call_service = await self.get_call_type_outbound_service(customer_id=customer_id)
        print("outbound call service initialized")
        call_details = await outbound_call_service.get_call_details()

        # validate organisation subscription
        is_subscription_valid = await validate_stripe_subscription(org_id=call_details["organisation_id"])
        if not is_subscription_valid:
            await outbound_call_service.stop_outbound_calls(campaign_id=call_details["usecase_id"], reason="Subscription limit reached")
            raise HTTPException(status_code=403, detail="Subscription has no remaining calls or minutes")

        call_details["call_logs_id"] = str(uuid.uuid4())
        call_details["service"] = self.provider
        print(f"fetched call details: {call_details}")
        # create the call on the provider service
        print("creating call on provider service")
        try:
            sid = self.provider_service.create_call(
                from_number=call_details["from_number"],
                to_number=call_details["to_number"],
                answer_url=f"{self.ANSWER_URL}?provider={self.provider}&type={self.type}&call_logs_id={call_details['call_logs_id']}",
                hangup_url=f"{self.HANGUP_URL}?provider={self.provider}&type={self.type}&call_logs_id={call_details['call_logs_id']}",
            )
            print(f"call created on provider service: {sid}")
        except Exception as e:
            sid = None
            print(f"error creating call on provider service: {e}")

        # create a call log and update the call details
        print("creating call log")
        call_details["request_uuid"] = sid

        call_log = await self.create_call_log(
            call_details=call_details
        )
        print(f"call log created: {call_log}")
        call_details = await outbound_call_service.update_call_details_on_trigger(
            status=bool(sid), call_details=call_details
        )
        print(f"call details updated on trigger: {call_details}")

        # return the call details
        return call_log

    async def handle_call_hangup(
        self,
        request: Request,
    ) -> Dict:
        print("handling call hangup")

        data = await self.provider_service.extract_data_from_hangup_request(request)
        print(f"extracted data from hangup request: {data}")
        # update the call log
        call_log = await self.handle_hangup_call_log_update(
            request_uuid=data["request_uuid"],
            hangup_cause=data["hangup_cause"],
            duration_billed=data.get("duration_billed", None),
            # total_cost=data.get("total_cost", None),
        )
        print(f"call log updated on hangup: {call_log}")

        # update the org calls consumed and consumed call minutes
        org_update_data = await self.update_org_calls_consumed(
            org_id=call_log["organisation_id"],
            duration_billed=data.get("duration_billed"),
        )
        print(f"org update data: {org_update_data}")

        # update the call details
        outbound_call_service = await self.get_call_type_outbound_service(
            customer_id=call_log["customer_id"]
        )
        call_details = await outbound_call_service.update_call_details_on_hangup(
            status=data["status"]
        )
        print(f"call details updated on hangup: {call_details}")

        # call the end call webhook
        end_call_url = call_details.get("end_call_url", None)  # In case of scheduled calls, end_call_url is present and in case of campaign calls, end_call_url is not present
        if end_call_url:
            payload = {
                "call_id": call_log["customer_id"],
                "call_logs_id": call_log["call_logs_id"],
                "to_number": call_log["to_number"],
                "from_number": call_log["from_number"],
                "agent_id": call_log["agent_id"],
                "hangup_cause": call_log["hangup_cause"],
                "duration": call_log["duration_billed"],
                "elevenlabs_conversation_id": call_log["elevenlabs_conversation_id"],
            }
            try:
                await requests.post(end_call_url, json=payload)
            except Exception as e:
                print(f"error posting to end call url: {e}")

        return call_log

    async def handle_call_answer(self, request: Request):
        # create socket url
        call_logs_id = request.query_params.get("call_logs_id")
        socket_url = f"{self.MEDIA_STREAM_URL}/{self.provider}/{self.type}/{call_logs_id}"
        print(f"socket url: {socket_url}")
        # generate answer esponse
        answer = await self.provider_service.generate_answer_response(
            socket_url=socket_url
        )
        return {
            "call_logs_id": call_logs_id,
            "answer": answer
        }

    async def get_agent_conversation_data(self, call_logs_id: str):
        # get call log details
        print(f"getting call log details for call logs id: {call_logs_id}")
        call_log = await self.get_call_log_details(call_logs_id)
        print(f"call log: {call_log}")
        # get agent data
        outbound_call_service = await self.get_call_type_outbound_service(
         customer_id=call_log["customer_id"]
        )
        print(f"outbound call service: {outbound_call_service}")
        # get agent data
        return await outbound_call_service.get_agent_conversation_data()

    async def handle_call_stream(self, call_logs_id: str,  websocket: WebSocket):
        # get agent data
        print(f"getting agent data for call logs id: {call_logs_id}")
        agent_data = await self.get_agent_conversation_data(call_logs_id)

        # handle call stream
        await super().handle_call_stream(
            call_logs_id=call_logs_id, agent_data=agent_data, websocket=websocket
        )

class InboundCallHandler(BaseCallHandler):
    async def get_call_details(self, request: Request):
        print("extracting data from answer request")
        data = await self.provider_service.extract_data_from_answer_request(request)
        print("data extracted from answer request", data)
        # get campaign details from from number
        campaign_phone_number_service = InboundCampaignPhoneNumberService()
        campaign_phone_number = campaign_phone_number_service.get_inbound_campaign_phone_number_map_by_phone_number(phone_number=data["to_number"])
        print("campaign phone number", campaign_phone_number)
        if not campaign_phone_number:
            raise HTTPException(status_code=400, detail="Campaign phone number not found")

        # get campaign details from campaign id
        campaign_service = InboundCampaignService()
        campaign = campaign_service.get_inbound_campaign_by_id(campaign_phone_number["campaign_id"])
        print("campaign", campaign)
        if not campaign:
            raise HTTPException(status_code=400, detail="Campaign not found")

        return {
            "customer_id": campaign["id"],
            "to_number": data["to_number"],
            "from_number": data["from_number"], 
            "usecase_id": campaign["id"],
            "agent_id": campaign["agent_id"],
            "organisation_id": campaign["organisation_id"],
            "request_uuid": data["request_uuid"],
            "type": "inbound",
            "service": self.provider    
        }

    async def handle_call_answer(self, request: Request):
        # get call details
        print("getting call details")
        call_details = await self.get_call_details(request)
        print(f"call details: {call_details}")

        # validate organisation subscription
        is_subscription_valid = await validate_stripe_subscription(org_id=call_details["organisation_id"])
        if not is_subscription_valid:
            # update the campaign status to stopped
            inbound_campaign_service = InboundCampaignService()
            inbound_campaign_service.stop_inbound_campaign(campaign_id=call_details['usecase_id'], org_id=call_details['organisation_id'])
            raise HTTPException(status_code=403, detail="Stripe subscription has no remaining calls or minutes")



        # create call log
        call_log = await self.create_call_log(call_details)
        print(f"call log created: {call_log}")

        # generate answer response
        print("generating answer response")
        answer = await self.provider_service.generate_answer_response(
            socket_url=f"wss://{settings.BACKEND_HOSTNAME}/api/v1/call/media-stream/{self.provider}/{self.type}/{call_log['call_logs_id']}"
        )
        return {
            "call_logs_id": call_log["call_logs_id"],
            "answer": answer
        }

    async def get_agent_conversation_data(self, call_logs_id: str):
        # get call log details
        call_log = await self.get_call_log_details(call_logs_id)
        print("call log", call_log)
        # get agent data
        agent_service = AgentSupabaseService()
        agent = agent_service.get_agent_by_id(call_log["agent_id"], fields="id, elevenlabs_agent_id, metadata")
        return agent

    async  def handle_call_stream(self, call_logs_id: str,  websocket: WebSocket):
        # get agent data
        print(f"getting agent data for call logs id: {call_logs_id}")
        agent_data = await self.get_agent_conversation_data(call_logs_id)
        print("agent data", agent_data)
        # handle call stream
        await super().handle_call_stream(call_logs_id=call_logs_id, agent_data=agent_data, websocket=websocket)

    async def handle_call_hangup(
        self,
        request: Request,
    ) -> Dict:
        print("handling call hangup")
        data = await self.provider_service.extract_data_from_hangup_request(request)
        print(f"extracted data from hangup request: {data}")
        call_log = await self.handle_hangup_call_log_update(
            request_uuid=data["request_uuid"],
            hangup_cause=data["hangup_cause"],
            duration_billed=data.get("duration_billed", None),
            # total_cost=data.get("total_cost", None),
        )
        print(f"call log updated on hangup: {call_log}")

        # update the org calls consumed and consumed call minutes
        await self.update_org_calls_consumed(
            org_id=call_log["organisation_id"],
            duration_billed=data.get("duration_billed"),
        )
        return call_log

def get_call_handler(type: str, provider: str):
    if type in ["scheduled_outbound", "campaign_outbound"]:
        return OutboundCallHandler(provider=provider, type=type)
    
    elif type == "inbound":
        return InboundCallHandler(provider=provider, type=type)
    
    else:
        raise HTTPException(status_code=400, detail="Invalid call type")
