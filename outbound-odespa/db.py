import os
from supabase import create_client, Client as SupabaseClient
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

def insert_sample_data(elevenlabs_conversation_id, phone_number, plivo_request_uuid, agent_id, agent_type):
    """Inserts sample data into the call_conversations table."""

    try:
        data, _ = supabase.table("call_conversations").insert({
            "elevenlabs_conversation_id": elevenlabs_conversation_id,
            "phone_number": phone_number,
            "plivo_request_uuid": plivo_request_uuid,
            'agent_id': agent_id,
            'agent_type': agent_type
        }).execute()
        print(f"Data inserted successfully: {data}")
    except Exception as e:
        print(f"Error inserting data: {e}")
