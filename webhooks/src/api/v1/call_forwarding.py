from fastapi import FastAPI, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv, find_dotenv
import os
from fastapi import APIRouter
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from twilio.rest import Client
from core.config import settings

load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

router = APIRouter()

twilio_client = Client(
    settings.ASHRAM_TWILIO_ACCOUNT_SID,
    settings.ASHRAM_TWILIO_AUTH_TOKEN
)

class TransferRequest(BaseModel):
    call_sid: str
    transfer_target: str

@router.post("/transfer_to_human")
async def forward_call(request: TransferRequest):
    """
    Twilio will POST the call information to this endpoint. 
    This handles the call forwarding logic.
    """
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Please hold while I transfer you to a human agent.</Say>
            <Dial>{settings.ASHRAM_CONTACT}</Dial>
        </Response>"""
    
    twilio_client.calls(request.call_sid).update(twiml=twiml)

    return {"message": "done"}
