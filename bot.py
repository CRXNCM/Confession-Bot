import asyncio
import logging
import logging.handlers
import signal
import os
import sys
from pathlib import Path
from typing import Optional

import aiohttp.web
from aiohttp import web
from telegram import Update, BotCommand, BotCommandScopeAllPrivateChats
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    CallbackContext,
)
from telegram.error import TelegramError

from config import BOT_TOKEN, ADMIN_GROUP_ID, CHANNEL_ID
from database import db
from models import Comment, User
from profile_handlers import handle_profile_callback

# Ensure logs directory exists
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True, parents=True)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            str(log_dir / 'bot.log'),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=5
        )
    ]
)
logger = logging.getLogger(__name__)

# Mask token for logging
def get_masked_token(token: str) -> str:
    return f"{token[:5]}...{token[-3:]}" if token else "[no token]"

# Webhook route handlers
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="Bot running")

async def webhook_handler(request: web.Request) -> web.Response:
    if request.method != 'POST':
        logger.warning(f"Received non-POST request: {request.method}")
        return web.Response(status=405, text="Method Not Allowed")

    # Verify token in URL path
    token = request.match_info.get('token')
    if token != BOT_TOKEN:
        masked_token = get_masked_token(token)
        logger.warning(f"Invalid token received: {masked_token}")
        return web.Response(status=403, text="Invalid token")

    try:
        json_data = await request.json()
        logger.debug(f"Received update: {json_data}")
        
        # Process the update
        update = Update.de_json(json_data, request.app['application'].bot)
        await request.app['application'].update_queue.put(update)
        
        return web.Response(text="OK")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return web.Response(status=400, text="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return web.Response(status=500, text="Internal Server Error")

# Command handlers (moved from original file)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the bot! Use /help for commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
    """
    await update.message.reply_text(help_text)

# Application setup
def create_application() -> Application:
    """Create and configure the Application instance."""
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    return application

async def setup_application_commands(application: Application) -> None:
    """Set up bot commands."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help information"),
    ]
    await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())

async def on_startup(application: Application) -> None:
    """Initialize bot on startup."""
    await application.initialize()
    await application.start()
    logger.info("Bot initialized and started")

async def on_shutdown(application: Application) -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down...")
    try:
        await application.bot.delete_webhook()
        logger.info("Webhook removed")
    except Exception as e:
        logger.error(f"Error removing webhook: {e}")
    
    await application.stop()
    await application.shutdown()
    logger.info("Shutdown complete")

