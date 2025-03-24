"""
Initialize the Flask application.
"""
import os
import logging
import asyncio
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Async patch for Flask
def patch_flask_for_async():
    """
    Monkey patch Flask to allow async handlers.
    """
    # Reference: https://flask.palletsprojects.com/en/2.3.x/async-await/
    import inspect
    from functools import wraps
    from flask import Flask
    
    original_route = Flask.route
    
    @wraps(original_route)
    def async_aware_route(self, rule, **options):
        """Wraps the route to support async functions."""
        def decorator(f):
            if inspect.iscoroutinefunction(f):
                @wraps(f)
                def sync_f(*args, **kwargs):
                    """Converts an async function to sync for flask."""
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    return loop.run_until_complete(f(*args, **kwargs))
                return original_route(self, rule, **options)(sync_f)
            return original_route(self, rule, **options)(f)
        return decorator
    
    Flask.route = async_aware_route

def create_app():
    """Create and configure the Flask application."""
    # Apply patch for async support
    patch_flask_for_async()
    
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