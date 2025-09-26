from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the Supabase client."""
        try:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Successfully connected to Supabase")
        except Exception as e:
            logger.error(f"Error connecting to Supabase: {e}")
            raise
    
    # User related methods
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by Telegram user ID."""
        try:
            response = self.supabase.table('users').select('*').eq('user_id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def create_user(self, user_data: Dict) -> Optional[Dict]:
        """Create a new user."""
        try:
            response = self.supabase.table('users').insert(user_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None
    
    async def update_user_bio(self, user_id: int, bio: str) -> bool:
        """Update user's bio."""
        try:
            self.supabase.table('users').update({'bio': bio}).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating bio for user {user_id}: {e}")
            return False
    
    # Confession related methods
    async def create_confession(self, confession_data: Dict) -> Optional[Dict]:
        """Create a new confession."""
        try:
            response = self.supabase.table('confessions').insert(confession_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating confession: {e}")
            return None
    
    async def get_pending_confessions(self) -> List[Dict]:
        """Get all pending confessions."""
        try:
            response = self.supabase.table('confessions').select('*').eq('status', 'pending').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting pending confessions: {e}")
            return []
    
    async def update_confession_status(self, confession_id: int, status: str, channel_msg_id: int = None) -> bool:
        """Update confession status and optionally set channel message ID."""
        try:
            update_data = {'status': status}
            if channel_msg_id is not None:
                update_data['channel_msg_id'] = channel_msg_id
                
            self.supabase.table('confessions').update(update_data).eq('id', confession_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating confession {confession_id}: {e}")
            return False
    
    # Comment related methods
    async def add_comment(self, comment_data: Dict) -> Optional[Dict]:
        """Add a comment to a confession."""
        try:
            response = self.supabase.table('comments').insert(comment_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding comment: {e}")
            return None
    
    async def get_comments(self, confession_id: int) -> List[Dict]:
        """Get all comments for a confession."""
        try:
            response = self.supabase.table('comments').select('*').eq('confession_id', confession_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting comments for confession {confession_id}: {e}")
            return []

# Singleton instance
db = Database()
