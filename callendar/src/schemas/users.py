from pydantic import BaseModel, Field

class CreateUserRequest(BaseModel):
    email: str = Field(..., example="john@gmail.com")
    first_name: str = Field(..., example="John")
    last_name: str = Field(..., example="Doe")