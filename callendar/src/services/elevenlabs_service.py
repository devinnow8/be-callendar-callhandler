
from fastapi import Depends
from src.core.config import settings
from elevenlabs import ConversationalConfig, ElevenLabs


ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY


if not ELEVENLABS_API_KEY :
    raise ValueError("ElevenLabs Key must be set in .env file")

elevenlabs_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)



class ElevenLabsService:
    def __init__(self):
        self.client = elevenlabs_client

    def create_agent(self, name, settings):
        # TODO: add other agent settings later
        return self.client.conversational_ai.create_agent(
            conversation_config=ConversationalConfig(
                name = name
            ),
        )
    
    def get_conversation_transcript(self, conversation_id):
        response =  self.client.conversational_ai.get_conversation(
                    conversation_id=conversation_id,
                )
        
        return response.model_dump()
    
    def get_conversation_audio(self, conversation_id):
        response = self.client.conversational_ai.get_conversation_audio(
                    conversation_id=conversation_id,
                )
        
        
        