from typing import Optional
from pydantic import BaseModel

# Pydantic models
class UserLogin(BaseModel):
    email: str
    password: str

class UserRegister(BaseModel):
    email: str
    password: str
    name: Optional[str] = None