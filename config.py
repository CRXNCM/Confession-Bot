import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip().isdigit()]

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Bot settings
MAX_BIO_LENGTH = 500
MAX_CONFESSION_LENGTH = 2000
MAX_COMMENT_LENGTH = 1000

# Channel/Group IDs (if needed)
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Add this to .env when you have a channel
ADMIN_GROUP_ID = os.getenv('ADMIN_GROUP_ID')  # Add this to .env for admin group

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
