from pydantic import BaseModel


class CampaignCallRequest(BaseModel):
    agent_id: int
    campaign_id: int