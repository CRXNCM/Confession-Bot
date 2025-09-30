import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from bson.objectid import ObjectId
from database import db
from config import ADMIN_GROUP_ID, CHANNEL_ID

# Database collection names
CONFESSIONS_COLLECTION = "confessions"

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

async def handle_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the confession process."""
    if context.args:
        # If confession text is provided directly, ask for category
        confession_text = " ".join(context.args)
        context.user_data['confession_text'] = confession_text
        await ask_for_category(update, context)
        return CATEGORY
    else:
        # If no text provided, ask for it first
        await update.message.reply_text(
            "✍️ Please type your confession. You'll be able to choose a category next."
        )
        return TEXT

async def receive_confession_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the confession text and ask for category."""
    try:
        print("receive_confession_text called")  # Debug log
        if not update.message or not update.message.text:
            print("No message or text in update")  # Debug log
            await update.message.reply_text("❌ Please provide a valid confession text.")
            return TEXT
            
        confession_text = update.message.text
        print(f"Received confession text: {confession_text}")  # Debug log
        
        # Store the confession text in user_data
        context.user_data['confession_text'] = confession_text
        print("Stored confession text in user_data")  # Debug log
        
        # Ask for category
        print("Calling ask_for_category")  # Debug log
        await ask_for_category(update, context)
        print("Returning CATEGORY state")  # Debug log
        return CATEGORY
        
    except Exception as e:
        print(f"Error in receive_confession_text: {str(e)}")  # Debug log
        await update.message.reply_text("❌ An error occurred. Please try again.")
        return ConversationHandler.END

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

async def save_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the confession with the selected category."""
    try:
        print("save_confession called")  # Debug log
        
        if not update.callback_query:
            print("No callback query in update")  # Debug log
            if update.message:
                await update.message.reply_text("❌ Invalid request. Please use the category buttons to select a category.")
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        print(f"Callback query data: {query.data}")  # Debug log
        
        # Get the category index from callback data
        try:
            category_idx = int(query.data.split('_')[1])
            print(f"Category index: {category_idx}")  # Debug log
            category = CATEGORIES[category_idx]
            print(f"Selected category: {category}")  # Debug log
        except (IndexError, ValueError, KeyError) as e:
            print(f"Error getting category: {str(e)}")  # Debug log
            await query.edit_message_text("❌ Error: Invalid category selection. Please try again.")
            return ConversationHandler.END
        
        # Get the confession text from user_data
        confession_text = context.user_data.get('confession_text')
        print(f"Confession text from user_data: {confession_text}")  # Debug log
        
        if not confession_text:
            error_msg = "❌ Error: Could not find your confession text. Please start over with /confess."
            print(error_msg)  # Debug log
            await query.edit_message_text(error_msg)
            return ConversationHandler.END
        
        user = update.effective_user
        user_fullname = ' '.join(filter(None, [user.first_name, user.last_name])) or 'Anonymous'
        print(f"User: {user_fullname} (ID: {user.id})")  # Debug log
        
        # Prepare confession data
        confession = {
            "user_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "user_fullname": user_fullname,
            "text": confession_text,
            "category": category,
            "status": "pending",  # pending, approved, rejected
            "created_at": update.effective_message.date,
            "updated_at": update.effective_message.date
        }
        
        # Add timestamps
        from datetime import datetime
        now = datetime.utcnow()
        confession.update({
            "created_at": now,
            "updated_at": now
        })
        
        print(f"Saving confession to database: {confession}")  # Debug log
        
        # Save confession to database and get the ID
        result = await db.get_collection(CONFESSIONS_COLLECTION).insert_one(confession)
        confession_id = str(result.inserted_id)
        print(f"Confession saved with ID: {confession_id}")  # Debug log
        
        # Clear the user_data to prevent data leakage
        if 'confession_text' in context.user_data:
            del context.user_data['confession_text']
        
        # Create approval buttons for admin
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send to admin group for approval
        admin_message = await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"📨 <b>New Confession (ID: {confession_id})</b>\n\n"
                 f"👤 <b>From:</b> {user_fullname} (@{user.username or 'N/A'})\n"
                 f"🏷️ <b>Category:</b> {category}\n\n"
                 f"📝 <b>Confession:</b>\n{confession_text}",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        # Update the confession with the admin message ID for future reference
        await db.get_collection(CONFESSIONS_COLLECTION).update_one(
            {"_id": result.inserted_id},
            {"$set": {"admin_message_id": admin_message.message_id}}
        )
        
        print(f"Confirmation sent to admin group. Message ID: {admin_message.message_id}")  # Debug log
        
        # Notify user
        await query.edit_message_text(
            f"✅ Your confession has been received and is pending approval!\n\n"
            f"📝 <b>Your Confession:</b>\n{confession_text}\n\n"
            f"🏷️ <b>Category:</b> {category}\n\n"
            "Our moderators will review it shortly. Thank you for your patience!",
            parse_mode='HTML'
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        print(f"Error in save_confession: {str(e)}")  # Debug log
        error_msg = "❌ An error occurred while saving your confession. Please try again."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        elif update.message:
            await update.message.reply_text(error_msg)
        return ConversationHandler.END

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
            
            # Get the total count of approved confessions for the number
            confessions_col = db.get_collection('confessions')
            confession_number = confessions_col.count_documents({"status": "approved"}) + 1
            
            # Escape the confession text for HTML
            from html import escape
            escaped_confession = escape(confession['text'])
            
            # Get the category with a default value if not set
            category = confession.get('category', '❓ Uncategorized')
            
            # Create the channel message with HTML formatting
            channel_message = (
                f"💌 <b>Confession {confession_number}</b>\n"
                f"🏷️ <i>{category}</i>\n\n"
                f"💬 {escaped_confession}\n\n"
                f"#Confession{confession_number}"  # No need to escape in HTML mode
            )
            
            try:
                print(f"Attempting to send message to channel ID: {CHANNEL_ID}")
                # Build a deep link back to the bot for comments
                bot_username = context.bot.username
                if not bot_username:
                    me = await context.bot.get_me()
                    bot_username = me.username

                # Compute existing number of comments for this confession (include replies)
                comments_col = db.get_collection('comments')
                comment_count = comments_col.count_documents({'confession_id': confession_id})

                comment_url = f"https://t.me/{bot_username}?start=comment_{confession_id}"
                channel_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"💬 Comments ({comment_count})", url=comment_url)]
                ])
                # Send to channel
                sent = await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=channel_message,
                    parse_mode="HTML",  # Changed to HTML parsing mode
                    reply_markup=channel_keyboard
                )
                print("Message sent to channel successfully")
                # Store the channel message id on this confession
                try:
                    col = db.get_collection('confessions')
                    col.update_one({"_id": ObjectId(confession_id)}, {"$set": {"channel_msg_id": sent.message_id}})
                except Exception as e:
                    print(f"Warning: failed to store channel message id: {e}")
                
                # Update the admin message to show it was approved
                await query.edit_message_text(
                    f"✅ Confession #{confession_number} approved and posted to channel!\n\n"
                    f"Confession ID: `{confession_id}`"
                )
                
                # Notify the user if possible
                try:
                    user_id = confession.get('user_id')
                    if user_id:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🎉 Your confession (Confession #{confession_number}) has been approved and posted to the channel!"
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