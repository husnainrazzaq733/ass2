import os
import sys

# Add your project directory to the sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask app object from app.py
from app import app as application
