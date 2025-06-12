from datetime import datetime
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import httpx
import pytz
from src.services.supabase_service import CampaignService, CampaignPhoneNumberService, OrganisationContactsService
from src.core.config import settings  # Import settings if needed
from threading import Thread, Lock


class CampaignCallScheduler:
    async def get_campaign_available_phone_numbers(self, campaign_id, retries = 6):
        while retries:
            campaign_phone_numbers = (
                CampaignPhoneNumberService().get_campaign_available_phone_numbers(
                    campaign_id=campaign_id, fields="phone_number, status"
                )
            )

            if campaign_phone_numbers:
                return campaign_phone_numbers

            retries -= 1
            await asyncio.sleep(30)

        return None

    async def get_next_available_call(self, campaign_id):
        print("fetching the next available call")
        campaign = CampaignService().get_campaign_by_id(
            id=campaign_id,
            fields="id, status, organisation_id, availability_start_time, availability_end_time",
        )
        if not campaign:
            return "Campaign Not Found"

        if campaign["status"] != "Running":
            return "Campaign is not running"

        # Convert string times to time objects
        try:
            current_time = datetime.now(pytz.utc).time()
            avail_start = datetime.strptime(
                campaign["availability_start_time"], "%H:%M:%S"
            ).time()
            avail_end = datetime.strptime(
                campaign["availability_end_time"], "%H:%M:%S"
            ).time()

            if avail_start <= avail_end:
                # normal same-day time window
                if not (avail_start <= current_time <= avail_end):
                    return "Campaign is not available to call"

            else:
                # overnight window
                if not (current_time >= avail_start or current_time <= avail_end):
                    return "Campaign is not available to call"

        except Exception as e:
            print(f"Time conversion error: {str(e)}")
            return "Invalid time format"

        campaign_sequence = CampaignService().get_priority_campaign_scheduled_call(
            campaign_id=campaign_id, fields="id"
        )
        if not campaign_sequence:
            # check if all the calls are completed or out of retry
            campaign_calls = CampaignService().get_count_for_pending_campaign_calls(
                campaign_id=campaign_id
            )
            print("campaign_calls ====>", campaign_calls)
            if campaign_calls:
                return "No call to schedule"
            else:
                # update the campaign status to completed
                CampaignService().update_campaign(
                    campaign_id=campaign_id, data={"status": "Completed"}
                )
                return "All calls are completed or out of retry"

        # Rest of the function remains same
        campaign_phone_numbers = await self.get_campaign_available_phone_numbers(campaign_id)
        if not campaign_phone_numbers:
            return "No Phone number available to call"

        # fetch the phone number details
        phone_number_details = OrganisationContactsService().get_orgnisation_number(
            phone_number=campaign_phone_numbers[0]["phone_number"],
            fields="phone_number, service",
        )
        if not phone_number_details:
            return "Phone number not found"

        return {
            "campaign_sequence_id": campaign_sequence["id"],
            "from_number": campaign_phone_numbers[0]["phone_number"],
            "service": phone_number_details["service"],
        }

    async def initiate_call(self, next_call):
        campaign_sequence_id = next_call["campaign_sequence_id"]
        from_number = next_call["from_number"]
        service = next_call["service"]
        print("service to initiate call ====>", service)
        api_url = f"https://{settings.BACKEND_HOSTNAME}/api/v1/call/trigger"

        payload = {
            "customer_id": campaign_sequence_id,
            "service": service,
            "type": "campaign_outbound",
        }
        print("api_url ====>", api_url)
        # update from number

        # update from number
        CampaignService().update_campaign_scheduled_call(
            id=campaign_sequence_id,
            data={"from_number": from_number},
        )

        print("posting the request to this")
        async with httpx.AsyncClient() as client:
            try:
                print("posting the request to this")
                await client.post(api_url, json=payload)  # No need to capture response
                return "Call Secheduled successfully"

            except Exception as e:
                print("\n\n\n ================================================\n\n\n")
                print(f"Error in scheduling the call API request: {e}")
                print("\n\n\n ================================================\n\n\n")
                return "Call Secheduling Failed"

        return "Something went wrong"

    async def schedule_campaign_call(self, campaign_id: str):
        try:
            while True:
                print("scheduling the campaign call ------------------------------")
                next_call = await self.get_next_available_call(campaign_id)
                print("\n\nnext_call ====>", next_call)
                if not next_call or not isinstance(next_call, dict):
                    print("no next call found ------------------------------")
                    return None

                # return None
                print("initiating the call ------------------------------")
                res = await self.initiate_call(next_call)
                print("\n\nres ====>", res)

        except Exception as e:
            print(f"Error in scheduling the call API request: {e}")
            return "Call Secheduling Failed"


class CampaignSchedularService:
    _running_campaigns = set()
    _running_camapigns_lock = Lock()
    _scheduler = BackgroundScheduler()

    @property
    def running_campaigns(self):
        with self._running_camapigns_lock:
            return list(self._running_campaigns)

    def _add_campaign_to_running_campaigns(self, campaign_id):
        with self._running_camapigns_lock:
            self._running_campaigns.add(campaign_id)

    def _remove_campaign_from_running_campaigns(self, campaign_id):
        with self._running_camapigns_lock:
            self._running_campaigns.discard(campaign_id)

    def init_campaign_scheduler(self):
        self._scheduler.add_job(self.schedule_running_campaigns, "interval", seconds=30)
        # self._scheduler.add_job(self.schedule_running_campaigns, "interval", minutes=5)
        self._scheduler.start()

    def shutdown_campaign_scheduler(self):
        self._scheduler.shutdown(wait=False)
        print("Scheduler shut down")

        for thread in threading.enumerate():
            if thread.name.startswith("campaignThread_"):
                print(f"Waiting for {thread.name} to finish...")
                thread.join(timeout=5)

    def create_event_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    def run_campaign_in_new_event_loop(self, campaign_id):
        try:
            print("Running campaign in thread: ", campaign_id)
            # wait until the campagn is running
            loop = self.create_event_loop()
            self._add_campaign_to_running_campaigns(campaign_id)
            loop.run_until_complete(
                asyncio.wait_for(
                    CampaignCallScheduler().schedule_campaign_call(campaign_id),
                    timeout=(5 * 60 * 60),
                )
            )
            print("Campaign scheduled: ", campaign_id)
        
        except asyncio.TimeoutError:
            print(f"Campaign {campaign_id} stopped after 5 hours (timeout).")
        
        except Exception as e:
            print(f"Error in campaign scheduling: {str(e)}")


        finally:
            self._remove_campaign_from_running_campaigns(campaign_id)
            loop.close()

    def schedule_running_campaigns(self):
        try:
            print("Running the cron job")
            campaigns = CampaignService().get_campaigns_running_campaign_within_time_window(fields="id")
            if not campaigns:
                print("No campaigns found")
                return
            campaigns = [
                campaign["id"]
                for campaign in campaigns
                if campaign["id"] not in self.running_campaigns
            ]

            if not campaigns:
                print(
                    "No campaigns found\nalready running campaigns: ", self.running_campaigns
                )
                return

            print("Campaigns found", campaigns)

            # create threads for each campaign
            tasks_threads = [
                Thread(
                    target=self.run_campaign_in_new_event_loop,
                    args=(campaign,),
                    name=f"campaignThread_{campaign}",
                )
                for campaign in campaigns
            ]
            for thread in tasks_threads:
                thread.start()
            print("all campaigns scheduled: ", self.running_campaigns)

        except Exception as e:
            print(f"Error in cron job: {str(e)}")

campaign_scheduler = CampaignSchedularService()
