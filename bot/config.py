import yaml
import os
from pathlib import Path

config_dir = Path(__file__).parent.parent.resolve() / "config"

# Try to load yaml config as optional fallback (values in env vars take priority)
config_yaml = {}
config_yml_path = config_dir / "config.yml"
if config_yml_path.exists():
    with open(config_yml_path, 'r') as f:
        config_yaml = yaml.safe_load(f) or {}

# config parameters — env vars take priority over config.yml
telegram_token = os.environ.get("TELEGRAM_TOKEN") or config_yaml.get("telegram_token", "")
openai_api_key = os.environ.get("OPENAI_API_KEY") or config_yaml.get("openai_api_key", "")
openai_api_base = os.environ.get("OPENAI_API_BASE") or config_yaml.get("openai_api_base") or None
openrouter_api_key = os.environ.get("OPENROUTER_API_KEY") or config_yaml.get("openrouter_api_key") or None
openrouter_api_base = os.environ.get("OPENROUTER_API_BASE") or config_yaml.get("openrouter_api_base", "https://openrouter.ai/api/v1")

# allowed_telegram_usernames: comma-separated in env, or list in config.yml
_allowed_env = os.environ.get("ALLOWED_TELEGRAM_USERNAMES", "")
if _allowed_env.strip():
    allowed_telegram_usernames = [u.strip() for u in _allowed_env.split(",") if u.strip()]
else:
    allowed_telegram_usernames = config_yaml.get("allowed_telegram_usernames", [])

new_dialog_timeout = int(os.environ.get("NEW_DIALOG_TIMEOUT", config_yaml.get("new_dialog_timeout", 600)))
enable_message_streaming = os.environ.get("ENABLE_MESSAGE_STREAMING", str(config_yaml.get("enable_message_streaming", True))).lower() not in ("false", "0", "no")
n_chat_modes_per_page = int(os.environ.get("N_CHAT_MODES_PER_PAGE", config_yaml.get("n_chat_modes_per_page", 5)))

# MongoDB — URI and database name from env or config.yml
mongodb_uri = os.environ.get("MONGODB_URI") or config_yaml.get("mongodb_uri") or "mongodb://localhost:27017"
mongodb_database = os.environ.get("MONGODB_DATABASE") or config_yaml.get("mongodb_database") or "chatgpt_telegram_bot"

# Webhook URL for production deployment. Empty = polling mode (dev).
webhook_url = os.environ.get("WEBHOOK_URL") or config_yaml.get("webhook_url", "")

# chat_modes
with open(config_dir / "chat_modes.yml", 'r') as f:
    chat_modes = yaml.safe_load(f)

# models
with open(config_dir / "models.yml", 'r') as f:
    models = yaml.safe_load(f)

# files
help_group_chat_video_path = Path(__file__).parent.parent.resolve() / "static" / "help_group_chat.mp4"
