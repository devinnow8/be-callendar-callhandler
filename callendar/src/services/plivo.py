import plivo
from src.core.config import settings


class PlivoService:
    def __init__(self):
        self.client = plivo.RestClient(
            settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN
        )

    def unlink_phone_number_and_application(self, phone_number):
        print("unlinking phone number and application", phone_number)
        response = self.client.numbers.update(number=phone_number, app_id="")
        response = response.__dict__
        return response
