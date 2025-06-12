import traceback
from datetime import datetime, timedelta
import pytz
from elevenlabs.conversational_ai.conversation import Conversation, ConversationConfig
from fastapi import HTTPException
from src.services.elevenlabs_service import ElevenLabsService
from src.services.supabase_service import CallLogService, AgentSupabaseService
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class AgentConfig:
    prompt: Optional[str] = None
    first_message: Optional[str] = None
    language: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


class BaseConversationHandler:
    def __init__(
        self,
        audio_interface,
    ):

        self.audio_interface = audio_interface
        self.elevenlabs_service = ElevenLabsService()
        self.conversation = None

    async def create_config(self, data: Optional[Dict] = None) -> ConversationConfig:
        """
        Creates a ConversationConfig object based on the provided data dictionary.

        Args:
            data (Optional[Dict]): Dictionary containing configuration parameters
                Supported keys:
                - dynamic_variables (dict): Variables to be used in conversation
                - prompt (str): Custom prompt for the agent
                - first_message (str): First message from the agent
                - language (str): Language for the conversation

        Returns:
            ConversationConfig: Configured conversation settings
        """
        if not data:
            return ConversationConfig()

        config_params = {}

        # Extract dynamic variables if present

        if dynamic_vars := data.get("dynamic_variables"):
            config_params["dynamic_variables"] = dynamic_vars

        # Build agent configuration
        agent = AgentConfig(
            prompt=data.get("prompt"),
            first_message=data.get("first_message"),
            language=data.get("language"),
        )

        # Only add agent configuration if any values are set
        if agent_dict := agent.to_dict():
            config_params["conversation_config_override"] = {
                "agent": {
                    key: value if key != "prompt" else {"prompt": value}
                    for key, value in agent_dict.items()
                }
            }

        return ConversationConfig(**config_params)

    async def setup_conversation(self, agent: Dict):
        """Set up the conversation with ElevenLabs"""
        data = agent.get("data", {})

        # create agent config
        config = await self.create_config(data)

        # pass in the agent
        self.conversation = Conversation(
            client=self.elevenlabs_service.client,
            config=config,
            agent_id=agent["elevenlabs_agent_id"],
            requires_auth=True,
            audio_interface=self.audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )
        self.conversation.start_session()
        print("Conversation started")

    async def handle_message(self, message):
        """Handle incoming audio message"""
        if not message:
            return
        if hasattr(self.audio_interface, "handle_plivo_message"):
            await self.audio_interface.handle_plivo_message(message)
        else:
            await self.audio_interface.handle_twilio_message(message)

    async def end_conversation(self):
        """End the conversation and return conversation data"""
        try:
            if not self.conversation:
                return None

            self.conversation.end_session()
            self.conversation.wait_for_session_end()

            conversation_id = self.conversation._conversation_id
            conv_transcript = self.elevenlabs_service.get_conversation_transcript(
                conversation_id=conversation_id
            )

            print(f"\n\n\n\nconv transcript: {conv_transcript}")
            return {
                "elevenlabs_conversation_id": conversation_id,
                "duration": conv_transcript["metadata"].get("call_duration_secs", None),
            }
        except Exception as e:
            print(f"Error ending conversation: {str(e)}")
            traceback.print_exc()
            return None
