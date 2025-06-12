from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.v1 import email, call_forwarding, ashram_courses

app = FastAPI(
    title="Email Service API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (can be restricted to specific domains)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email.router, prefix="/api/v1")
app.include_router(call_forwarding.router, prefix="/api/v1")
app.include_router(ashram_courses.router, prefix="/api/v1")
