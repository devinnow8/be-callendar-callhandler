from fastapi import APIRouter, Depends, HTTPException
from src.services.elevenlabs_service import ElevenLabsService
from src.middleware.auth_middleware import get_current_user
from src.services.auth import auth_service
from src.core.config import settings
from fastapi.responses import StreamingResponse
from io import BytesIO  
import requests

router = APIRouter()



@router.get("/conversations")
def get_conversations(
    agent_id: str,
    user=Depends(get_current_user),
    page_size: int = 10,
    cursor: str = None, # bu default NONE
    call_successful: bool = None, # taking as none by default
):
    """
    Fetch conversations for the current user's agents from ElevenLabs API.
    """
    # 1. Validate agent ownership
    if agent_id:
        agent = auth_service.client.table("agents").select("*").eq("agent_id", agent_id).execute()
        if not agent:
            raise HTTPException(
                status_code=404, detail="Agent not found."
            )
        print("agent", agent)
        if agent.data[0]["user_id"] != user["user"].user.id:
            raise HTTPException(
                status_code=403, detail="You do not own the specified agent."
            )

    # 2. Prepare query parameters for ElevenLabs API
    params = {
        "cursor": cursor,
        "agent_id": agent_id,
        "call_successful": call_successful,
        "page_size": page_size,
    }
    # Remove None values from params
    params = {k: v for k, v in params.items() if v is not None}

    # 3. Call ElevenLabs API
    elevenlabs_api_key = settings.ELEVENLABS_API_KEY
    if not elevenlabs_api_key:
        raise HTTPException(
            status_code=500, detail="Missing ELEVENLABS_API_KEY in environment variables."
        )

    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json",
    }
    url = "https://api.elevenlabs.io/v1/convai/conversations"

    response = requests.get(url, headers=headers, params=params)

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to fetch conversations: {response.text}",
        )

    # 4. Return response to the client
    return response.json()


@router.get("/conversations/{conversation_id}/audio")
def get_conversation_audio(
    conversation_id: str,
) :
    """
    Fetches audio for a specific conversation from the ElevenLabs API.

    :param conversation_id: The ID of the conversation for which to fetch audio.
    :return: Audio file or error response.
    """
    # Validate input
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Conversation ID is required.")

    # Get ElevenLabs API key from environment or configuration
    elevenlabs_api_key = settings.ELEVENLABS_API_KEY
    if not elevenlabs_api_key:
        raise HTTPException(
            status_code=500, detail="Missing ELEVENLABS_API_KEY in environment."
        )

    # Construct the ElevenLabs API URL
    url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}/audio"

    # Set up headers with the API key
    headers = {
        "xi-api-key": elevenlabs_api_key,
    }

    # Make the GET request to ElevenLabs API
    response = requests.get(url, headers=headers, stream=True)

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to fetch conversation audio: {response.text}",
        )

    # Return the audio file as a streaming response
    return StreamingResponse(BytesIO(response.content), media_type="audio/mpeg")



@router.get("/conversations/{conversation_id}")
def get_conversation_transcript(
    conversation_id: str,
    elevenlabs_service: ElevenLabsService = Depends()
) :
    """
    Fetches transcript for a specific conversation from the ElevenLabs API.

    :param conversation_id: The ID of the conversation for which to fetch audio.
    :return: conversaton messages or error response.
    """
    
    # Validate input
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Conversation ID is required.")
    
    try:
        response = elevenlabs_service.get_conversation_transcript(conversation_id=conversation_id)
    
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail="Failed to fetch conversation transcript."
        )
    metadata = response['metadata']
    data = {
        "agent_id": response.get("agent_id", None),
        "conversation_id": response.get('conversation_id', conversation_id),
        "status": response.get('status', None),
        "transcript":  response.get('transcript', None),
        "client_data": response.get('conversation_initiation_client_data', None),
        "overview": {
            "summary": response['analysis'].get("transcript_summary"),
            "status": response['analysis'].get("call_successful"),
            "data_collection": response['analysis'].get("data_collection_results", None)
        }

    }

    return data

