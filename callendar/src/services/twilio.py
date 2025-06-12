from twilio.rest import Client
from fastapi import FastAPI, HTTPException, Query
from src.core.config import settings
from typing import Optional

class TwilioService:
  def __init__(self, account_sid: str, auth_token: str):
    # account_sid = settings.TWILIO_ACCOUNT_SID
    # auth_token = settings.TWILIO_AUTH_TOKEN
    
    if not account_sid or not auth_token:
      raise ValueError("Twilio credentials are required")
    
    self.client = Client(account_sid, auth_token)


  def get_available_numbers(self, country_code, capabilities=None, area_code=None, limit=10):
        """
        Fetches available phone numbers for a specified country and criteria.
        """
        try:
            available_numbers = self.client.available_phone_numbers(country_code).local.list(
                area_code=area_code,
                sms_enabled=capabilities.get("sms", False) if capabilities else None,
                voice_enabled=capabilities.get("voice", False) if capabilities else None,
                limit=limit,
            )
            return [
                {"phone_number": number.phone_number, "capabilities": number.capabilities}
                for number in available_numbers
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching available numbers: {str(e)}")
        
  def check_number_cost(self, country_code):
        """
        Fetches pricing information for the specified country.
        """
        try:
            pricing = self.client.pricing.v1.phone_numbers.countries(country_code).fetch()
            return pricing.phone_number_prices
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching pricing: {str(e)}")
        
  def purchase_number(self, phone_number, sms_url=None, voice_url=None, friendly_name=None):
     """
     Purchases a phone number from Twilio.
     """
     try:
         purchased_number = self.client.incoming_phone_numbers.create(
             phone_number=phone_number,
             sms_url=sms_url,
             voice_url=voice_url,
             friendly_name=friendly_name,
         )
        
         return {
             "phone_number": purchased_number.phone_number,
             "friendly_name": purchased_number.friendly_name,
             "sid": purchased_number.sid,
         }
     
     except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error purchasing phone number: {str(e)}")

  def add_webhook_endpoint_for_inbound_phone_number(self, phone_number, answer_url = "", hangup_url = ""):
    """
    Adds a webhook endpoint for an inbound phone number.
    """
    try:
        print("phone_number", phone_number)
        phone = self.client.incoming_phone_numbers.list(phone_number=phone_number)
        if phone:
            phone[0].update(
                voice_url=answer_url,
                voice_method="POST",
                status_callback=hangup_url,
                status_callback_method="POST"  
            )
            return True
        return False

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding webhook endpoint for inbound phone number: {str(e)}")





def get_twilio_service(org_id: Optional[str] = None, is_admin: bool = False):
    if not is_admin and not org_id:
        raise HTTPException(400, "Organisation ID is required")
    
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN

    if org_id:
        from src.services.supabase_service import OrganisationSecretsService
        org_secrets = OrganisationSecretsService().get_organisation_secret_by_type(
            organisation_id=org_id, type="twilio_subaccount", fields="id, creds"
        )
        
        if not org_secrets:
            return None
        
        account_sid = org_secrets["creds"]["account_sid"]
        auth_token = org_secrets["creds"]["auth_token"]
    
    return TwilioService(
        account_sid=account_sid,
        auth_token=auth_token
    )

