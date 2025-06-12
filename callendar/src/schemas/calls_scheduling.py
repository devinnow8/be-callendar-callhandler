from pydantic import BaseModel, Field
from datetime import datetime
import pytz

class ScheduleCallRequest(BaseModel):
    id: int = Field(..., example=1)
    first_name: str = Field(..., example="John")
    last_name: str = Field(..., example="Doe")
    call_date: str = Field(..., example="2025-03-01")  # YYYY-MM-DD format
    call_time: str = Field(..., example="14:30")  # HH:MM:SS format
    call_timezone: str = Field(..., example="America/New_York")  # Timezone string

    def get_utc_datetime(self):
        """ Convert given call_time from provided timezone to UTC """
        try:
            self.call_timezone = self.call_timezone.strip()  # Remove leading/trailing spaces & newlines
            
            if self.call_timezone not in pytz.all_timezones:
                raise ValueError(f"Invalid timezone: {self.call_timezone}")
            
            local_tz = pytz.timezone(self.call_timezone)
            local_dt = datetime.strptime(f"{self.call_date} {self.call_time}", "%Y-%m-%d %H:%M")
            local_dt = local_tz.localize(local_dt)  # Assign timezone
            utc_dt = local_dt.astimezone(pytz.UTC)  # Convert to UTC
            return utc_dt.isoformat()
        
        except Exception as e:
            raise ValueError(f"Invalid timezone or datetime format: {str(e)}")
