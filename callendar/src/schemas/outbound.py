from pydantic import BaseModel

class OutboundCallRequest(BaseModel):
    customer_id: str