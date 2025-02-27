import sys
from pathlib import Path
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# There are two approaches we can take:

# Option 1: Import the app module and access its variables
import importlib
app_module = importlib.import_module('dash_imagination.app-sqlite')

# Get the app instance
app = app_module.app

# Server for gunicorn
server = app.server

# Add request logging
@server.before_request
def log_request_info():
    from flask import request
    logger.info(f'Received request for path: {request.path}')
    logger.info(f'Full URL: {request.url}')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f'Starting server on port {port}')
    app.run_server(host='0.0.0.0', port=port, debug=False)