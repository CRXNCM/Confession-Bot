import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from config import ADMIN_GROUP_ID, CHANNEL_ID
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    CallbackContext
)
from pymongo import MongoClient
from typing import Dict, Tuple, Optional, List

# Import models
from models import User, Confession, Comment, init_db
from confession import handle_confession, button_callback

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize MongoDB
init_db()

# Admin IDs (from .env)
ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip().isdigit()]

async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the rules and ask for acceptance."""
    rules_text = (
        "📜 <b>Rules & Guidelines</b>\n\n"
        "1. Be respectful to others\n"
        "2. No hate speech or harassment\n"
        "3. No personal information\n"
        "4. No spam or advertisements\n"
        "5. Follow Telegram's Terms of Service\n\n"
        "By clicking 'I Accept the Rules', you agree to these terms."
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ I Accept the Rules", callback_data='accept_rules')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store the message ID so we can delete it later
    message = await update.message.reply_html(
        rules_text,
        reply_markup=reply_markup
    )
    
    # Store the message ID in context for later deletion
    context.user_data['rules_message_id'] = message.message_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    # If user already accepted rules, show main menu
    if context.user_data.get('rules_accepted', False):
        await show_main_menu(update, context)
    else:
        await show_rules(update, context)

async def button_click(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'accept_rules':
        # Mark rules as accepted
        context.user_data['rules_accepted'] = True
        
        # Delete the rules message if possible
        if 'rules_message_id' in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=context.user_data['rules_message_id']
                )
            except Exception as e:
                logger.error(f"Error deleting rules message: {e}")
        
        # Send thank you message and show main menu
        await query.message.reply_text(
            "✅ Thank you for accepting the rules!"
        )
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the main menu with reply keyboard."""
    keyboard = [
        ["📝 Confess"],
        ["👤 Bio", "❓ Help"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    # Check if this is a callback query or a message
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "Please choose an option:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Please choose an option:",
            reply_markup=reply_markup
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "🤖 <b>Confession Bot Help</b>\n\n"
        "<b>Available Commands:</b>\n"
        "📝 <b>Confess</b> - Submit an anonymous confession\n"
        "👤 <b>Bio</b> - Set or update your bio\n"
        "❓ <b>Help</b> - Show this help message\n"
        "\nJust type or tap the commands above to get started!"
    )
    
    if update.effective_user.id in ADMIN_IDS:
        help_text += "\n\n⚙️ <b>Admin Commands:</b>\n"
        help_text += "/review - Review pending confessions\n"
    
    await update.message.reply_html(help_text, reply_markup=ReplyKeyboardRemove())

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input from the reply keyboard."""
    text = update.message.text.lower()
    user = update.effective_user
    
    # Check if user is in the middle of making a confession
    if context.user_data.get('awaiting_confession'):
        # Process the confession text
        confession_text = update.message.text
        
        # Save confession to database
        from database import db
        confession = {
            "user_id": user.id,
            "username": user.username or "Anonymous",
            "text": confession_text,  # Changed from 'confession' to 'text' to match schema
            "status": "pending",
            "created_at": update.message.date,
            "updated_at": update.message.date
        }
        
        # Use the existing database instance (synchronous operation)
        collection = db.get_collection('confessions')
        result = collection.insert_one(confession)
        confession_id = str(result.inserted_id)

        # Create approval buttons for admin
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send to admin group for approval
        from telegram.helpers import escape_markdown
        
        # Escape special characters in the confession text
        escaped_confession = escape_markdown(confession_text, version=2)
        
        # Get user mention or 'Anonymous'
        user_mention = f"@{user.username}" if user.username else 'Anonymous'
        
        admin_message = (
            f"📨 *New Confession* \(ID: `{confession_id}`\)\n\n"
            f"👤 *User:* {escape_markdown(user_mention, version=2)}\n"
            f"🆔 *User ID:* `{user.id}`\n\n"
            f"💬 *Confession:*\n{escaped_confession}"
        )

        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_message,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )

        # Reset the state
        context.user_data['awaiting_confession'] = False
        
        # Confirm to user
        await update.message.reply_text(
            "✅ Your confession has been received and is pending approval by admins. "
            "It will be posted to the channel soon if approved.",
            reply_markup=ReplyKeyboardMarkup(
                [['📝 Confess', '👤 Bio'], ['❓ Help']],
                resize_keyboard=True
            )
        )
        return
    
    # Handle main menu buttons
    if '📝 confess' in text or 'confess' in text:
        # Set state to await confession
        context.user_data['awaiting_confession'] = True
        await update.message.reply_text(
            "✍️ Please type your confession. It will be reviewed by admins before posting.",
            reply_markup=ReplyKeyboardMarkup(
                [['❌ Cancel']],
                resize_keyboard=True
            )
        )
        return
            
    elif '👤 bio' in text or 'bio' in text:
        # Check if user already has a bio
        user_data = User.get_user(user.id)
        if user_data and 'bio' in user_data:
            await update.message.reply_text(
                f"📝 <b>Your current bio:</b>\n{user_data['bio']}\n\n"
                "Please send your new bio (max 500 characters):",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardMarkup([['❌ Cancel']], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "👋 Welcome! Please write a short bio (max 500 characters) "
                "that will be shown with your comments:",
                reply_markup=ReplyKeyboardMarkup([['❌ Cancel']], resize_keyboard=True)
            )
        context.user_data['awaiting_bio'] = True
        
    elif '❓ help' in text or 'help' in text:
        await help_command(update, context)
        
    elif '❌ cancel' in text or 'cancel' in text:
        # Clear any pending states
        context.user_data.pop('awaiting_confession', None)
        context.user_data.pop('awaiting_bio', None)
        await show_main_menu(update, context)
        return
        
    elif context.user_data.get('awaiting_bio'):
        # Handle bio submission
        if len(text) > 500:
            await update.message.reply_text("❌ Your bio is too long. Please keep it under 500 characters.")
            return
            
        # Save or update user bio
        user_data = {
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'bio': update.message.text
        }
        
        if User.get_user(user.id):
            User.update_user_bio(user.id, update.message.text)
        else:
            User.create_user(user_data)
            
        # Reset state
        context.user_data.pop('awaiting_bio', None)
        
        # Send confirmation
        await update.message.reply_text(
            "✅ Your bio has been updated!\n\n"
            f"<b>Your new bio:</b>\n{update.message.text}",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup([['📝 Confess', '❓ Help']], resize_keyboard=True)
        )
        
    else:
        await update.message.reply_text(
            "I didn't understand that command. Please use the buttons below or type /help for assistance.",
            reply_markup=ReplyKeyboardMarkup(
                [['📝 Confess', '👤 Bio'], ['❓ Help']],
                resize_keyboard=True
            )
        )

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("confess", handle_confession))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add callback query handler for button clicks
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Add message handler for text messages (for the reply keyboard)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_input
    ))

    # Log any errors
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    if update and hasattr(update, 'effective_message') and update.effective_message:
        await update.effective_message.reply_text(
            'An error occurred while processing your request. Please try again later.'
        )

if __name__ == "__main__":
    main()
