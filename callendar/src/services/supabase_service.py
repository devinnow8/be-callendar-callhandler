from datetime import datetime

from fastapi import HTTPException
import pytz
from src.services.provider_handler import PlivoHandler, TwilioHandler
from src.core.config import settings
import uuid
import os
import supabase


SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY


if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set in .env file")

supabase_client = supabase.create_client(SUPABASE_URL, SUPABASE_KEY)


class SupabaseService:
    """Supabase Service Class for managing database interactions."""
    
    def __init__(self):
        """Initialize Supabase Client"""
        self.client = supabase_client

    def get_object_or_none(self, response):
        response = response.model_dump()
        if not response.get('data', None):
            return None
        
        return response['data'][0]
    
    def get_objects(self, response):
        response = response.model_dump()
        print(response)
        if not response.get('data', None):
            return None
        
        return response['data']
    
    
    
    def insert_call_to_supabase(self, id, first_name, last_name, call_date, call_time, call_timezone, call_time_utc):
        """Insert a new scheduled call into Supabase using the Supabase Python client"""
        call_id = str(uuid.uuid4())  # Generate a random UUID as a string
        data = {
            "call_id": call_id,
            "id": id,
            "first_name": first_name,
            "last_name": last_name,
            "call_date": call_date,
            "call_time": call_time,
            "call_timezone": call_timezone,
            "call_time_utc": call_time_utc,
            "status": "Scheduled"
        }

        try:
            response = self.client.table("calls_scheduled").insert(data).execute()
            print("response from supabase ===>", response)
            if response.data:
                print(f"Call {call_id} successfully inserted into Supabase.")
                return call_id
            else:
                print(f"Failed to insert call {call_id}. Response: {response}")
                return None

        except Exception as e:
            print(f"Error inserting call {call_id}: {e}")
            return None


class CallLogService(SupabaseService):
    def insert_call_log_to_supabase(self, data):
        """Insert a new call-log into Supabase using the Supabase Python client"""
        response = self.client.table("call_logs").insert(data).execute()
        return self.get_object_or_none(response)
    
    def get_call_log_by_id(self, id, fields: str = "*"):
        """Query to get all call logs by id"""
        log = self.client.table("call_logs").select(fields).eq("call_logs_id", id).execute()
        return self.get_object_or_none(log)

    def get_call_log_by_request_uuid(self, request_uuid, fields: str = "*"):
        """Query to get all call logs by request_uuid"""
        log = self.client.table("call_logs").select(fields).eq("request_uuid", request_uuid).execute()
        return self.get_object_or_none(log)

    def get_all_call_logs_by_agent_id(self, agent_id, fields: str = "*"):
        """Query to get all call logs for the agent_id"""
        logs = self.client.table("call_logs").select(fields).eq("agent_id", agent_id).order("created_at", desc=True).execute()
        return self.get_objects(logs)
    
    def get_duration_filtered_call_logs_of_an_agent(self, agent_id, start_date: str, fields: str = "*"):
        '''filter based on agent
        '''
        logs = self.client.table("call_logs").select(fields).eq("agent_id", agent_id).gte("created_at", start_date).order("created_at", desc=True).execute()
        return self.get_objects(logs)
    
    def update_call_log_fields(self, id, update_data):
        response = self.client.table("call_logs").update(update_data).eq("call_logs_id", id).execute()
        return self.get_object_or_none(response)
    
    def update_call_log_fields_by_request_uuid(self, request_uuid, update_data):
        response = self.client.table("call_logs").update(update_data).eq("request_uuid", request_uuid).execute()
        return self.get_object_or_none(response)
    
    def get_duration_filtered_call_logs_of_an_org(self, agent_list, start_date: str):
        '''filter based on agents of the org
        AGENT_LIST: is the list of all the agents of an org
        '''
        logs = (
            self.client
            .table("call_logs")
            .select("call_logs_id, duration, duration_billed, total_cost, created_at, agent_id, human_name, hangup_cause")
            .gte("created_at", start_date)   # Filter logs created after start_date
            .in_("agent_id", agent_list)  # Filter logs where agent_id is in agent_list
            .execute()
        )
        return self.get_objects(logs)
    
    def get_total_count_of_call_logs_by_agent_id(self, agent_id):
        """Query to get the total count of records for the agent_id"""
        return self.client.table("call_logs").select("agent_id", count="exact").eq("agent_id", agent_id).execute()

    def get_paginated_call_logs_by_agent_id(self, agent_id, page, page_size, fields: str= "*"):
        """Query to get paginated call logs for the agent_id"""
        logs = self.client.table("call_logs").select(fields).eq("agent_id", agent_id).order("created_at", desc=True).range((page - 1) * page_size, page * page_size - 1).execute()
        return self.get_objects(logs)
