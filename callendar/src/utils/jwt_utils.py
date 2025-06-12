import jwt
import datetime
from src.core.config import settings

# Function to create JWT token
def create_jwt_token(data: dict):
    expiration = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    data.update({"exp": expiration})
    return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm="HS256")

def extract_data_from_token(token: str):
    try:
        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token.split(" ", 1)[1]
            
        decoded_data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return decoded_data  # Returns the original data stored in the token
    except jwt.ExpiredSignatureError:
        return {"error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}
