import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN or BOT_TOKEN environment variable is not set")

ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip().isdigit()]
if not ADMIN_IDS:
    print("Warning: No ADMIN_IDS set. Admin features will not work.")

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI')
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

DATABASE_NAME = 'confession_bot'

# Bot settings
MAX_BIO_LENGTH = 500
MAX_CONFESSION_LENGTH = 2000
MAX_COMMENT_LENGTH = 1000

# Channel/Group IDs
try:
    CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))
    ADMIN_GROUP_ID = int(os.getenv('ADMIN_GROUP_ID', '0'))
    if not CHANNEL_ID or not ADMIN_GROUP_ID:
        print("Warning: CHANNEL_ID or ADMIN_GROUP_ID is not properly set")
except (ValueError, TypeError) as e:
    print(f"Error parsing CHANNEL_ID or ADMIN_GROUP_ID: {e}")
    CHANNEL_ID = 0
    ADMIN_GROUP_ID = 0

# Messages
MESSAGES = {
    'welcome': (
        "👋 Welcome to Anonymous Confessions Bot!\n\n"
        "📝 Use /confess to submit an anonymous confession\n"
        "👤 Use /bio to set or update your bio\n"
    ),
    'help': (
        "🤖 <b>Confession Bot Help</b>\n\n"
        "<b>Available Commands:</b>\n"
        "/start - Show welcome message\n"
        "/help - Show this help message\n"
        "/bio - Set or update your bio\n"
        "/confess - Submit an anonymous confession\n"
    )
}
