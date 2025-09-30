# Telegram Confession Bot

An anonymous confession bot for Telegram that allows users to submit confessions, comment on them, and engage in anonymous discussions with customizable profiles.

## Features

- Anonymous confession submission with sequential numbering
- Admin approval system with moderation
- Commenting on confessions with like/dislike reactions
- Real-time updates and notifications
- Anonymous chat between users with approval flow
- Secure and scalable with MongoDB
- Comment count tracking on channel posts
- User reporting system for inappropriate content
- **User Profiles** with:
  - Customizable profile emoji
  - Personal nickname
  - Bio section
  - Confession history

## Prerequisites

- Python 3.8+
- Telegram Bot Token from [@BotFather](https://t.me/botfather)
- MongoDB database (local or cloud)
- (Optional) Redis for production session management

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd DDCFS
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Fill in your Telegram bot token and MongoDB connection string

4. Set up MongoDB:
   - Create a new database
   - The bot will automatically create the required collections on first run

5. Run the database migration (required for profile features):
   ```bash
   python migrate_profile_fields.py
   ```

6. Run the bot:
   ```bash
   python bot.py
   ```

## Project Structure

- `bot.py` - Main application entry point
- `bot.py` - Main bot logic and handlers
- `confession.py` - Confession handling and moderation
- `models.py` - Database models and operations
- `config.py` - Configuration settings
- `database.py` - Database connection setup
- `migrate_profile_fields.py` - Database migration script for profile features
- `.env` - Environment variables (not committed to version control)
- `requirements.txt` - Python dependencies

## Environment Variables

Create a `.env` file with the following variables:

```
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Admin User IDs (comma-separated for multiple admins)
ADMIN_IDS=123456789,987654321

# Channel ID where confessions will be posted
CHANNEL_ID=-1001234567890

# Admin Group ID for moderation
ADMIN_GROUP_ID=-1001234567890

# MongoDB Connection String
MONGODB_URI=mongodb://username:password@host:port/database_name
```

## Key Features in Detail

### Confession Submission
- Users can submit confessions which are held for admin approval
- Each approved confession gets a unique sequential number
- Confessions are posted to the configured channel with comment functionality

### Comment System
- Users can comment on confessions
- Comments support rich text formatting
- Like/Dislike functionality for comments
- Reply functionality for threaded discussions

### Moderation
- Admin approval system for all confessions
- User reporting system for inappropriate content
- Ability to ban users if needed

### User Profiles
- **Custom Profile Emoji**: Choose from a variety of emojis to represent your profile
- **Personal Nickname**: Set a custom display name that appears in your profile
- **Bio Section**: Share a short bio (up to 500 characters) to tell others about yourself
- **Confession History**: View all your approved confessions in one place
- **Profile Statistics**: See how many confessions you've submitted

### Profile Customization
1. Tap on the "👤 Profile" button in the main menu
2. Choose "⚙️ Customization"
3. Select what you want to update:
   - 😀 Change your profile emoji
   - 📝 Update your nickname
   - ✏️ Set or update your bio

### Anonymous Chat
- Users can request to chat anonymously with confession authors
- Chat requires approval from the confession author
- Secure and private messaging between users

## Database Schema

The bot uses MongoDB with the following collections:
- `confessions` - Stores all confessions with their status and metadata
- `comments` - Stores comments and their relationships to confessions
- `users` - User information and preferences

## Deployment

For production deployment, consider using:
- A VPS or cloud provider
- Process manager like PM2 or systemd
- Redis for session management (optional)
- Monitoring and logging

## Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

## License

MIT
