from typing import Optional
from sqlmodel import Field, SQLModel, Session
from supabase import create_client, Client
import datetime
import os
from sqlmodel import SQLModel, Field, create_engine
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class CampaignNumber(SQLModel, table=True):
    campaign_number_id: Optional[int] = Field(default=None, primary_key=True)
    campaign_name: str
    campaign_description: Optional[str] = None
    phone_number: str
    first_name: Optional[str] = None
    experience: Optional[str] = None
    venue: Optional[str] = None
    status: str = Field(default="pending")
    number_created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

def create_campaign_number_table_from_schema():
    engine = create_engine("postgresql://", creator=lambda: supabase.connection()) #creates a dummy connection.
    try:
        SQLModel.metadata.create_all(engine)
        print("CampaignNumber table created successfully.")
    except Exception as e:
        print(f"Error creating CampaignNumber table: {e}")

if __name__ == "__main__":
    create_campaign_number_table_from_schema()