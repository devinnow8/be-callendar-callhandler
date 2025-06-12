import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from django.conf import settings
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi import APIRouter
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv()

router = APIRouter()

# Email configuration
SMTP_SERVER = settings.EMAIL_SMTP_SERVER
SMTP_PORT = settings.EMAIL_SMTP_PORT
SMTP_USERNAME = settings.EMAIL_SMTP_USERNAME
SMTP_PASSWORD = settings.EMAIL_SMTP_PASSWORD

# Request schema for email data
class EmailRequest(BaseModel):
    recipient: str
    subject: str
    message: str
    cc: Optional[str] = None  # Optional CC field
    start_time: Optional[str] = None  # Optional start time in ISO 8601 format
    end_time: Optional[str] = None  # Optional end time in ISO 8601 format
    time_zone: Optional[str] = "CET"  # Default to CET


@router.post("/email/send-email")
async def send_email(request: EmailRequest):
    """
    API endpoint to send emails with a calendar .ics file attached only if CC exists.
    """
    try:
        # Extract email details
        recipient = request.recipient
        subject = request.subject
        message_body = request.message
        cc_list = request.cc.split(",") if request.cc else []  # Split CC addresses into a list
        time_zone = pytz.timezone(request.time_zone or "CET")  # Default to CET if no time zone is provided

        # Default to the current time if start_time or end_time is not provided
        now = datetime.now(time_zone)
        start_time = (
            datetime.fromisoformat(request.start_time).astimezone(time_zone)
            if request.start_time
            else now
        )
        end_time = (
            datetime.fromisoformat(request.end_time).astimezone(time_zone)
            if request.end_time
            else start_time + timedelta(hours=1)  # Default duration: 1 hour
        )

        # Format times for ICS
        start_time_ics = start_time.strftime("%Y%m%dT%H%M%SZ")
        end_time_ics = end_time.strftime("%Y%m%dT%H%M%SZ")

        # Create email message
        msg = MIMEMultipart()
        msg["From"] = SMTP_USERNAME
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["Cc"] = ", ".join(cc_list)  # Convert CC list back to a string for email headers

        # Attach email body
        msg.attach(MIMEText(message_body, "plain"))

        # Only attach the calendar invite if CC is provided
        if cc_list:
            calendar_invite = f"""BEGIN:VCALENDAR
                            VERSION:2.0
                            CALSCALE:GREGORIAN
                            METHOD:REQUEST
                            BEGIN:VEVENT
                            UID:info@callendar.app
                            DTSTAMP:{start_time_ics}
                            DTSTART:{start_time_ics}
                            DTEND:{end_time_ics}
                            SUMMARY:Shuttle Booking - Art of Living Ashram
                            DESCRIPTION: Shuttle booking from Oppenau Station to the Art of Living Ashram.
                            LOCATION: Art of Living International Ashram BadAntogast
                            STATUS:CONFIRMED
                            ATTENDEE:mailto:{SMTP_USERNAME}
                            ATTENDEE:mailto:{recipient}
                            SEQUENCE:0
                            END:VEVENT
                            END:VCALENDAR"""

            # Attach the ICS content as a file
            ics_part = MIMEBase("text", "calendar", method="REQUEST")
            ics_part.set_payload(calendar_invite)
            encoders.encode_base64(ics_part)
            ics_part.add_header(
                "Content-Disposition",
                "attachment; filename=shuttle_booking.ics"
            )
            msg.attach(ics_part)

        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure the connection
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

            # Combine recipient and CC addresses
            all_recipients = [recipient] + cc_list
            server.sendmail(SMTP_USERNAME, all_recipients, msg.as_string())

        return {"success": True, "message": "Email sent successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending email: {str(e)}")