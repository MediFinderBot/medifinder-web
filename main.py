"""
Entry point for the Medifinder Web application.
"""
import os
from app import create_app
from app.config import DEBUG, PORT, HOST

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    # Run the application
    app.run(debug=DEBUG, host=HOST, port=PORT)