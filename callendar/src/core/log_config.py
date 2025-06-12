import logging
import sys

# Configure the root logger
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG if needed
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Logs to console
        logging.FileHandler("/var/log/fastapi_app.log")  # Logs to file (EC2)
    ],
)

# Create a logger instance
logger = logging.getLogger(__name__)
