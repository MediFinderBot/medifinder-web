"""
Initialize the Flask application.
"""
import os
import logging
from flask import Flask
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Enable CORS
    CORS(app)
    
    # Configure secret key for sessions
    app.secret_key = os.environ.get('SECRET_KEY', 'medifinder-dev-key')
    
    # Configure session to use filesystem
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    
    # Register routes
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)
    
    return app