class OrgService(SupabaseService):
    """Supabase Service Class for managing Organisation database interactions."""
    def get_organisation_by_sub_domain(self, sub_domain, fields: str = "*"):
        """Query to get organisation by sub_domain"""
        org = self.client.table("organisations").select(fields).eq("sub_domain", sub_domain).execute()
        return self.get_object_or_none(org)
    
    def get_organisation_by_id(self, id, fields: str = "*"):
        """Query to get organisation by id"""
        org = self.client.table("organisations").select(fields).eq("id", id).execute()
        return self.get_object_or_none(org)

    def insert_organisation_to_supabase(self, name, sub_domain, company_name, website, address, phone_number, email):
        data = {
            
            "name": name,
            "sub_domain": sub_domain,
            "company_name": company_name,
            "website": website,
            "address": address,
            "phone_number": phone_number,
            "email": email
        }
        return self.client.table("organisations").insert(data).execute()
    
    def update_organisation_by_id(self, id, data):
        response = self.client.table("organisations").update(data).eq("id", id).execute()
        return self.get_object_or_none(response)

    def get_org_phone_numbers(self, org_id, fields: str = "*"):
        phone_numbers = self.client.table("organisation_contacts").select(fields).eq("org_id", org_id).execute()
        return self.get_objects(phone_numbers)

class UserService(SupabaseService):
    """Supabase Service Class for managing USER database interactions."""
    
    def get_user_by_id(self, id, not_password = True, fields: str = "*"):
        user = self.client.table("users").select(fields).eq("id", id).execute()
        user = self.get_object_or_none(user)
        if user and not_password:
            user.pop('password', None)

        return user

    def get_user_by_email(self, email, not_password = True, fields: str = "*"):
        user =  self.client.table("users").select(fields).eq("email", email).execute()
        user = self.get_object_or_none(user)
        if user and not_password:
            user.pop('password', None)

        return user
    
    def insert_user_to_supabase(self, data):
        user = self.client.table("users").insert(data).execute()
        user = self.get_object_or_none(user)
        if user:
            user.pop('password', None)

        return user


class CampaignService(SupabaseService):
    def get_campaign_by_id(self,id, fields: str = "*"):
        campaign = self.client.table("campaigns").select(fields).eq("id", id).execute()
        return self.get_object_or_none(campaign)

    def get_priority_campaign_scheduled_call(self, campaign_id, fields: str = "*"):
        call = (
            self.client.table("campaign_calls_scheduled")
            .select(fields)
            .eq("campaign_id", campaign_id)
            .eq("status", "Not Initiated")
            .gt("retry", 0)
            .lte("next_possible_call_date", datetime.now(pytz.utc).date())
            .order("retry", desc=True)
            .order("call_at", desc=False)
            .limit(1)
            .execute()
        )
        return self.get_object_or_none(call)
    
    def get_count_for_pending_campaign_calls(self, campaign_id):
        not_initiated_count = self.client.table("campaign_calls_scheduled").select("id", count="exact").eq("campaign_id", campaign_id).eq("status", "Not Initiated").gt("retry", 0).execute()
        
        in_process_count = (
            self.client.table("campaign_calls_scheduled")
            .select("id", count="exact")
            .eq("campaign_id", campaign_id)
            .eq("status", "In Process")
            .execute()

        )
        print("not_initiated_count ====>", not_initiated_count)
        print("in_process_count ====>", in_process_count)
        return (not_initiated_count.count or 0) + (in_process_count.count or 0)

    def get_campaign_calls_filtered_by_status(self, campaign_id, status, fields = "*"):
        phone_numbers = self.client.table("campaign_calls_scheduled").select(fields).eq("status", status).eq("campaign_id", campaign_id).execute()
        return self.get_objects(phone_numbers)

    def update_campaign(self, campaign_id, data):
        response = self.client.table("campaigns").update(data).eq("id", campaign_id).execute()
        return self.get_object_or_none(response)

    def update_campaign_scheduled_call(self, id, data):
        response = self.client.table("campaign_calls_scheduled").update(data).eq("id", id).execute()
        return self.get_object_or_none(response)

    def bulk_update_campaign_scheduled_call_status_by_campaign_id_and_status(self, campaign_id, status, data):
        response = self.client.table("campaign_calls_scheduled").update(data).eq("campaign_id", campaign_id).eq("status", status).execute()
        return self.get_objects(response)

    def bulk_add_campaign_calls(self, calls):
        response = self.client.table("campaign_calls_scheduled").insert(calls).execute()
        return self.get_objects(response)

    def get_campaigns_running_campaign_within_time_window(self, fields: str = "*"):
        current_time = datetime.now(pytz.utc).time()
        campaigns = (
            self.client.table("campaigns")
            .select(fields)
            .eq("status", "Running")
            .lte("availability_start_time", current_time)
            .gte("availability_end_time", current_time)
            .execute()
        )
        return self.get_objects(campaigns)
    
    def get_campaign_call_by_id(self, id, fields: str = "*"):
        campaign_call = self.client.table("campaign_calls_scheduled").select(fields).eq("id", id).execute()
        return self.get_object_or_none(campaign_call)

    def update_campaign_phone_number_status(self, campaign_id, phone_number, status):
        response = self.client.table("campaign_phone_numbers_map").update({"status": status}).eq("campaign_id", campaign_id).eq("phone_number", phone_number).execute()
        return self.get_object_or_none(response)

