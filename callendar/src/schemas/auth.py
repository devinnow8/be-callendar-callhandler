from typing import Dict, Any, Optional
from pydantic import BaseModel

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str