# config.py
import os
import sys
from dotenv import load_dotenv

# For local development, load from .env file
if os.path.exists('.env'):
    load_dotenv()

# Auto-detect environment based on Render-specific indicators
def detect_environment():
    """Automatically detect if running on Render or locally."""
    # Render sets these environment variables automatically
    if os.getenv('RENDER'):
        return 'render'
    if os.getenv('RENDER_SERVICE_NAME'):
        return 'render'
    if os.path.exists('/opt/render'):
        return 'render'
    # Check for PORT environment variable (common in cloud deployments)
    if os.getenv('PORT') and not os.path.exists('.env'):
        return 'render'
    return 'local'

# Determine run mode (auto-detect or use manual override)
manual_mode = os.getenv('RUN_MODE')
auto_detected = detect_environment()
RUN_MODE = (manual_mode or auto_detected).lower()

# Print environment info for debugging
if manual_mode:
    print(f"⚙️  Environment: {RUN_MODE.upper()} (manually set)")
else:
    print(f"⚙️  Environment: {RUN_MODE.upper()} (auto-detected)")
print(f"📁 Current directory: {os.getcwd()}")
print(f"📄 .env exists: {os.path.exists('.env')}")
print(f"🔍 Render detected: {os.path.exists('/opt/render') or bool(os.getenv('RENDER'))}")

# Select token based on run mode
token_var = 'RENDER_BOT_TOKEN' if RUN_MODE == 'render' else 'LOCAL_BOT_TOKEN'
BOT_TOKEN = os.getenv(token_var)

# Check for required variables
if not BOT_TOKEN:
    error_msg = f"❌ {token_var} не знайдено у змінних середовища. "
    error_msg += f"Поточний каталог: {os.getcwd()}"
    print("\n=== Доступні змінні середовища ===")
    for k, v in os.environ.items():
        if any(x in k.lower() for x in ['token', 'api', 'mode']):
            print(f"{k}: {'*' * 8 + v[-4:] if 'token' in k.lower() else v}")
    print("===============================\n")
    raise ValueError(error_msg)

# Log which bot is being used (only show first and last 4 chars for security)
token_display = f"{BOT_TOKEN[:4]}...{BOT_TOKEN[-4:]}" if BOT_TOKEN else "NOT FOUND"
print(f"🤖 Використовується бот: {token_display}")

# Other required environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Database configuration
def get_db_path():
    """Get the appropriate database path based on the environment."""
    # On Render, use the /tmp directory which is writable
    if RUN_MODE == "render":
        db_dir = '/tmp'
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, 'channels.db')
    # For local development, use the current directory
    return 'channels.db'

DB_PATH = get_db_path()

# Webhook configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено у змінних середовища.")

# Log the configuration
print(f"🚀 Конфігурація завантажена. Режим: {RUN_MODE.upper()}")
print(f"📦 База даних: {os.path.abspath(DB_PATH)}")
