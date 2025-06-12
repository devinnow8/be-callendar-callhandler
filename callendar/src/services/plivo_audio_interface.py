import asyncio
import base64
import json
from fastapi import WebSocket
from elevenlabs.conversational_ai.conversation import AudioInterface
from starlette.websockets import WebSocketDisconnect, WebSocketState

class PlivoAudioInterface(AudioInterface):
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.input_callback = None
        self.loop = asyncio.get_event_loop()

    def start(self, input_callback):
        self.input_callback = input_callback

    def stop(self):
        self.input_callback = None

    def output(self, audio: bytes):
        asyncio.run_coroutine_threadsafe(self.send_audio_to_plivo(audio), self.loop)

    def interrupt(self):
        asyncio.run_coroutine_threadsafe(self.send_clear_message_to_plivo(), self.loop)

    async def send_audio_to_plivo(self, audio: bytes):
        try:
            audio_payload = base64.b64encode(audio).decode("utf-8")
            message = {
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-l16",
                    "sampleRate": 8000,
                    "payload": audio_payload
                }}
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            print("WebSocket not connected.")

    async def send_clear_message_to_plivo(self):
        try:
            clear_message = {"event": "clear"}
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(clear_message))
        except (WebSocketDisconnect, RuntimeError) as e:
            print("Error sending clear message to Plivo:", e)

    async def handle_plivo_message(self, data: dict):
        try:
            event_type = data.get("event")
            if event_type == "media":
                payload = data.get("mediaPayload")
                if payload is None and "media" in data:
                    payload = data["media"].get("payload")
                if payload:
                    try:
                        audio_data = base64.b64decode(payload)
                        
                        if self.input_callback:
                            self.input_callback(audio_data)
                    except Exception as decode_error:
                        print("Error decoding payload:", decode_error)
                # Do not print anything if payload is missing.
            elif event_type == "start":
                pass
            elif event_type == "stop":
                pass
        except Exception as e:
            print("Error processing Plivo message:", e)
