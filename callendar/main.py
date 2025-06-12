from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.api.v1 import call_handling
from contextlib import asynccontextmanager
from src.services.cronjob import campaign_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    campaign_scheduler.init_campaign_scheduler()
    print("Application started, scheduler initialized")

    yield

    # Shutdown
    campaign_scheduler.shutdown_campaign_scheduler()
    print("Application shutting down, scheduler stopped")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan   
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],

)

app.include_router(call_handling.router, prefix=settings.API_V1_STR)


@app.get("/")
async def check_status():
    return {"message": "Hey congrats you've reached the backend"}
