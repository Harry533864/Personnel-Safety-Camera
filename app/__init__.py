from flask import Flask
from flask_cors import CORS
from .auth import install_admin_auth
from .config import Config
from .logging_config import configure_logging


configure_logging()

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
install_admin_auth(app)

from app import views
from app.runtime import maybe_start_runtime

maybe_start_runtime()
