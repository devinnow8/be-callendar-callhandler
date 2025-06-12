import os
from supabase import create_client, Client as SupabaseClient
from dotenv import load_dotenv
import requests
import time
import json
from tqdm import tqdm

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# NGROK_URL = os.getenv("NGROK_URL")
BACKEND_BASE_ENDPOINT = os.getenv("BACKEND_BASE_ENDPOINT")

supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

campaign_id = 9
campaign_number_id = 2186

response = supabase.table("campaign_numbers_sequence").select("campaign_number_id").gt("campaign_number_id", campaign_number_id).eq("campaign_id", campaign_id).eq("phone_quality_check", "valid").neq("first_name", "Guest").order("campaign_sequence_number").execute()
data = response.data

headers = {'Content-Type': 'application/json'}
url = f"{BACKEND_BASE_ENDPOINT}/plivo/call"

for i in tqdm(data, desc="Processing records"):
    pl = {"customer_id": str(i["campaign_number_id"])}
    print(pl)
    response = requests.post(url, json=pl, headers=headers)
    call_logs_id = response.json().get("call_logs_id")

    print(f"Call logs id: {call_logs_id}")
    while True:
        check_response = supabase.table("call_logs").select("hangup_cause").eq("call_logs_id", call_logs_id).execute()
        print(check_response)
        if check_response.data[0]["hangup_cause"]:
            print(f"hangup_cause populated for call_logs_id: {call_logs_id}")
            break  # Exit the loop when conversation_id is populated
        else:
            print(f"Waiting for hangup_cause to populate for call_logs_id: {call_logs_id}")
            time.sleep(5)  # Wait for 5 seconds before checking again