class OrgUserService(SupabaseService):
    """Supabase Service Class for managing ORG-USER database interactions."""
    def add_user_to_organisation_to_supabase(self, user_id, organisation_id, role: str = "admin"):
        data = {
            "user_id": user_id,
            "organisation_id": organisation_id,
            "role": role,
        }
        return self.client.table("organisation_users_map").insert(data).execute()
    
    def get_org_user_map(self, user_id, org_id):
        org_user = self.client.table("organisation_users_map").select("*").eq("user_id", user_id).eq("organisation_id", org_id).execute()
        return self.get_object_or_none(org_user)
    
    def get_user_orgs(self, user_id):
        user_org = self.client.table("organisation_users_map").select("*").eq("user_id", user_id).execute()
        return self.get_object_or_none(user_org)


class AgentSupabaseService(SupabaseService):
    def insert_agent_to_supabase(self, data):
        agent = self.client.table("agents").insert(data).execute()
        return self.get_object_or_none(agent)
    
    def get_org_agents_by_organisation_id(self, org_id, fields: str = "*"):
        agents = self.client.table("agents").select(fields).eq("organisation_id", org_id).execute()
        return self.get_objects(agents)
    
    def get_agent_by_elevenlabs_agent_id(self, elevenlabs_agent_id, fields : str = "*"):
        agents = self.client.table("agents").select(fields).eq("elevenlabs_agent_id", elevenlabs_agent_id).execute()
        return self.get_object_or_none(agents)
    
    def get_agent_by_id(self, id, fields : str = "*"):
        agents = self.client.table("agents").select(fields).eq("id", id).execute()
        return self.get_object_or_none(agents)


class CampaignPhoneNumberService(SupabaseService):
    def map_campaign_phone_number(self, data):
        return self.client.table("campaign_phone_numbers_map").insert(data).execute()
    
    def get_campaign_available_phone_numbers(self, campaign_id: int, fields: str = "*"):
        response = self.client.table("campaign_phone_numbers_map").select(fields).eq("campaign_id", campaign_id).eq("status", "available").execute()
        return self.get_objects(response)
    
    def update_campaign_ph_no_status(self, campaign_id: int, phone_number: str, data: dict):
        response = self.client.table("campaign_phone_numbers_map").update(data).eq('campaign_id', campaign_id).eq('phone_number', phone_number).execute()
class ScheduledCallService(SupabaseService):
    def get_scheduled_call_by_call_id(self, call_id, fields: str = "*"):
        call = self.client.table("calls_scheduled").select(fields).eq("call_id", call_id).execute()
        return self.get_object_or_none(call)
    
    def update_scheduled_call(self, call_id, data):
        response = self.client.table("calls_scheduled").update(data).eq("call_id", call_id).execute()
        return self.get_object_or_none(response)

class OrganisationContactsService(SupabaseService):
    def get_organisation_contact_by_id(self, org_id, fields: str = "*"):
        contacts = self.client.table("organisation_contacts").select(fields).eq("org_id", org_id).execute()
        contacts =  self.get_objects(contacts)
        if contacts:
            return contacts[0]
        return None

    def get_orgnisation_number(self, phone_number, fields: str = "*"):
        contacts = self.client.table("organisation_contacts").select(fields).eq("phone_number", phone_number).execute()
        return self.get_object_or_none(contacts)

