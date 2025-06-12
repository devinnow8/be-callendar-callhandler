from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
from fastapi import requests
import httpx
from src.api.v1.outbound_odespa import schedule_campaign_call
from src.services.supabase_service import CampaignService
from src.core.config import settings  # Import settings if needed
backend_url = settings.BACKEND_BASE_ENDPOINT

# Initialize APScheduler
scheduler = BackgroundScheduler()

# Function to run the async task correctly
def run_async_task():
    print("Running the cron job")
    campaigns = CampaignService().get_campaigns_running_campaign_within_time_window(
        fields="id"
    )
    if not campaigns:
        print("No campaigns found")
        return
    print("Campaigns found", campaigns)
    async def wrapper():
        tasks = [schedule_campaign_call(campaign["id"]) for campaign in campaigns]
        await asyncio.gather(*tasks)  # Run tasks concurrently

    asyncio.run(wrapper()) 
    print("Campaigns scheduled")

# Add job to scheduler (run every 5 minutes)
scheduler.add_job(run_async_task, "interval", minutes=5)
# scheduler.add_job(run_async_task, "interval", seconds=20)
scheduler.start()
