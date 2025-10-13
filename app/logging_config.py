import logging
import os

# Ensure logs directory exists
os.makedirs('/app/logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    filename='/app/logs/logger.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'  # Append mode to prevent overwriting logs on restart
)

# Create logger instance
logger = logging.getLogger("siso-pipeline")
