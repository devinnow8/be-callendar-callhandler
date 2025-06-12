from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class CreateOrganisationRequest(BaseModel):
    name: str = Field(..., example="Ai Caller")
    company_name: str = Field(..., example="Ai Caller")
    phone_number: str = Field(..., example="+1234567890")
    address: Dict[str, Any] = Field(..., example={"street": "123 Main St", "city": "New York", "zip": "10001"})
    website: Optional[str] = Field(None, example="https://aicaller.com")
    email: str = Field(..., example="aicaller@gmail.com")
    user_id: str = Field(..., example="uuid")  # Temporary field, will extract later from token