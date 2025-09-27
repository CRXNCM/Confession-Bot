import os
import logging
import time
import uuid
from dotenv import load_dotenv
from database import db
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

# In-memory anonymous chat sessions
# CHAT_SESSIONS: session_id -> {requester_id, owner_id, status: 'pending'|'active'|'ended'}
# CHAT_PEERS: user_id -> {peer_id, session_id}
CHAT_SESSIONS = {}
CHAT_PEERS = {}

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
    # Check for deep-link parameters e.g. /start comment_<confession_id>
    if context.args:
        arg = context.args[0]
        if arg.startswith('comment_'):
            confession_id = arg.split('_', 1)[1]
            # Store the context for this session
            context.user_data['comment_confession_id'] = confession_id
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
        # Handle deep-link to anonymous profile for a specific comment
        if arg.startswith('profilec_'):
            from bson import ObjectId
            from models import Comment, User
            cid = arg.split('_', 1)[1]
            try:
                obj_id = ObjectId(cid)
            except Exception:
                await update.message.reply_text("❌ Invalid reference.")
                return
            c = Comment.get_comment(obj_id)
            if not c:
                await update.message.reply_text("❌ Comment not found.")
                return
            # Optional: show a minimal profile header and actions
            user_obj = User.get_user(c.get('user_id'))
            bio = (user_obj.get('bio') if user_obj else None) or "This user has not set a bio yet."
            profile_text = (
                "👤 Anonymous\n\n"
                "📝 Bio:\n"
                f"{bio}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚩 Report User", callback_data=f"reportc_{cid}")],
                [InlineKeyboardButton("💬 Request Chat", callback_data=f"requestc_{cid}")]
            ])
            await update.message.reply_text(profile_text, reply_markup=keyboard)
            return

    # Anonymous profile removed

    # Handle report user: notify admins with context
    if query.data and query.data.startswith('reportc_'):
        from bson import ObjectId
        from models import Comment
        _, cid = query.data.split('_', 1)
        try:
            obj_id = ObjectId(cid)
        except Exception:
            await query.message.reply_text("❌ Invalid reference.")
            return
        c = Comment.get_comment(obj_id)
        if not c:
            await query.message.reply_text("❌ Comment not found.")
            return
        reporter = update.effective_user
        text = c.get('text', '')
        owner_id = c.get('user_id')
        admin_msg = (
            "🚩 Report Received\n\n"
            f"Comment ID: {cid}\n"
            f"Owner User ID: {owner_id}\n"
            f"Reporter User ID: {reporter.id}\n\n"
            f"Excerpt:\n{text[:500]}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_msg)
        except Exception:
            logger.warning("Failed to send report to admin group")
        await query.message.reply_text("✅ Report submitted. Our admins will review this user.")
        return

    # Handle request chat: ask owner for approval
    if query.data and query.data.startswith('requestc_'):
        from bson import ObjectId
        from models import Comment
        _, cid = query.data.split('_', 1)
        requester_id = update.effective_user.id
        try:
            obj_id = ObjectId(cid)
        except Exception:
            await query.message.reply_text("❌ Invalid reference.")
            return
        c = Comment.get_comment(obj_id)
        if not c:
            await query.message.reply_text("❌ Comment not found.")
            return
        owner_id = c.get('user_id')
        if owner_id == requester_id:
            await query.message.reply_text("ℹ️ You cannot request a chat with yourself.")
            return
        session_id = str(uuid.uuid4())
        CHAT_SESSIONS[session_id] = {
            'requester_id': requester_id,
            'owner_id': owner_id,
            'status': 'pending'
        }
        # Ask owner for approval
        try:
            approve_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"approvechat_{session_id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"rejectchat_{session_id}")]
            ])
            await context.bot.send_message(
                chat_id=owner_id,
                text=(
                    "💬 Anonymous Chat Request\n\n"
                    "Someone wants to chat with you anonymously regarding one of your comments.\n\n"
                    "Do you approve this request?"
                ),
                reply_markup=approve_keyboard
            )
        except Exception as e:
            logger.warning(f"Unable to reach comment owner: {e}")
            await query.message.reply_text("❌ Could not contact the user. They may not have started the bot.")
            return
        await query.message.reply_text("✅ Chat request sent. You'll be notified if they accept.")
        return

    # Owner responds to chat request
    if query.data and (query.data.startswith('approvechat_') or query.data.startswith('rejectchat_')):
        action, session_id = query.data.split('_', 1)
        sess = CHAT_SESSIONS.get(session_id)
        if not sess or sess.get('status') != 'pending':
            await query.message.reply_text("❌ This chat request is no longer available.")
            return
        owner_id = sess['owner_id']
        requester_id = sess['requester_id']
        if action == 'rejectchat':
            sess['status'] = 'ended'
            try:
                await context.bot.send_message(chat_id=requester_id, text="❌ Your chat request was rejected.")
            except Exception:
                pass
            await query.message.edit_text("You rejected the chat request.")
            return
        # Approve
        sess['status'] = 'active'
        CHAT_PEERS[owner_id] = {'peer_id': requester_id, 'session_id': session_id}
        CHAT_PEERS[requester_id] = {'peer_id': owner_id, 'session_id': session_id}
        leave_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚪 Leave Chat", callback_data=f"leavechat_{session_id}")]
        ])
        try:
            await context.bot.send_message(chat_id=requester_id, text="✅ Anonymous chat started. Say hi!", reply_markup=leave_keyboard)
        except Exception:
            pass
        await query.message.edit_text("✅ Chat approved. You can now chat anonymously.", reply_markup=leave_keyboard)
        return

    # Leave chat
    if query.data and query.data.startswith('leavechat_'):
        _, session_id = query.data.split('_', 1)
        sess = CHAT_SESSIONS.get(session_id)
        if not sess:
            await query.message.reply_text("❌ Chat session not found.")
            return
        if sess.get('status') != 'active':
            await query.message.reply_text("ℹ️ This chat is already closed.")
            return
        owner_id = sess['owner_id']
        requester_id = sess['requester_id']
        sess['status'] = 'ended'
        for uid in [owner_id, requester_id]:
            CHAT_PEERS.pop(uid, None)
        try:
            peer = requester_id if update.effective_user.id == owner_id else owner_id
            await context.bot.send_message(chat_id=peer, text="ℹ️ The other person left the chat.")
        except Exception:
            pass
        await query.message.edit_text("🚪 You left the chat.")
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
            Comment.add_reply(parent_cid, reply_data)
            # Refresh channel button count for this confession
            try:
                await refresh_channel_comment_count(parent.get('confession_id'), context)
            except Exception as e:
                logger.warning(f"Failed to refresh channel comment count (reply): {e}")
        except Exception as e:
            logger.error(f"Error saving reply: {e}")
            await update.message.reply_text("❌ Failed to save your reply. Please try again later.")
            return

        # Clear reply state
        context.user_data.pop('awaiting_reply', None)
        context.user_data.pop('parent_comment_id', None)

        await update.message.reply_text(
            "✅ Your reply has been submitted.",
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

async def button_click(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    try:
        logger.info(f"Callback received: {query.data}")
    except Exception:
        pass
    
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
            # Build bot username for deep-link to anonymous profile
            bot_username = context.bot.username
            if not bot_username:
                me = await context.bot.get_me()
                bot_username = me.username
            for c in comments[:10]:
                roll_no = c.get('roll_no') or '-'
                text = c.get('text', '')
                likes = c.get('likes', 0)
                dislikes = c.get('dislikes', 0)
                comment_id = str(c.get('_id'))
                # Escape text for HTML
                text_html = _html.escape(text)
                profile_url = f"https://t.me/{bot_username}?start=profilec_{comment_id}"
                body = (
                    f"🗨️ Comment #{roll_no}\n\n"
                    f"{text_html}\n\n"
                    f"👍 {likes}    👎 {dislikes}\n\n"
                    f"<a href=\"{profile_url}\">👤 Anonymous</a>"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("👍 Like", callback_data=f"like_{comment_id}"),
                     InlineKeyboardButton("👎 Dislike", callback_data=f"dislike_{comment_id}")],
                    [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{comment_id}")],
                    [InlineKeyboardButton("🚩 Report User", callback_data=f"reportc_{comment_id}"),
                     InlineKeyboardButton("💬 Request Chat", callback_data=f"requestc_{comment_id}")]
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
                Comment.like_comment(obj_id)
            else:
                Comment.dislike_comment(obj_id)
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
            # Build bot username for deep-link to anonymous profile
            bot_username = context.bot.username
            if not bot_username:
                me = await context.bot.get_me()
                bot_username = me.username
            text_html = _html.escape(text)
            profile_url = f"https://t.me/{bot_username}?start=profilec_{cid}"
            body = (
                f"🗨️ Comment #{roll_no}\n\n"
                f"{text_html}\n\n"
                f"👍 {likes}    👎 {dislikes}\n\n"
                f"<a href=\"{profile_url}\">👤 Anonymous</a>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👍 Like", callback_data=f"like_{cid}"),
                 InlineKeyboardButton("👎 Dislike", callback_data=f"dislike_{cid}")],
                [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{cid}")],
                [InlineKeyboardButton("🚩 Report User", callback_data=f"reportc_{cid}"),
                 InlineKeyboardButton("💬 Request Chat", callback_data=f"requestc_{cid}")]
            ])
            try:
                await query.edit_message_text(body, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"edit_message_text failed, sending new message instead: {e}")
                await query.message.reply_text(body, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating reaction: {e}")
            await query.message.reply_text("❌ Failed to update reaction. Please try again later.")
        return

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
    logger.info(f"/help invoked: { _summarize_update(update) }")
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
    t0 = time.perf_counter()
    logger.info(f"text input: { _summarize_update(update) }")
    text = update.message.text.lower()
    user = update.effective_user
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
            f"📨 *New Confession* \\(ID: `{confession_id}` \\)\n\n"
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
        context.user_data.pop('awaiting_comment', None)
        context.user_data.pop('comment_confession_id', None)
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
        logger.info(f"text input completed (bio set) in {(time.perf_counter()-t0)*1000:.1f}ms")
        return
    else:
        await update.message.reply_text(
            "I didn't understand that command. Please use the buttons below or type /help for assistance.",
            reply_markup=ReplyKeyboardMarkup(
                [['📝 Confess', '👤 Bio'], ['❓ Help']],
                resize_keyboard=True
            )
        )
        logger.info(f"text input completed (fallback) in { (time.perf_counter()-t0)*1000:.1f} ms")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("confess", handle_confession))
    # Pre-log every incoming update and callback (runs before other handlers)
    application.add_handler(MessageHandler(filters.ALL, log_incoming), group=-1)
    application.add_handler(CallbackQueryHandler(log_callback, pattern=r'.*'), group=-1)
    # Route callback queries specifically to avoid conflicts
    # Comment-related and rules acceptance callbacks
    application.add_handler(CallbackQueryHandler(button_click, pattern=r'^(showcomments|addcomment|like|dislike|reply|reportc|requestc|approvechat|rejectchat|leavechat)_|^accept_rules$'))
    # Confession approval/rejection callbacks
    application.add_handler(CallbackQueryHandler(button_callback, pattern=r'^(approve|reject)_'))
    
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
            [InlineKeyboardButton(f"💬 Comments ({count})", url=comment_url)]
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
    main()