class InboundCampaignService(SupabaseService):
    def get_inbound_campaign_by_id(self, id, fields: str = "*"):
        campaign = self.client.table("inbound_campaigns").select(fields).eq("id", id).execute()
        return self.get_object_or_none(campaign)
    
    def update_inbound_campaign(self, campaign_id, data):
        response = self.client.table("inbound_campaigns").update(data).eq("id", campaign_id).execute()
        return self.get_object_or_none(response)
    
    def stop_inbound_campaign(self, campaign_id, org_id):
        try:
            # fetch inbound campaign phone numbers
            inbound_campaign_phone_number_service = InboundCampaignPhoneNumberService()
            inbound_campaign_phone_numbers = inbound_campaign_phone_number_service.get_inbound_campaign_phone_numbers_by_campaign_id(campaign_id, fields="phone_number, status")
            if not inbound_campaign_phone_numbers:
                raise HTTPException(status_code=400, detail="Inbound Campaign Phone Numbers Not Found")

            # fetch organisation phone numbers
            org_contacts_service = OrganisationContactsService()
            organisation_contacts = org_contacts_service.get_organisation_contact_by_id(org_id, fields="phone_number, service")
            if not organisation_contacts:
                raise HTTPException(status_code=400, detail="Organisation Phone Numbers Not Found")

            # Create a dictionary of phone numbers to their services
            organisation_phone_numbers = {
                contact["phone_number"]: contact["service"] 
                for contact in organisation_contacts
            }
            
            inactive_phone_numbers = []

            # add webhook endpoint to twilio for each phone number of the campaign
            for phone_number in inbound_campaign_phone_numbers:
                try:
                    print("Processing phone_number:", phone_number)
                    if phone_number["status"] == "inactive":
                        inactive_phone_numbers.append(phone_number["phone_number"])
                        continue

                    if organisation_phone_numbers.get(phone_number["phone_number"]) == "twilio":
                        twilio_service = TwilioHandler()
                        response = twilio_service.stop_incoming_service(
                            phone_number["phone_number"]
                        )
                        if response:
                            inactive_phone_numbers.append(phone_number["phone_number"])
                       
                    elif organisation_phone_numbers[phone_number["phone_number"]] == "plivo":
                        plivo_service = PlivoHandler()
                        response = plivo_service.stop_incoming_service(phone_number=phone_number["phone_number"])
                        if response.get("message", None) == "changed":
                            inactive_phone_numbers.append(phone_number["phone_number"])

                except Exception as e:
                    print("Error unlinking Phone Number to Application: ", e)
        
            print("inactive_phone_numbers", inactive_phone_numbers)
            inbound_campaign_phone_number_service.update_inbound_campaign_phone_numbers_status(campaign_id, inactive_phone_numbers, "inactive")
            
            if len(inactive_phone_numbers) !=  len(inbound_campaign_phone_numbers):
                return None
            
            return self.update_inbound_campaign(campaign_id, {"status": "Stopped"})
        except HTTPException as e:
            print("HTTPExcepraise etion block,", str(e))
            return None

        except Exception as e:
            print("Exception block,", str(e))
            return None



class InboundCampaignPhoneNumberService(SupabaseService):
    def get_inbound_campaign_phone_number_map_by_phone_number(self, phone_number, fields: str = "*"):
        response = self.client.table("inbound_campaign_numbers").select(fields).eq("phone_number", phone_number).execute()
        return self.get_object_or_none(response)

    def get_inbound_campaign_phone_numbers_by_campaign_id(self, campaign_id, fields: str = "*"):
        response = self.client.table("inbound_campaign_numbers").select(fields).eq("campaign_id", campaign_id).execute()
        return self.get_objects(response)
    
    def update_inbound_campaign_phone_numbers_status(self, campaign_id, phone_numbers, status):
        response = self.client.table("inbound_campaign_numbers").update({"status": status}).eq("campaign_id", campaign_id).in_("phone_number", phone_numbers).execute()
        return self.get_objects(response)

class StripeService(SupabaseService):

    async def get_stripe_subscription_by_org_id(self, org_id: str, fields: str = "*"):
        response = (
            self.client.table("subscriptions")
            .select(fields)
            .eq("org_id", org_id)
            .execute()
        )
        return self.get_object_or_none(response)
