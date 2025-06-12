from abc import ABC, abstractmethod

from fastapi import Request, WebSocket
from twilio.twiml.voice_response import VoiceResponse, Connect
from fastapi.responses import HTMLResponse
from src.services.plivo_audio_interface import PlivoAudioInterface
from src.services.twilio_audio_interface import TwilioAudioInterface
from src.core.config import settings
from plivo import RestClient as PlivoClient
from twilio.rest import Client as TwilioClient
from fastapi import HTTPException

plivo_client = PlivoClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
twilio_client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


class BaseProviderHandler(ABC):
    @abstractmethod
    def create_call(self, *args, **kwargs):
        pass

    @abstractmethod
    async def generate_answer_response(self, *args, **kwargs):
        pass

    @abstractmethod
    async def extract_data_from_hangup_request(self, *args, **kwargs):
        pass
    
    @abstractmethod
    async def extract_data_from_answer_request(self, *args, **kwargs):
        pass

    @abstractmethod
    async def get_audio_interface(self, websocket: WebSocket, *args, **kwargs):
        pass
    
    @abstractmethod
    async def stop_incoming_service(self, phone_number: str):
        pass

class TwilioHandler(BaseProviderHandler):
    def __init__(self):
        self.client = twilio_client

    def create_call(
        self, to_number: str, from_number: str, answer_url: str, hangup_url: str
    ):
        call = self.client.calls.create(
            to=to_number,
            from_=from_number,
            # machine_detection="Enable",
            # machine_detection_timeout=1,
            time_limit=2700,
            url=answer_url,
            status_callback=hangup_url,
            status_callback_event=["completed"],
        )
        return call.sid

    async def generate_answer_response(self, socket_url: str):
        response = VoiceResponse()
        connect = Connect()
        connect.stream(url=socket_url)
        response.append(connect)
        return HTMLResponse(content=str(response), media_type="application/xml")

    async def extract_data_from_hangup_request(self, request: Request):
        form_data = await request.form()
        print(f"twilio hangup form data: {form_data}")
        call_sid = form_data.get("CallSid", "Unknown")
        call_status = form_data.get("CallStatus", "unknown")
        call_duration = int(form_data.get("Duration", 0))*60
        status = call_status == "completed"
        hangup_cause = "Normal Hangup" if call_status == "completed" else "Busy"
        return {
            "request_uuid": call_sid,
            "duration_billed": call_duration,
            "hangup_cause": hangup_cause,
            "status": status,
        }

    async def extract_data_from_answer_request(self, request: Request):
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "Unknown")
        to_number = form_data.get("To", "Unknown")
        from_number = form_data.get("From", "Unknown")

        return {
            "request_uuid": call_sid,
            "to_number": to_number,
            "from_number": from_number,
        }

    async def get_audio_interface(self, websocket: WebSocket):
        return TwilioAudioInterface(websocket)

    async def stop_incoming_service(self, phone_number: str):
        """
        Adds a webhook endpoint for an inbound phone number.
        """
        try:
            print("phone_number", phone_number)
            phone = self.client.incoming_phone_numbers.list(phone_number=phone_number)
            if phone:
                phone[0].update(
                    voice_url="",
                    voice_method="POST",
                    status_callback="",
                    status_callback_method="POST"  
                )
                return True
            return False

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error adding webhook endpoint for inbound phone number: {str(e)}")

class PlivoHandler(BaseProviderHandler):
    def __init__(self):
        self.client = plivo_client

    def create_call(
        self, to_number: str, from_number: str, answer_url: str, hangup_url: str
    ):
        call = self.client.calls.create(
            from_=from_number,
            to_=to_number,
            machine_detection="hangup",
            machine_detection_time=2000,
            answer_url=answer_url,
            hangup_url=hangup_url,
            answer_method="POST",
            time_limit=2700,
        )
        return call["request_uuid"]

    async def generate_answer_response(self, socket_url: str):
        xml_response = (
            f"<Response>"
            f"<Stream bidirectional='true' contentType='audio/x-l16;rate=8000' keepCallAlive='true'>"
            f"{socket_url}"
            f"</Stream>"
            f"</Response>"
        )
        return HTMLResponse(content=str(xml_response), media_type="text/xml")

    async def extract_data_from_hangup_request(self, request: Request):
        form_data = await request.form()

        call_id = form_data.get("CallUUID")
        hangup_cause = form_data.get("HangupCauseName")
        duration_billed = int(form_data.get("BillDuration", 0))
        # total_cost = form_data.get("TotalRate")

        status = hangup_cause == "Normal Hangup"

        return {
            "request_uuid": call_id,
            "hangup_cause": hangup_cause,
            "duration_billed": duration_billed,
            "status": status,
            # "total_cost": total_cost,
        }

    async def extract_data_from_answer_request(self, request: Request):
        form_data = await request.form()
        call_id = form_data.get("CallUUID")
        to_number = form_data.get("To", "Unknown")
        from_number = form_data.get("From", "Unknown")

        return {
            "request_uuid": call_id,
            "to_number": to_number,
            "from_number": from_number,
        }

    async def get_audio_interface(self, websocket: WebSocket):
        return PlivoAudioInterface(websocket)

    async def stop_incoming_service(self, phone_number: str):
        print("unlinking phone number and application", phone_number)
        response = self.client.numbers.update(number=phone_number, app_id="")
        response = response.__dict__
        return response