# Error handler
async def error_handler(update: object, context: CallbackContext) -> None:
    """Log errors caused by updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and hasattr(update, 'effective_message'):
        try:
            await update.effective_message.reply_text(
                "An error occurred while processing your request. Please try again later."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

async def setup_webhook(application: Application) -> None:
    """Set up the webhook and return the webhook URL."""
    webhook_url = os.getenv('WEBHOOK_URL')
    if not webhook_url:
        render_service = os.getenv('RENDER_SERVICE_URL', '').rstrip('/')
        if not render_service:
            raise ValueError("Neither WEBHOOK_URL nor RENDER_SERVICE_URL is set in environment variables")
        webhook_url = f"{render_service}/webhook/{BOT_TOKEN}"
    
    try:
        await application.bot.delete_webhook()
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set successfully: {webhook_url}")
        bot_info = await application.bot.get_me()
        logger.info(f"Bot info: {bot_info}")
        return webhook_url
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise

async def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    # Initialize application
    application = create_application()
    
    # Create aiohttp web application
    app = web.Application()
    app['bot'] = application.bot
    app['application'] = application
    
    # Add routes
    app.router.add_get("/", health_check)
    app.router.add_post("/webhook/{token}", webhook_handler)
    
    # Set up startup and shutdown handlers
    app.on_startup.append(lambda app: setup_webhook(application))
    app.on_shutdown.append(lambda app: on_shutdown(application))
    
    return app

def main() -> None:
    """Run the bot."""
    logger.info("Starting bot initialization...")
    
    try:
        # Create and run the application
        app = asyncio.run(create_app())
        
        # Get port from environment variable or use default
        port = int(os.getenv('PORT', '5000'))
        logger.info(f"Starting web server on port {port}")
        
        # Start the web server
        web.run_app(
            app,
            host='0.0.0.0',
            port=port,
            handle_signals=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        raise

async def shutdown(app: web.Application, application: Application) -> None:
    """Shutdown the server."""
    logger.info("Shutdown signal received")
    await on_shutdown(application)
    await app.shutdown()
    await app.cleanup()
    logger.info("Server stopped")

if __name__ == "__main__":
    logger.info(f"Starting bot with token: {get_masked_token(BOT_TOKEN)}")
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

# (Profile-related history functions removed)

class CustomFormatter(logging.Formatter):
    """Custom formatter with colors and cleaner output"""
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"
    
    COLORS = {
        logging.DEBUG: blue,
        logging.INFO: grey,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red
    }
    
    def format(self, record):
        # Shorten logger name to just the last part after the last dot
        if '.' in record.name:
            record.name = record.name.split('.')[-1]
        
        # Apply color based on log level
        color = self.COLORS.get(record.levelno, self.grey)
        record.levelname = f"{color}{record.levelname}{self.reset}"
        record.name = f"{self.blue}{record.name}{self.reset}"
        
        return super().format(record)

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console handler with custom formatter
console = logging.StreamHandler(sys.stdout)
console_formatter = logging.Formatter(
    '%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
console.setFormatter(CustomFormatter('%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
                                  datefmt='%H:%M:%S'))

# File handler with rotation
file_handler = RotatingFileHandler(
    log_dir / 'bot.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# Add handlers
logger.addHandler(console)
logger.addHandler(file_handler)

# Suppress noisy loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Get logger for this module
logger = logging.getLogger(__name__)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    CallbackContext,
    ConversationHandler
)
from pymongo import MongoClient
from typing import Dict, Tuple, Optional, List

# Import models and handlers
from models import User, Confession, Comment
from confession import (
    handle_confession, 
    button_callback, 
    receive_confession_text, 
    save_confession
)

# Available categories
CATEGORIES = [
    "💖 Love & Relationships",
    "🎓 School & Education",
    "👥 Friends & Family",
    "😕 Confusion & Thoughts",
    "😔 Regrets",
    "🎭 Secrets",
    "🎉 Celebrations",
    "❓ Other"
]

# Conversation states
TEXT, CATEGORY = range(2)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)

# Admin IDs (from .env)
ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip().isdigit()]

# Removed chat functionality
# In-memory structures for chat/request flows. These were previously removed
# accidentally; restore as empty dicts so chat-related handlers don't crash.
CHAT_SESSIONS: Dict[str, dict] = {}
ACTIVE_CHATS: Dict[int, int] = {}
CHAT_PEERS: Dict[int, dict] = {}

def _summarize_update(update: Update) -> str:
    try:
        if update.message:
            u = update.effective_user
            chat = update.effective_chat
            txt = (update.message.text or '').replace('\n', ' ')
            return f"msg from {u.id}(@{u.username}) in {chat.type}:{chat.id} -> {txt[:120]}"
        if update.callback_query:
            u = update.effective_user
            chat = update.effective_chat
            data = update.callback_query.data
            return f"cb from {u.id}(@{u.username}) in {chat.type}:{chat.id} -> {data}"
        if update.edited_message:
            u = update.effective_user
            chat = update.effective_chat
            return f"edited msg from {u.id}(@{u.username}) in {chat.type}:{chat.id}"
    except Exception as e:
        return f"update summary error: {e}"
    return "unknown update"


async def log_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Incoming update: { _summarize_update(update) }")


async def log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        logger.info(f"Incoming callback: { _summarize_update(update) }")


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
    t0 = time.perf_counter()
    logger.info(f"/start invoked: { _summarize_update(update) }")
    
    # Check if this is a callback query
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # Handle request chat callback
        if query.data.startswith('requestc_'):
            from bson import ObjectId
            from models import Comment
            _, cid = query.data.split('_', 1)
            # Rest of the request chat handling code...
            return
    
    # Handle regular /start command with message
    if not update.message:
        return
        
    user = update.effective_user
    
    # Check for deep-link parameters e.g. /start comment_<confession_id>
    if context.args:
        arg = context.args[0]
        if arg.startswith('comment_'):
            confession_id = arg.split('_', 1)[1]
            # Store the context for this session
            context.user_data['comment_confession_id'] = confession_id
            # Show main menu first if user is not new
            from models import User
            db_user = User.get_user(user.id)
            if db_user:
                await show_main_menu(update, context)
            # Offer options: display comments or add a new one
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🧾 Display comments", callback_data=f"showcomments_{confession_id}")],
                [InlineKeyboardButton("➕ Add comment", callback_data=f"addcomment_{confession_id}")]
            ])
            await update.message.reply_text(
                "What would you like to do for this post?",
                reply_markup=keyboard
            )
            logger.info(f"/start deep link (comment) handled in { (time.perf_counter()-t0)*1000:.1f} ms")
            return
            
    # Check if user exists in database
    from models import User
    db_user = User.get_user(user.id)
    
    if db_user:
        # Existing user - show welcome back message and main menu
        welcome_text = (
            f"👋 Welcome back, {user.first_name}!\n\n"
            "What would you like to do today?"
        )
        await show_main_menu(update, context)
        await update.message.reply_text(welcome_text)
        return
    else:
        # New user - show rules
        await show_rules(update, context)
        return


    # Handle chat request responses (approve/reject)
    if update.callback_query and (update.callback_query.data.startswith('approvechat_') or update.callback_query.data.startswith('rejectchat_')):
        query = update.callback_query
        await query.answer()
        
        action, session_id = query.data.split('_', 1)
        sess = CHAT_SESSIONS.get(session_id)
        
        if not sess or sess.get('status') != 'pending':
            await query.message.reply_text("❌ This chat request is no longer available.")
            return
            
        owner_id = sess['owner_id']
        requester_id = sess['requester_id']
        
        if action == 'rejectchat':
            sess['status'] = 'rejected'
            try:
                await context.bot.send_message(
                    chat_id=requester_id, 
                    text="❌ Your chat request was rejected."
                )
            except Exception as e:
                logger.error(f"Error notifying requester of rejection: {e}")
                
            await query.message.edit_text("You rejected the chat request.")
            return
            
        elif action == 'approvechat':
            sess['status'] = 'active'
            
            # Notify both parties that the chat is active
            try:
                # Notify the requester
                await context.bot.send_message(
                    chat_id=requester_id,
                    text=(
                        "✅ Your chat request was approved!\n\n"
                        "You can now chat anonymously. Type /endchat to end the conversation."
                    )
                )
                
                # Notify the owner
                await query.message.edit_text(
                    "✅ Chat started! You can now chat anonymously.\n"
                    "Type /endchat to end the conversation."
                )
                
                # Store the active chat session
                ACTIVE_CHATS[requester_id] = owner_id
                ACTIVE_CHATS[owner_id] = requester_id
                
            except Exception as e:
                logger.error(f"Error starting chat session: {e}")
                await query.message.reply_text("❌ Failed to start chat. Please try again.")
                
            return

    # Handle leave chat request
    if update.callback_query and update.callback_query.data.startswith('leavechat_'):
        query = update.callback_query
        await query.answer()
        
        _, session_id = query.data.split('_', 1)
        sess = CHAT_SESSIONS.get(session_id)
        
        if not sess:
            await query.message.reply_text("❌ Chat session not found.")
            return
            
        if sess.get('status') != 'active':
            await query.message.reply_text("ℹ️ This chat is already closed.")
            return
            
        user_id = update.effective_user.id
        owner_id = sess['owner_id']
        requester_id = sess['requester_id']
        
        # Update session status
        sess['status'] = 'ended'
        
        # Remove from active chats
        if user_id in ACTIVE_CHATS:
            del ACTIVE_CHATS[user_id]
        
        # Notify the other participant if they're still in the chat
        try:
            peer_id = requester_id if user_id == owner_id else owner_id
            
            # Check if peer is still in the chat
            if peer_id in ACTIVE_CHATS and ACTIVE_CHATS[peer_id] == user_id:
                await context.bot.send_message(
                    chat_id=peer_id,
                    text="ℹ️ The other person has left the chat. The chat is now closed."
                )
                # Remove peer from active chats
                del ACTIVE_CHATS[peer_id]
                
        except Exception as e:
            logger.error(f"Error notifying peer about chat end: {e}")
        
        # Update the message to show the chat has ended
        await query.message.edit_text(
            "🚪 You have left the chat.\n\n"
            "Type /start to return to the main menu."
        )
        return

    # Handle reply entry flow
    if context.user_data.get('awaiting_reply'):
        raw_reply_text = update.message.text
        try:
            from models import Comment
            from bson import ObjectId
            parent_cid_str = context.user_data.get('parent_comment_id')
            parent_cid = ObjectId(parent_cid_str)
            # To associate reply to the same confession as parent, fetch parent
            parent = Comment.get_comment(parent_cid)
            if not parent:
                await update.message.reply_text("❌ Original comment not found.")
                # clear reply state
                context.user_data.pop('awaiting_reply', None)
                context.user_data.pop('parent_comment_id', None)
                return
            reply_data = {
                "confession_id": parent.get('confession_id'),
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "text": raw_reply_text,
            }
            # Add the reply to the database
            reply = Comment.add_reply(parent_cid, reply_data)
            
            # Get the confession to update the comment count
            from database import db
            confessions_col = db.get_collection('confessions')
            confessions_col.update_one(
                {"_id": ObjectId(parent.get('confession_id'))},
                {"$inc": {"comment_count": 1}},
                upsert=True
            )
            
            # Refresh channel button count for this confession
            try:
                await refresh_channel_comment_count(parent.get('confession_id'), context)
            except Exception as e:
                logger.warning(f"Failed to refresh channel comment count (reply): {e}")
                
            # Send success message
            await update.message.reply_text(
                "✅ Your reply has been posted!",
                reply_markup=ReplyKeyboardRemove()
            )
            
        except Exception as e:
            logger.error(f"Error saving reply: {e}")
            await update.message.reply_text("❌ Failed to save your reply. Please try again later.")
            return
        finally:
            # Always clean up the reply state
            context.user_data.pop('awaiting_reply', None)
            context.user_data.pop('parent_comment_id', None)

        # Handle cancel button
        if update.message.text in ['❌ cancel', 'cancel']:
            if 'awaiting_confession' in context.user_data:
                # Clear all confession-related data
                for key in ['awaiting_confession', 'confession_stage', 'confession_text', 'confession_category']:
                    if key in context.user_data:
                        del context.user_data[key]
                
                await update.message.reply_text(
                    "❌ Confession cancelled. What would you like to do next?",
                    reply_markup=ReplyKeyboardMarkup(
                        [['📝 Confess', '👤 Bio'], ['❓ Help']],
                        resize_keyboard=True
                    )
                )
                return

        # If user already accepted rules, show main menu; otherwise show rules
        if context.user_data.get('rules_accepted', False):
            await show_main_menu(update, context)
        else:
            await show_rules(update, context)
        logger.info(f"/start completed in { (time.perf_counter()-t0)*1000:.1f} ms")
        await show_rules(update, context)
    logger.info(f"/start completed in { (time.perf_counter()-t0)*1000:.1f} ms")

async def button_click(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    
    # Log the callback data first
    try:
        logger.info(f"Callback received: {query.data}")
    except Exception as e:
        logger.error(f"Error logging callback data: {e}")
    
    # Answer the callback query with error handling
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Could not answer callback query: {e}")
        # Continue processing even if answering fails
    
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
        return

    # Handle confession preview callbacks
    if query.data == 'preview_submit':
        # Get confession data from user_data
        confession_text = context.user_data.get('confession_text')
        selected_categories = context.user_data.get('selected_categories', ['Uncategorized'])
        
        # Get user info
        user = query.from_user
        
        # Save confession to database
        from database import db
        from models import Confession
        from telegram.helpers import escape_markdown
        
        # Get category hashtags
        category_hashtags = Confession.get_category_hashtags(selected_categories)
        
        # Save to database
        confession = {
            "user_id": user.id,
            "username": user.username or "Anonymous",
            "text": confession_text,
            "categories": selected_categories,
            "hashtags": category_hashtags,
            "status": "pending",
            "created_at": query.message.date,
            "updated_at": query.message.date
        }
        
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
        
        # Send to admin group
        user_mention = f"@{user.username}" if user.username else 'Anonymous'
        escaped_categories = [escape_markdown(cat, version=2) for cat in selected_categories]
        categories_text = ', '.join([f'`{cat}`' for cat in escaped_categories])
        
        # Escape all special characters in the message
        escaped_id = escape_markdown(str(confession_id), version=2)
        escaped_mention = escape_markdown(user_mention, version=2)
        escaped_confession = escape_markdown(confession_text, version=2)
        
        # Escape hashtags and other special characters
        escaped_hashtags = escape_markdown(category_hashtags, version=2)
        # Replace # with \# for MarkdownV2
        escaped_hashtags = escaped_hashtags.replace('#', r'\#')
        
        # Build the message parts with proper escaping
        message_parts = [
            "📨 *New Confession* \\(ID: `" + escaped_id + "`\\)",
            "🏷️ *Categories:* " + categories_text,
            "👤 *User:* " + escaped_mention,
            "🆔 *User ID:* `" + str(user.id) + "`",
            "",  # Empty line for spacing
            "💬 *Confession:*",
            escaped_confession,
            "",  # Empty line for spacing
            "🔖 *Tags:* `" + escaped_hashtags + "`"
        ]
        
        # Join with newlines
        admin_message = "\n".join(message_parts)
        
        try:
            from config import ADMIN_GROUP_ID
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=admin_message,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            
            # Show success message to user
            await query.answer("Your confession has been submitted for review!")
            await query.edit_message_text(
                "✅ Your confession has been submitted for admin review.\n\n"
                "We'll notify you once it's approved and posted.",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Error sending confession to admin: {e}")
            await query.answer("❌ Failed to submit your confession. Please try again.", show_alert=True)
            return
        
        # Clear the state
        for key in ['awaiting_confession', 'confession_stage', 'confession_text', 'selected_categories']:
            context.user_data.pop(key, None)
            
        return ConversationHandler.END
        
    elif query.data == 'preview_edit':
        # Go back to text editing
        context.user_data['confession_stage'] = 'text'
        await query.edit_message_text(
            "✏️ Please send me your confession text again. You can edit it now.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="preview_cancel")]
            ])
        )
        return TEXT  # Return to text input state
        
    elif query.data == 'preview_cancel':
        # Clear everything
        for key in ['awaiting_confession', 'confession_stage', 'confession_text', 'selected_categories']:
            context.user_data.pop(key, None)
        await query.edit_message_text(
            "❌ Confession cancelled. Your message has been discarded.",
            reply_markup=None
        )
        return ConversationHandler.END

    # Handle comment-related callbacks
    if query.data and query.data.startswith('showcomments_'):
        confession_id = query.data.split('_', 1)[1]
        # Fetch and display comments for this confession
        try:
            from models import Comment
            comments = Comment.get_comments(confession_id)
            if not comments:
                await query.message.reply_text("🕊️ No comments yet for this post.")
                return
            # Send each comment as its own message with action buttons (limit to 10)
            import html as _html
            for c in comments[:10]:
                roll_no = c.get('roll_no') or '-'
                text = c.get('text', '')
                likes = c.get('likes', 0)
                dislikes = c.get('dislikes', 0)
                comment_id = str(c.get('_id'))
                # Escape text for HTML
                text_html = _html.escape(text)
                # Calculate auto ratio if there are votes
                total_votes = likes + dislikes
                if total_votes > 0:
                    like_percent = int((likes / total_votes) * 100)
                    dislike_percent = 100 - like_percent
                    auto_section = (
                        f"\n\n🔄 <b>Auto ({total_votes} votes)</b>\n"
                        f"👍 {like_percent}% • 👎 {dislike_percent}%"
                    )
                else:
                    auto_section = "\n\n🔄 <b>Auto</b> (No votes yet)"
                
                body = (
                    f"🗨️ Comment #{roll_no}\n\n"
                    f"{text_html}\n\n"
                    f"<b>Votes:</b> 👍 {likes}  •  👎 {dislikes}"
                    f"{auto_section}"
                )
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{comment_id}"),
                        InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{comment_id}")
                    ],
                    [
                        InlineKeyboardButton("🔄 Auto", callback_data=f"auto_{comment_id}")
                    ],
                    [
                        InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{comment_id}")
                    ]
                ])
                await query.message.reply_text(body, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error fetching comments: {e}")
            await query.message.reply_text("❌ Failed to load comments. Please try again later.")
        return

    if query.data and query.data.startswith('addcomment_'):
        confession_id = query.data.split('_', 1)[1]
        context.user_data['awaiting_comment'] = True
        context.user_data['comment_confession_id'] = confession_id
        await query.message.reply_text(
            "💬 Please type your comment. It will be posted under the confession after review.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
        )
        return


    # Handle reactions: like/dislike
    if query.data and (query.data.startswith('like_') or query.data.startswith('dislike_')):
        from bson import ObjectId
        from models import Comment
        action, cid = query.data.split('_', 1)
        try:
            obj_id = ObjectId(cid)
        except Exception:
            await query.message.reply_text("❌ Invalid comment reference.")
            return
        try:
            if action == 'like':
                if not Comment.like_comment(obj_id):
                    await query.answer("❌ Failed to like the comment.", show_alert=True)
                    return
            else:
                if not Comment.dislike_comment(obj_id):
                    await query.answer("❌ Failed to dislike the comment.", show_alert=True)
                    return
            # Fetch updated comment and update the message text
            c = Comment.get_comment(obj_id)
            if not c:
                await query.message.reply_text("❌ Comment not found.")
                return
            roll_no = c.get('roll_no') or '-'
            text = c.get('text', '')
            likes = c.get('likes', 0)
            dislikes = c.get('dislikes', 0)
            import html as _html
            text_html = _html.escape(text)
            body = (
                f"🗨️ Comment #{roll_no}\n\n"
                f"{text_html}\n\n"
                f"👍 {likes}    👎 {dislikes}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👍 Like", callback_data=f"like_{cid}"),
                 InlineKeyboardButton("👎 Dislike", callback_data=f"dislike_{cid}")],
                [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{cid}")]
            ])
            try:
                await query.edit_message_text(body, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"edit_message_text failed, sending new message instead: {e}")
        except Exception as e:
            logger.error(f"Error handling like/dislike action: {e}", exc_info=True)
            try:
                await query.answer("❌ An error occurred while processing your vote.", show_alert=True)
            except Exception:
                pass

    # Handle admin actions
    if query.data and query.data.startswith('admin_'):
        try:
            admin_ids = [int(id_str) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip().isdigit()]
            if not admin_ids:
                logger.error("No admin IDs configured in environment variables")
                await query.answer("❌ Server configuration error. Please contact the administrator.", show_alert=True)
                return
                
            if query.from_user.id not in admin_ids:
                await query.answer("❌ You are not authorized to perform this action.", show_alert=True)
                return
                
            action_parts = query.data.split('_')
            action = action_parts[1]
            
            if action == 'del' and len(action_parts) == 4:  # admin_del_comment_<comment_id>
                comment_id = action_parts[3]
                try:
                    # Delete the comment
                    result = await db.get_collection('comments').delete_one({"_id": ObjectId(comment_id)})
                    if result.deleted_count > 0:
                        # Update the report status
                        await db.get_collection('reports').update_many(
                            {"comment_id": ObjectId(comment_id)},
                            {"$set": {"status": "resolved", "action": "deleted", "resolved_at": datetime.utcnow(), "resolved_by": query.from_user.id}}
                        )

                        # Notify in the admin group
                        await query.message.edit_text(
                            f"✅ Comment {comment_id} has been deleted by @{query.from_user.username}\n\n" + 
                            query.message.text,
                            parse_mode='Markdown',
                            reply_markup=None
                        )
                        
                        # Try to delete the original message from the channel
                        try:
                            comment = await db.get_collection('comments').find_one({"_id": ObjectId(comment_id)})
                            if comment and 'message_id' in comment:
                                try:
                                    await context.bot.delete_message(
                                        chat_id=CHANNEL_ID,
                                        message_id=comment['message_id']
                                    )
                                    await query.answer("Comment deleted successfully.", show_alert=True)
                                except Exception as e:
                                    logger.error(f"Failed to delete message from channel: {e}")
                                    await query.answer("Comment marked as deleted but could not remove from channel.", show_alert=True)
                        except Exception as e:
                            logger.error(f"Error finding comment: {e}")
                            await query.answer("Comment marked as deleted but could not verify channel message.", show_alert=True)
                    else:
                        await query.answer("Comment not found or already deleted.", show_alert=True)
                        
                except Exception as e:
                    logger.error(f"Error in delete action: {e}")
                    await query.answer("An error occurred while processing the delete request.", show_alert=True)

            elif action == 'warn' and len(action_parts) == 5:  # admin_warn_user_<user_id>_<comment_id>
                user_id = int(action_parts[3])
                comment_id = action_parts[4]
                
                try:
                    # Update the report status
                    result = await db.get_collection('reports').update_many(
                        {"comment_id": ObjectId(comment_id)},
                        {"$set": {"status": "resolved", "action": "user_warned", "resolved_at": datetime.utcnow(), "resolved_by": query.from_user.id}}
                    )
                    
                    if result.matched_count == 0:
                        logger.warning(f"No reports found for comment {comment_id}")
                        await query.answer("⚠️ No active reports found for this comment.", show_alert=True)
                        return
                except Exception as e:
                    logger.error(f"Error updating reports for warn action: {e}", exc_info=True)
                    await query.answer("❌ Failed to update report status.", show_alert=True)
                    return

                # Update the admin message
                await query.message.edit_text(
                    f"✅ Report ignored by @{query.from_user.username}\n\n" + 
                    query.message.text,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🗑️ Delete Comment", callback_data=f"admin_del_comment_{comment_id}"),
                            InlineKeyboardButton("⚠️ Warn User", callback_data=f"admin_warn_user_{user_id}_{comment_id}")
                        ]
                    ])
                )
                
            await query.answer()  # Acknowledge the callback
            
        except Exception as e:
            logger.error(f"Error in admin action handler: {e}", exc_info=True)
            try:
                await query.answer("❌ An error occurred while processing your request.", show_alert=True)
            except:
                pass
            
        return  # Important to prevent further processing
    
    # Handle reply start
    if query.data and query.data.startswith('reply_'):
        from bson import ObjectId
        action, cid = query.data.split('_', 1)
        try:
            ObjectId(cid)  # validate only
        except Exception:
            await query.message.reply_text("❌ Invalid comment reference.")
            return
        context.user_data['awaiting_reply'] = True
        context.user_data['parent_comment_id'] = cid
        # Also preserve confession id if present in session
        await query.message.reply_text(
            "↩️ Please type your reply to this comment.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
        )
        return

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the main menu with reply keyboard."""
    keyboard = [
        ["📝 Confess", "👤 Profile"],
        ["❓ Help"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    # Check if this is a callback query or a message
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "🏠 *Main Menu*\n\n"
            "Please choose an option:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏠 *Main Menu*\n\n"
            "Please choose an option:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    logger.info(f"/help invoked: { _summarize_update(update) }")
    help_text = (
        "🤖 <b>Confession Bot Help</b>\n\n"
        "<b>Available Commands:</b>\n"
        "📝 <b>Confess</b> - Submit an anonymous confession\n"
        "❓ <b>Help</b> - Show this help message\n\n"
        "Tap the buttons below to get started!"
    )
    
    if update.effective_user.id in ADMIN_IDS:
        help_text += "\n\n⚙️ <b>Admin Commands:</b>\n"
        help_text += "/review - Review pending confessions\n"
    
    await update.message.reply_html(help_text, reply_markup=ReplyKeyboardRemove())

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input from the reply keyboard."""
    t0 = time.perf_counter()
    logger.info(f"text input: { _summarize_update(update) }")
    text = update.message.text.lower()
    user = update.effective_user
    
    # Handle reply entry flow - this needs to be checked first
    if context.user_data.get('awaiting_reply'):
        parent_cid_str = context.user_data.get('parent_comment_id')
        if not parent_cid_str:
            await update.message.reply_text("❌ Error: No parent comment reference found. Please try again.")
            # Clear any existing reply state
            context.user_data.pop('awaiting_reply', None)
            context.user_data.pop('parent_comment_id', None)
            await show_main_menu(update, context)
            return
            
        # Clean up the state first in case of errors
        context.user_data.pop('awaiting_reply', None)
        context.user_data.pop('parent_comment_id', None)
        
        # Check if the user is trying to cancel
        if text in ['❌ cancel', 'cancel']:
            await update.message.reply_text("❌ Reply cancelled.", reply_markup=ReplyKeyboardRemove())
            await show_main_menu(update, context)
            return
            
        # Validate reply length
        if len(update.message.text) > 500:
            await update.message.reply_text("❌ Reply is too long. Maximum 500 characters allowed.")
            # Reset the reply state
            context.user_data['awaiting_reply'] = True
            context.user_data['parent_comment_id'] = parent_cid_str
            return
            
        try:
            from models import Comment
            from bson import ObjectId
            from database import db
            
            parent_cid = ObjectId(parent_cid_str)
            parent = Comment.get_comment(parent_cid)
            
            if not parent:
                await update.message.reply_text("❌ The original comment was not found.")
                return
                
            reply_data = {
                "confession_id": parent.get('confession_id'),
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "text": update.message.text,
                "created_at": datetime.utcnow()
            }
            
            # Add the reply to the database
            try:
                result = Comment.add_reply(parent_cid, reply_data)
                
                if result.modified_count > 0:
                    # Update the confession's comment count
                    db.get_collection('confessions').update_one(
                        {"_id": parent.get('confession_id')},
                        {"$inc": {"comment_count": 1}}
                    )
                    
                    # Send success message
                    await update.message.reply_text(
                        "✅ Your reply has been posted!",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    
                    # Notify the parent comment's author if it's not the same user
                    if parent.get('user_id') != user.id:
                        try:
                            await context.bot.send_message(
                                chat_id=parent['user_id'],
                                text=f"💬 Someone replied to your comment: \n\n{update.message.text}"
                            )
                        except Exception as e:
                            logger.warning(f"Could not send reply notification to user {parent['user_id']}: {e}")
                    
                    # Show main menu
                    await show_main_menu(update, context)
                else:
                    logger.warning(f"Failed to add reply: {result.raw_result}")
                    await update.message.reply_text("❌ Failed to post your reply. The comment may have been deleted or you may not have permission.")
            except Exception as e:
                logger.error(f"Error in add_reply: {e}")
                await update.message.reply_text("❌ An error occurred while posting your reply. Please try again later.")
                
        except Exception as e:
            logger.error(f"Error saving reply: {e}")
            await update.message.reply_text("❌ An error occurred while saving your reply. Please try again.")
        
        return
    
    # Handle Profile button -> show profile from profile_handlers
    if update.message.text == '👤 Profile' or text == 'profile':
        from profile_handlers import show_profile as show_profile_min
        await show_profile_min(update, context)
        await show_main_menu(update, context)
        return
    
    # Handle Help button
    if update.message.text == '❓ Help' or text == 'help':
        await help_command(update, context)
        return
    # Anonymous relay chat: if user is in an active chat, relay their message
    peer_info = CHAT_PEERS.get(user.id)
    if peer_info:
        peer_id = peer_info['peer_id']
        session_id = peer_info['session_id']
        leave_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚪 Leave Chat", callback_data=f"leavechat_{session_id}")]])
        try:
            await context.bot.send_message(chat_id=peer_id, text=f"Anonymous: {update.message.text}", reply_markup=leave_keyboard)
        except Exception as e:
            logger.warning(f"Failed to relay message: {e}")
            await update.message.reply_text("❌ Failed to deliver your message.")
            return
        # Acknowledge to sender (optional): we can stay silent or show minimal ack
        return
    
    # Handle comment entry flow first
    if context.user_data.get('awaiting_comment'):
        raw_comment_text = update.message.text
        # Optional: enforce max length
        try:
            from config import MAX_COMMENT_LENGTH
            if len(raw_comment_text) > MAX_COMMENT_LENGTH:
                await update.message.reply_text(
                    f"❌ Your comment is too long. Please keep it under {MAX_COMMENT_LENGTH} characters."
                )
                return
        except Exception:
            pass

        confession_id = context.user_data.get('comment_confession_id')
        # Persist the comment
        try:
            from models import Comment
            comment_data = {
                "confession_id": confession_id,
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "text": raw_comment_text,
            }
            Comment.add_comment(comment_data)
            # After adding comment, refresh the channel button count
            try:
                await refresh_channel_comment_count(confession_id, context)
            except Exception as e:
                logger.warning(f"Failed to refresh channel comment count: {e}")
        except Exception as e:
            logger.error(f"Error saving comment: {e}")
            await update.message.reply_text("❌ Failed to save your comment. Please try again later.")
            # Do not clear state to allow retry
            return

        # Clear comment state
        context.user_data.pop('awaiting_comment', None)
        context.user_data.pop('comment_confession_id', None)

        await update.message.reply_text(
            "✅ Your comment has been submitted for review.",
            reply_markup=ReplyKeyboardMarkup(
                [['📝 Confess', '👤 Bio'], ['❓ Help']],
                resize_keyboard=True
            )
        )
        return

    # Check if user is in the middle of making a confession
    if context.user_data.get('awaiting_confession'):
        current_stage = context.user_data.get('confession_stage')
        
        # If we're in the text editing stage (after preview)
        if current_stage == 'text':
            # Save the edited text
            context.user_data['confession_text'] = text
            
            # Show the preview again
            categories = context.user_data.get('selected_categories', ['Uncategorized'])
            preview_text = (
                f"📝 *Preview Your Confession (Edited)*\n\n"
                f"📌 *Categories:* {', '.join(categories)}\n\n"
                f"{text}"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Submit", callback_data="preview_submit")],
                [InlineKeyboardButton("✏️ Edit", callback_data="preview_edit")],
                [InlineKeyboardButton("❌ Cancel", callback_data="preview_cancel")]
            ]
            
            # Edit the original preview message or send a new one
            try:
                await update.message.reply_text(
                    preview_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error showing preview: {e}")
                await update.message.reply_text("❌ An error occurred. Please try again.")
            
            return
            
        # If we're in the category selection stage
        elif current_stage == 'category':
            from models import Confession
            
            # Initialize selected categories if not exists
            if 'selected_categories' not in context.user_data:
                context.user_data['selected_categories'] = []
            
            selected_categories = context.user_data['selected_categories']
            
            # Handle 'Done' button
            if update.message.text.lower() == '✅ done':
                if not selected_categories:
                    await update.message.reply_text(
                        "❌ Please select at least one category before continuing."
                    )
                    return
                    
                context.user_data['confession_stage'] = 'text'
                
                # Format categories for display
                categories_text = "\n".join([f"• {cat}" for cat in selected_categories])
                
                await update.message.reply_text(
                    f"✍️ You've selected these categories:\n{categories_text}\n\n"
                    "Now, please type your confession. It will be reviewed by admins before posting.",
                    reply_markup=ReplyKeyboardMarkup(
                        [['❌ Cancel']],
                        resize_keyboard=True
                    ),
                    parse_mode='Markdown'
                )
                return
                
            # Handle category toggle
            category = update.message.text
            if Confession.is_valid_category(category):
                # Toggle category selection
                if category in selected_categories:
                    selected_categories.remove(category)
                    action = "removed"
                else:
                    selected_categories.append(category)
                    action = "added"
                
                # Update the keyboard to show selected categories
                from models import Confession
                categories = Confession.get_categories()
                keyboard = []
                for i in range(0, len(categories), 2):
                    row = []
                    for j in range(2):
                        if i + j < len(categories):
                            cat = categories[i + j]
                            prefix = "✅ " if cat in selected_categories else ""
                            row.append(f"{prefix}{cat}")
                    if row:
                        keyboard.append(row)
                
                # Add Done button if at least one category is selected
                if selected_categories:
                    keyboard.append(['✅ Done'])
                keyboard.append(['❌ Cancel'])
                
                await update.message.reply_text(
                    f"{action.capitalize()}: *{category}*\n\n"
                    "Select more categories or tap '✅ Done' when finished:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False),
                    parse_mode='Markdown'
                )
                return
            else:
                # Invalid category selected
                await update.message.reply_text(
                    "❌ Please select a valid category from the options below."
                )
                return
                
        # If we're in the text input stage
        elif context.user_data.get('confession_stage') == 'text':
            # Get the categories from context
            selected_categories = context.user_data.get('selected_categories', ['💬 General'])
            confession_text = update.message.text
            
            # Get category hashtags using the model method
            from models import Confession
            category_hashtags = Confession.get_category_hashtags(selected_categories)
            full_confession_text = f"{confession_text}\n\n{category_hashtags}"
            
            # Store confession data for preview
            context.user_data['confession_text'] = confession_text
            context.user_data['confession_hashtags'] = category_hashtags
            
            # Move to preview stage
            context.user_data['confession_stage'] = 'preview'
            
            # Show preview with confirmation buttons
            preview_text = (
                f"📝 *Preview Your Confession*\n\n"
                f"📌 *Categories:* {', '.join(selected_categories)}\n\n"
                f"{text}"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Submit", callback_data="preview_submit")],
                [InlineKeyboardButton("✏️ Edit", callback_data="preview_edit")],
                [InlineKeyboardButton("❌ Cancel", callback_data="preview_cancel")]
            ]
            
            await update.message.reply_text(
                preview_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
            # Return PREVIEW state to handle the callback
            return 'PREVIEW'
            
        else:
            # Invalid category selected
            await update.message.reply_text(
                "❌ Invalid category selected. Please select a valid category from the options."
            )
            return
    
    # Handle main menu buttons
    if '📝 confess' in text or 'confess' in text:
        # Set state to await category selection
        context.user_data['awaiting_confession'] = True
        context.user_data['confession_stage'] = 'category'
        
        # Get categories and create keyboard with checkboxes
        from models import Confession
        categories = Confession.get_categories()
        
        # Create a keyboard with 2 columns
        keyboard = []
        for i in range(0, len(categories), 2):
            row = []
            for j in range(2):
                if i + j < len(categories):
                    cat = categories[i + j]
                    row.append(f"{cat}")
            if row:
                keyboard.append(row)
        
        # Add Cancel button
        keyboard.append(['❌ Cancel'])
        
        await update.message.reply_text(
            "📚 *Select a category for your confession:*\n\n"
            "Tap a category to select it.\n"
            "This helps with organization and makes it easier for others to find your confession.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=False
            ),
            parse_mode='Markdown'
        )
        return
    
    # Handle category selection
    if context.user_data.get('confession_stage') == 'category':
        if text.lower() == '❌ cancel':
            await cancel_confession(update, context)
            return
            
        # Check if the selected category is valid
        from models import Confession
        categories = Confession.get_categories()
        
        if text not in categories:
            await update.message.reply_text(
                "❌ Please select a valid category from the options below.",
                reply_markup=ReplyKeyboardMarkup(
                    [[cat] for cat in categories] + [['❌ Cancel']],
                    resize_keyboard=True,
                    one_time_keyboard=False
                )
            )
            return
            
        # Store the selected category and move to text input
        context.user_data['selected_categories'] = [text]
        context.user_data['confession_stage'] = 'text'
        
        await update.message.reply_text(
            "📝 Please type your confession:",
            reply_markup=ReplyKeyboardMarkup(
                [["❌ Cancel"]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return
        
    # Handle text input stage for confessions
    if context.user_data.get('confession_stage') == 'text':
        # Get the categories from context
        selected_categories = context.user_data.get('selected_categories', ['💬 General'])
        confession_text = update.message.text
        
        # Get category hashtags using the model method
        from models import Confession
        category_hashtags = Confession.get_category_hashtags(selected_categories)
        full_confession_text = f"{confession_text}\n\n{category_hashtags}"
        
        # Store confession data for preview
        context.user_data['confession_text'] = confession_text
        context.user_data['confession_hashtags'] = category_hashtags
        
        # Move to preview stage
        context.user_data['confession_stage'] = 'preview'
        
        # Show preview with confirmation buttons
        preview_text = (
            f"📝 *Preview Your Confession*\n\n"
            f"📌 *Categories:* {', '.join(selected_categories)}\n\n"
            f"{confession_text}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Submit", callback_data="preview_submit")],
            [InlineKeyboardButton("✏️ Edit", callback_data="preview_edit")],
            [InlineKeyboardButton("❌ Cancel", callback_data="preview_cancel")]
        ]
        
        await update.message.reply_text(
            preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # Return PREVIEW state to handle the callback
        return 'PREVIEW'
    
    # Handle main menu buttons
    if '📝 confess' in text or 'confess' in text:
        # Set state to await category selection
        context.user_data['awaiting_confession'] = True
        context.user_data['confession_stage'] = 'category'
        await ask_for_category(update, context)
        return
        
        # Get categories and create keyboard with checkboxes
        from models import Confession
        categories = Confession.get_categories()
        
        # Create a keyboard with 2 columns and checkboxes for selected categories
        keyboard = []
        for i in range(0, len(categories), 2):
            row = []
            for j in range(2):
                if i + j < len(categories):
                    cat = categories[i + j]
                    # No categories are selected initially
                    row.append(f"{cat}")
            if row:
                keyboard.append(row)
        
        # Add Done and Cancel buttons
        keyboard.append(['❌ Cancel'])
        
        await update.message.reply_text(
            "📚 *Select categories for your confession:*\n\n"
            "You can select multiple categories. Tap a category to select/deselect it, then tap '✅ Done' when finished.\n"
            "This helps with organization and makes it easier for others to find your confession.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=False
            ),
            parse_mode='Markdown'
        )
        return
        
    # (Removed bio update handling)
        
    # (Removed emoji picker fallback handling)
        
    # If we get here, it's not a command we recognize
    await update.message.reply_text(
        "I'm not sure what you're trying to do. Use the buttons or type /help for a list of commands."
    )

def configure_application() -> Application:
    """Configure and return a fully built Application with all handlers."""
    # Create the Application
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # 1. Command Handlers (must be added before the conversation handler)
    command_handlers = [
        ("start", start),
        ("help", help_command)
    ]
    for cmd, handler in command_handlers:
        application.add_handler(CommandHandler(cmd, handler))

    # 2. Profile-related callbacks (buttons only for now) — add BEFORE conversation handler for priority
    application.add_handler(CallbackQueryHandler(
        handle_profile_callback,
        pattern=r'^(edit_profile|back_to_profile|change_profile_emoji|change_nickname|change_bio|edit_visibility|my_confessions|my_comments|profile_settings)$',
        block=False
    ), group=0)

    # 3. Conversation Handler for confessions (must be added after command handlers)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('confess', start)],
        states={
            TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
            ],
            CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
                CallbackQueryHandler(button_click, pattern=r'^category_\d+$')
            ],
            'PREVIEW': [
                CallbackQueryHandler(button_click, pattern='^preview_')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_confession),
            MessageHandler(filters.ALL & ~filters.COMMAND, handle_text_input)
        ],
        allow_reentry=True,
        per_message=False
    )
    application.add_handler(conv_handler)

    # 4. Add preview callbacks with higher priority
    application.add_handler(CallbackQueryHandler(
        button_click,
        pattern='^preview_',
        block=False
    ), group=0)

    # 5. Message Handlers
    application.add_handler(MessageHandler(filters.ALL, log_incoming), group=-1)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_input
    ))

    # 6. Callback Query Handlers
    application.add_handler(CallbackQueryHandler(log_callback, pattern=r'.*'), group=-1)
    application.add_handler(CallbackQueryHandler(
        button_click,
        pattern=r'^(showcomments|addcomment|like|dislike|reply)_|^accept_rules$'
    ))

    # Import button_callback from confession module
    from confession import button_callback
    application.add_handler(CallbackQueryHandler(
        button_callback,
        pattern=r'^(approve|reject)_'
    ))

    # Error handler
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    """Entry point: validate env, build app, and run polling (no asyncio.run)."""
    logger.info("🚀 Initializing bot...")
    load_dotenv()

    required_vars = ['TELEGRAM_BOT_TOKEN', 'MONGODB_URI', 'ADMIN_IDS', 'CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.info("✅ Environment variables loaded successfully")

    application = configure_application()

    logger.info("🤖 Starting bot...")
    try:
        # Clean up any existing webhook before starting polling
        logger.info("🔄 Ensuring no webhook is set...")
        application.bot.delete_webhook(drop_pending_updates=True)
        
        logger.info("🔄 Starting polling for updates...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    except telegram.error.Conflict as e:
        logger.critical("❌ Another instance of this bot is already running. Only one instance can run at a time.")
        logger.critical("Please check for other running instances on this server or in other environments.")
        logger.critical(f"Error details: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {e}", exc_info=True)
        sys.exit(1)


async def _deprecated_show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery = None) -> None:
    # Deprecated placeholder; real profile handler lives in profile_handlers.show_profile
    return

async def _deprecated_show_emoji_picker(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int = None) -> None:
    # Deprecated placeholder
    return

async def _deprecated_update_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE, emoji: str, query: CallbackQuery = None) -> bool:
    # Deprecated placeholder
    return False

async def _deprecated_handle_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Deprecated placeholder; real handler imported from profile_handlers
    return

async def ask_for_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category selection keyboard."""
    try:
        print("ask_for_category called")  # Debug log
        
        # Create keyboard with categories
        keyboard = []
        print(f"Creating keyboard with {len(CATEGORIES)} categories")  # Debug log
        
        # Create two buttons per row
        for i in range(0, len(CATEGORIES), 2):
            row = []
            row.append(InlineKeyboardButton(CATEGORIES[i], callback_data=f"category_{i}"))
            if i + 1 < len(CATEGORIES):
                row.append(InlineKeyboardButton(CATEGORIES[i+1], callback_data=f"category_{i+1}"))
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        print("Created reply markup")  # Debug log
        
        message_text = "📝 Please select a category for your confession:"
        
        if update.callback_query:
            print("Handling callback query")  # Debug log
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=reply_markup
                )
                print("Edited message with category selection")  # Debug log
            except Exception as e:
                print(f"Error editing message: {str(e)}")  # Debug log
                await update.callback_query.message.reply_text(
                    message_text,
                    reply_markup=reply_markup
                )
        else:
            print("Sending new message")  # Debug log
            try:
                await update.message.reply_text(
                    message_text,
                    reply_markup=reply_markup
                )
                print("Sent category selection message")  # Debug log
            except Exception as e:
                print(f"Error sending message: {str(e)}")  # Debug log
                raise
                
    except Exception as e:
        print(f"Error in ask_for_category: {str(e)}")  # Debug log
        error_message = "❌ An error occurred while showing categories. Please try again."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_message)
        elif update.message:
            await update.message.reply_text(error_message)
        return ConversationHandler.END

