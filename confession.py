import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from bson.objectid import ObjectId
from database import db
from config import ADMIN_GROUP_ID, CHANNEL_ID

# Database collection names
CONFESSIONS_COLLECTION = "confessions"

async def handle_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /confess command or button press."""
    # Check if user provided a confession
    if not context.args:
        await update.message.reply_text(
            "Please share your confession after the /confess command.\n"
            "Example: /confess I have a secret to share..."
        )
        return

    confession_text = " ".join(context.args)
    user = update.effective_user

    # Save confession to database
    user = update.effective_user  # Get the user who sent the message
    user_fullname = ' '.join(filter(None, [user.first_name, user.last_name])) or 'Anonymous'
    
    confession = {
        "user_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "user_fullname": user_fullname,
        "text": confession_text,
        "status": "pending",  # pending, approved, rejected
        "created_at": update.message.date,
        "updated_at": update.message.date
    }
    
    # Save confession to database and get the ID
    result = await db.get_collection(CONFESSIONS_COLLECTION).insert_one(confession)
    confession_id = str(result.inserted_id)
    
    # Create approval buttons for admin
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send to admin group for approval
    from telegram.helpers import escape_markdown
    
    # Build user display info
    user_parts = []
    if user.username:
        user_parts.append(f"@{escape_markdown(user.username, version=2)}")
    if user.first_name or user.last_name:
        name_parts = []
        if user.first_name:
            name_parts.append(escape_markdown(user.first_name, version=2))
        if user.last_name:
            name_parts.append(escape_markdown(user.last_name, version=2))
        user_parts.append(' '.join(name_parts))
    
    user_display = ' '.join(user_parts) or 'Anonymous'
    
    # Escape the confession text
    escaped_confession = escape_markdown(confession_text, version=2)
    
    # Prepare admin message with user details
    admin_message = (
        f"📨 *New Confession* \(ID: `{confession_id}`\)\n\n"
        f"👤 *User:* {user_display}\n"
        f"🆔 *User ID:* `{user.id}`\n"
        f"🔗 *Profile Link:* [Contact User](tg://user?id={user.id})\n\n"
        f"💬 *Confession:*\n{escaped_confession}"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_message,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        print(f"Error sending message to admin group: {e}")
        # Try sending a simpler message if Markdown parsing fails
        simple_message = (
            f"📨 New Confession (ID: {confession_id})\n\n"
            f"👤 User: {user_display}\n"
            f"🆔 User ID: {user.id}\n\n"
            f"💬 Confession:\n{confession_text}"
        )
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=simple_message,
            reply_markup=reply_markup
        )

    # Confirm to user
    await update.message.reply_text(
        "✅ Your confession has been received and is pending approval by admins. "
        "It will be posted to the channel soon if approved.",
        reply_markup=ReplyKeyboardMarkup(
            [["📝 Confess", "👤 Bio"], ["❓ Help"]],
            resize_keyboard=True
        )
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks for approving/rejecting confessions and other actions."""
    query = update.callback_query
    await query.answer()

    if not query.data:
        await query.edit_message_text("❌ Error: No callback data received.")
        return
        
    try:
        # Debug: Print the callback data
        print(f"Callback data received: {query.data}")
        
        # Check if this is a rules acceptance callback
        if query.data == "accept_rules":
            # Create the help message with buttons
            help_text = (
                "🤖 <b>Confession Bot Help</b>\n\n"
                "<b>Available Commands:</b>\n"
                "📝 <b>Confess</b> - Submit an anonymous confession\n"
                "👤 <b>Bio</b> - Set or update your bio\n"
                "❓ <b>Help</b> - Show this help message\n"
                "\nTap the buttons below to get started!"
            )
            
            # Create a keyboard with the main commands
            keyboard = [
                ["📝 Confess"],
                ["👤 Bio", "❓ Help"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            # Send the help message with the keyboard
            await query.edit_message_text("✅ Thank you for accepting the rules!")
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=help_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return
            
        # Ensure the callback data is in the expected format
        if '_' not in query.data:
            await query.edit_message_text("❌ Error: Invalid callback data format.")
            return
        
        action, confession_id = query.data.split("_", 1)
        print(f"Action: {action}, Confession ID: {confession_id}")
        
        # Validate confession_id before querying
        if not confession_id:
            await query.edit_message_text("❌ Error: No confession ID provided.")
            return
            
        # Convert to ObjectId and validate format
        if not ObjectId.is_valid(confession_id):
            raise ValueError(f"Invalid ObjectId format: {confession_id}")
            
        # Get the database collection
        collection = db.get_collection('confessions')
        
        # Find the confession
        confession = collection.find_one({"_id": ObjectId(confession_id)})
        
        if not confession:
            await query.edit_message_text("❌ Error: Confession not found in database.")
            return
            
        # Handle the action
        if action == "approve":
            # Update status in database
            collection.update_one(
                {"_id": ObjectId(confession_id)},
                {"$set": {"status": "approved"}}
            )
            
            # Get the updated confession
            confession = collection.find_one({"_id": ObjectId(confession_id)})
            if not confession:
                await query.edit_message_text("❌ Error: Could not find confession in database.")
                return
            
            # Format the message for the channel (no user info)
            from telegram.helpers import escape_markdown
            
            # Escape the confession text for MarkdownV2
            escaped_confession = escape_markdown(confession['text'], version=2)
            
            channel_message = (
                "💌 *New Confession*\n\n"
                f"💬 {escaped_confession}\n\n"
                "\#Confession"  # Escaped the # with \
            )
            
            try:
                print(f"Attempting to send message to channel ID: {CHANNEL_ID}")
                # Send to channel
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=channel_message,
                    parse_mode="MarkdownV2"
                )
                print("Message sent to channel successfully")
                
                # Update the admin message to show it was approved
                await query.edit_message_text(
                    f"✅ Confession approved and posted to channel!\n\n"
                    f"Confession ID: `{confession_id}`"
                )
                
                # Notify the user if possible
                try:
                    user_id = confession.get('user_id')
                    if user_id:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="🎉 Your confession has been approved and posted to the channel!"
                        )
                except Exception as e:
                    print(f"Could not notify user: {e}")
                    
            except Exception as e:
                print(f"Error posting to channel: {e}")
                error_msg = (
                    f"❌ Error posting to channel.\n"
                    f"Error: {str(e)}\n"
                    f"Channel ID: {CHANNEL_ID}\n"
                    "Please check that:\n"
                    "1. The bot is added to the channel as admin\n"
                    "2. The channel ID is correct\n"
                    "3. The bot has 'Post Messages' permission"
                )
                await query.edit_message_text(error_msg)

        elif action == "reject":
            # Update status in database
            collection.update_one(
                {"_id": ObjectId(confession_id)},
                {"$set": {"status": "rejected"}}
            )
            await query.edit_message_text("❌ Confession rejected.")
            
        else:
            await query.edit_message_text(f"❌ Error: Unknown action '{action}'")
            
    except ValueError as e:
        print(f"ValueError in button_callback: {e}")
        # Don't show error message for non-confession related callbacks
        if "accept_rules" not in str(e):
            await query.edit_message_text("❌ Error: Invalid format for this action.")
    except Exception as e:
        print(f"Unexpected error in button_callback: {e}")
        await query.edit_message_text("❌ An error occurred while processing your request.")