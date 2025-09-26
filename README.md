# Telegram Confession Bot

An anonymous confession bot for Telegram that allows users to submit confessions and comment on them.

## Features

- Anonymous confession submission
- Admin approval system
- Commenting on confessions
- Real-time updates
- Secure and scalable with Supabase

## Prerequisites

- Python 3.8+
- Telegram Bot Token from [@BotFather](https://t.me/botfather)
- Supabase account (free tier)

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
   - Fill in your Telegram bot token and Supabase credentials

4. Set up Supabase:
   - Create a new project on [Supabase](https://supabase.com/)
   - Run the SQL from `schema.sql` in the SQL editor
   - Get your project URL and anon/public key from Project Settings > API

5. Run the bot:
   ```bash
   python bot.py
   ```

## Project Structure

- `bot.py` - Main application entry point
- `config.py` - Configuration settings
- `database.py` - Database operations
- `.env` - Environment variables (not committed to version control)
- `requirements.txt` - Python dependencies

## Environment Variables

Create a `.env` file with the following variables:

```
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Supabase Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Admin User ID (comma-separated for multiple admins)
ADMIN_IDS=123456789,987654321
```

## Database Schema

See `schema.sql` for the database schema.

## Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

## License

MIT
