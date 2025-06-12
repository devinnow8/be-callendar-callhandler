from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.middleware.sub_domain_middleware import SubdomainMiddleware
from src.core.config import settings
from src.api.v1 import auth
from src.api.v1 import callendar
from src.api.v1 import onboarding
from src.api.v1 import agents
from src.api.v1 import conversations
# from src.api.v1 import twilio
from src.api.v1 import call_metrics
from src.api.v1 import call_scheduling
from src.api.v1 import users
from src.api.v1 import organisation
from src.api.v1 import inbound_ashram
from src.api.v1 import email
from src.api.v1 import authentication
from src.api.v1 import outbound_odespa
from src.api.v1 import campaign
from src.api.v1 import outbound_scheduled_calls
from src.api.v1 import plivo_inbound
from src.api.v1 import twilio_outbound
from src.api.v1 import twilio_inbound
from src.api.v1 import twilio_outbound_scheduled_calls
from apscheduler.schedulers.background import BackgroundScheduler
from src.services.cronjob import scheduler
import threading

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],

)
app.add_middleware(
    SubdomainMiddleware
)


app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(authentication.router, prefix=settings.API_V1_STR)
app.include_router(callendar.router, prefix= settings.API_V1_STR)
app.include_router(onboarding.router, prefix= settings.API_V1_STR)
app.include_router(agents.router, prefix= settings.API_V1_STR)
app.include_router(conversations.router, prefix= settings.API_V1_STR)
# app.include_router(twilio.router, prefix= settings.API_V1_STR)
app.include_router(call_metrics.router, prefix=settings.API_V1_STR)
app.include_router(call_scheduling.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(organisation.router, prefix=settings.API_V1_STR)
app.include_router(inbound_ashram.router, prefix=settings.API_V1_STR)
app.include_router(email.router, prefix=settings.API_V1_STR)
app.include_router(outbound_odespa.router, prefix=settings.API_V1_STR)
app.include_router(campaign.router, prefix=settings.API_V1_STR)
app.include_router(outbound_scheduled_calls.router, prefix=settings.API_V1_STR)
app.include_router(twilio_inbound.router, prefix=settings.API_V1_STR)
app.include_router(plivo_inbound.router, prefix=settings.API_V1_STR)
app.include_router(twilio_outbound.router, prefix=settings.API_V1_STR)
app.include_router(twilio_outbound_scheduled_calls.router, prefix=settings.API_V1_STR)

@app.get("/")
async def check_status():
    return {"message": "Hey congrats you've reached the backend"}
