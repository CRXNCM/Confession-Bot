import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Minimal profile view: show basic stats without menus or callbacks."""
    try:
        user = update.effective_user
        confessions_count = len(await db.get_user_confessions(user.id))
        comments_count = len(await db.get_user_comments(user.id))

        text = (
            "<b>👤 Your Profile</b>\n\n"
            f"🆔 <b>User ID</b>: <code>{user.id}</code>\n"
            f"📝 <b>Confessions</b>: {confessions_count}\n"
            f"💬 <b>Comments</b>: {comments_count}"
        )

        # Inline menu for profile actions
        keyboard = [
            [
                InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile"),
                InlineKeyboardButton("📜 My Confessions", callback_data="my_confessions")
            ],
            [
                InlineKeyboardButton("💬 My Comments", callback_data="my_comments"),
                InlineKeyboardButton("⚙️ Settings", callback_data="profile_settings")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error in show_profile: {e}")
        if update.message:
            await update.message.reply_text("❌ Failed to load profile. Please try again later.")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Failed to load profile. Please try again later.")


async def show_edit_profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the Edit Profile menu with buttons only."""
    text = "<b>✏️ Edit Profile</b>\n\nChoose what you want to change:"
    keyboard = [
        [InlineKeyboardButton("😀 Change Profile Emoji", callback_data="change_profile_emoji")],
        [InlineKeyboardButton("📛 Change Nickname", callback_data="change_nickname")],
        [InlineKeyboardButton("📝 Set/Update Bio", callback_data="change_bio")],
        [InlineKeyboardButton("🔒 Profile Details & Visibility", callback_data="edit_visibility")],
        [InlineKeyboardButton("⬅️ Back to Profile", callback_data="back_to_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        q = update.callback_query
        await q.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode='HTML')


async def handle_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route profile-related callbacks (buttons only for now)."""
    query = update.callback_query
    data = query.data
    # Always acknowledge the callback to avoid client spinners/timeouts
    try:
        await query.answer()
    except Exception:
        pass
    # Buttons only; no functionality yet
    if data == 'edit_profile':
        await show_edit_profile_menu(update, context)
        return
    if data == 'back_to_profile':
        await show_profile(update, context)
        return
