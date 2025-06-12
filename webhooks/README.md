# Run Application

```
uvicorn main:app --port 5001 --reload
```


# Docker Webhook

```
docker run -d --network host --name webhook_tunnel cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJhIjoiOTBjMjU5YTFkNjI0NWY3MzI3ZWM1OTFmYWVjYmIyOTYiLCJ0IjoiODUxMWY3M2YtNGIxMy00NDJlLTg1YmYtMTIzMmJjYmJiZDlkIiwicyI6IllUTmpNV0ZsTjJRdE9UZGhOUzAwT1RrM0xUbGlPRFV0TjJKbU9HSXlaalppWW1ZMCJ9
```

# Curl Request

```
curl --location --request POST "https://w1.callendar.app/api/v1/email" \
  --header "Content-Type: application/json" \
  --data-raw '{
    "recipient": "krishnakalyan3@gmail.com",
    "subject": "hi",
    "message": "test"
  }'
```