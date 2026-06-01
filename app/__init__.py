from flask import Flask
from flask_cors import CORS
from .config import Config
from .logging_config import configure_logging


configure_logging()

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

from app import views
