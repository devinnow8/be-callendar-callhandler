from typing import Dict, Optional
from pydantic import BaseModel, Field

class CreateAgentRequest(BaseModel):
    name: str = Field(..., example="David")
    template_id: Optional[str] = None
    description: Optional[str] = Field(None, example="This is an inbound agent.")
    elevenlabs_agent_id: str = Field(..., example="550e8400-e29b-41d4-a716-446655440000")
    type: str = Field(..., example="inbound")

    class Config:
        schema_extra = {
            "example": {
                "name": "David",
                "template_id": "c56a4180-65aa-42ec-a945-5fd21dec0538",
                "description": "This is an inbound agent.",
                "elevenlabs_agent_id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "inbound",
            }
        }