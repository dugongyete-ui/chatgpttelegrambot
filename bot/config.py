import yaml
import dotenv
import os
from pathlib import Path

config_dir = Path(__file__).parent.parent.resolve() / "config"

# load yaml config
with open(config_dir / "config.yml", 'r') as f:
    config_yaml = yaml.safe_load(f)

# load .env config
config_env = dotenv.dotenv_values(config_dir / "config.env")

# config parameters - prefer environment variables over config.yml for secrets
telegram_token = os.environ.get("TELEGRAM_TOKEN") or config_yaml["telegram_token"]
openai_api_key = os.environ.get("OPENAI_API_KEY") or config_yaml["openai_api_key"]
openai_api_base = config_yaml.get("openai_api_base", None)
openrouter_api_key = os.environ.get("OPENROUTER_API_KEY") or config_yaml.get("openrouter_api_key", None)
openrouter_api_base = config_yaml.get("openrouter_api_base", "https://openrouter.ai/api/v1")
allowed_telegram_usernames = config_yaml["allowed_telegram_usernames"]
new_dialog_timeout = config_yaml["new_dialog_timeout"]
enable_message_streaming = config_yaml.get("enable_message_streaming", True)
return_n_generated_images = config_yaml.get("return_n_generated_images", 1)
image_size = config_yaml.get("image_size", "1024x1024")
n_chat_modes_per_page = config_yaml.get("n_chat_modes_per_page", 5)

# MongoDB — URI and database name from env or config.yml
mongodb_uri = os.environ.get("MONGODB_URI") or config_yaml.get("mongodb_uri") or "mongodb://localhost:27017"
mongodb_database = os.environ.get("MONGODB_DATABASE") or config_yaml.get("mongodb_database") or "chatgpt_telegram_bot"

# Webhook URL for production (Cloud Run/autoscale). Empty = polling mode (dev).
webhook_url = os.environ.get("WEBHOOK_URL") or config_yaml.get("webhook_url", "")

# chat_modes
with open(config_dir / "chat_modes.yml", 'r') as f:
    chat_modes = yaml.safe_load(f)

# models
with open(config_dir / "models.yml", 'r') as f:
    models = yaml.safe_load(f)

# files
help_group_chat_video_path = Path(__file__).parent.parent.resolve() / "static" / "help_group_chat.mp4"
