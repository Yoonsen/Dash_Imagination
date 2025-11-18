import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the src directory to the Python path
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, src_path)

# Run the application
from dash_imagination.app import app

# Server for gunicorn
server = app.server

# Add request logging
@server.before_request
def log_request_info():
    from flask import request
    logger.info(f'Received request for path: {request.path}')
    logger.info(f'Full URL: {request.url}')

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8066))
    logger.info(f'Starting server on port {port}')
    app.run_server(host='0.0.0.0', port=port, debug=True, dev_tools_hot_reload=False)