async def _deprecated_show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, query: CallbackQuery = None) -> None:
    # Deprecated placeholder
    return

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the confession process and clean up all related data."""
    # Clear all confession-related data
    for key in ['awaiting_confession', 'confession_stage', 'confession_text']:
        if key in context.user_data:
            del context.user_data[key]
    
    # Send cancellation message with main menu
    await update.message.reply_text(
        '❌ Confession cancelled. What would you like to do next?',
        reply_markup=ReplyKeyboardMarkup(
            [['📝 Confess', '👤 Bio'], ['❓ Help']],
            resize_keyboard=True
        )
    )
    return ConversationHandler.END

# Helper to refresh the channel button's comment count for a given confession
async def refresh_channel_comment_count(confession_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        from bson import ObjectId
        # Find the channel message id for this confession
        conf_col = db.get_collection('confessions')
        conf_doc = conf_col.find_one({"_id": ObjectId(confession_id)})
        if not conf_doc:
            logger.warning(f"Confession not found for refresh: {confession_id}")
            return
        channel_msg_id = conf_doc.get('channel_msg_id')
        if not channel_msg_id:
            logger.info(f"No channel message id for confession {confession_id}, skipping refresh")
            return
        # Count comments (including replies)
        comments_col = db.get_collection('comments')
        count = comments_col.count_documents({"confession_id": confession_id})
        # Build deep-link URL
        bot_username = context.bot.username
        if not bot_username:
            me = await context.bot.get_me()
            bot_username = me.username
        comment_url = f"https://t.me/{bot_username}?start=comment_{confession_id}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 View/Add Comments ({count})", url=comment_url)]
        ])
        # Edit the reply markup on the channel message
        await context.bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=channel_msg_id, reply_markup=keyboard)
        logger.info(f"Refreshed channel comment count for confession {confession_id}: {count}")
    except Exception as e:
        logger.warning(f"refresh_channel_comment_count failed: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    if update and hasattr(update, 'effective_message') and update.effective_message:
        await update.effective_message.reply_text(
            'An error occurred while processing your request. Please try again later.'
        )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
