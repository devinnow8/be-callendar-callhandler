import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from core.config import settings

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
    is_shuttle_email: Optional[bool] = False  # Determines if ICS file should be sent

@router.get("/")
async def check_status():
    return {"message": "Webhook is working."}

@router.post("/email")
async def send_email(request: EmailRequest):
    try:
        print("Starting email preparation...")

        # Extract email details
        recipient = request.recipient
        subject = request.subject
        message_body = request.message
        is_shuttle_email = request.is_shuttle_email  # Check if shuttle email is required
        print(f"Recipient: {recipient}, Subject: {subject}, Shuttle Email: {is_shuttle_email}")

        cc_list = request.cc.split(",") if request.cc else []  # Split CC addresses into a list
        print(f"CC List: {cc_list}")

        # Set start and end times in UTC
        now = datetime.utcnow()
        start_time = (
            datetime.fromisoformat(request.start_time)
            if request.start_time
            else now
        )
        end_time = (
            datetime.fromisoformat(request.end_time)
            if request.end_time
            else start_time + timedelta(hours=1)  # Default duration: 1 hour
        )

        print(f"Start Time (UTC): {start_time}, End Time (UTC): {end_time}")

        # Format times for ICS in UTC
        start_time_ics = start_time.strftime("%Y%m%dT%H%M%SZ")
        end_time_ics = end_time.strftime("%Y%m%dT%H%M%SZ")
        print(f"ICS Start Time: {start_time_ics}, ICS End Time: {end_time_ics}")

        # Create email message
        msg = MIMEMultipart()
        msg["From"] = SMTP_USERNAME
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["Cc"] = ", ".join(cc_list)  # Convert CC list back to a string for email headers

        # Attach email body
        msg.attach(MIMEText(message_body, "plain"))
        print("Email body attached.")

        # Attach ICS file **only if is_shuttle_email is True**
        if is_shuttle_email:
            print("Preparing calendar invite for shuttle booking...")

            calendar_invite = f"""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}@yourapp.com
DTSTAMP:{start_time_ics}
DTSTART:{start_time_ics}
DTEND:{end_time_ics}
SUMMARY:Shuttle Booking - Art of Living Ashram
DESCRIPTION: Shuttle booking from Oppenau Station to the Art of Living Ashram.
LOCATION: Art of Living International Ashram Bad Antogast
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
            print("Calendar invite attached.")

        # Send email
        print("Connecting to SMTP server...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure the connection
            print("Logging into SMTP server...")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

            # Combine recipient and CC addresses
            all_recipients = [recipient] + cc_list
            print(f"Sending email to: {all_recipients}")
            server.sendmail(SMTP_USERNAME, all_recipients, msg.as_string())

        print("Email sent successfully.")
        return {"success": True, "message": "Email sent successfully"}

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending email: {str(e)}")
