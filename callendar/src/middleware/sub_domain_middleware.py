from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlparse
class SubdomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")  # Get full Origin URL
        subdomain = None  # Default to None if extraction fails
        parsed_origin = None
        if origin:
            # Extract hostname from origin
            try:
                parsed_origin = urlparse(origin).hostname  # Extract hostname
                if parsed_origin:
                    subdomain = parsed_origin.split(".")[0]
            except Exception as e:
                pass

        request.state.organisation = subdomain  # Attach extracted subdomain to request state
        response = await call_next(request)
        return response
