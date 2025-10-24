from pymongo import MongoClient
from config import MONGODB_URI, DATABASE_NAME
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
    
    def _initialize(self, max_retries: int = 3, retry_delay: int = 2):
        """Initialize the MongoDB client with retry logic and create indexes.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay in seconds between retry attempts
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Configure connection with timeouts and retry writes
                self.client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=30000,  # 30 seconds
                    connectTimeoutMS=30000,          # 30 seconds
                    socketTimeoutMS=45000,           # 45 seconds
                    maxPoolSize=100,                 # Maximum number of connections
                    retryWrites=True,
                    retryReads=True,
                    connect=False  # Lazy connect
                )
                
                # Test the connection
                self.client.server_info()
                self.db = self.client[DATABASE_NAME]
                logger.info("✅ Successfully connected to MongoDB!")
                
                # Create indexes
                self._create_indexes()
                return  # Success - exit the retry loop
                
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(
                        f"⚠️ Connection attempt {attempt + 1}/{max_retries} failed: {str(e)}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    import time
                    time.sleep(wait_time)
                continue
        
        # If we get here, all retries failed
        error_msg = f"❌ Failed to connect to MongoDB after {max_retries} attempts: {str(last_exception)}"
        logger.error(error_msg)
        raise ConnectionError(error_msg) from last_exception
    
    def _create_indexes(self):
        """Create necessary indexes for the database."""
        try:
            # Users collection indexes
            self.db.users.create_index([("user_id", 1)], unique=True)
            
            # Confessions collection indexes
            self.db.confessions.create_index([("user_id", 1)])
            self.db.confessions.create_index([("status", 1)])
            self.db.confessions.create_index([("created_at", 1)])
            
            # Comments collection indexes
            self.db.comments.create_index([("confession_id", 1)])
            self.db.comments.create_index([("confession_id", 1), ("roll_no", 1)])
            self.db.comments.create_index([("parent_comment_id", 1)])
            self.db.comments.create_index([("user_id", 1)])
            self.db.comments.create_index([("created_at", 1)])
            
            logger.info("✅ Database indexes created successfully!")
        except Exception as e:
            logger.error(f"❌ Error creating database indexes: {e}")
            # Don't raise here, as the app might still work without indexes
            pass
    
    def get_collection(self, collection_name: str):
        """Get a reference to a MongoDB collection."""
        return self.db[collection_name]
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by Telegram user ID."""
        try:
            collection = self.get_collection('users')
            return collection.find_one({'user_id': user_id})
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            raise
    
    async def create_user(self, user_data: Dict) -> Optional[Dict]:
        """Create a new user."""
        try:
            collection = self.get_collection('users')
            result = collection.insert_one(user_data)
            return collection.find_one({"_id": result.inserted_id})
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    async def update_user_bio(self, user_id: int, bio: str) -> bool:
        """Update user's bio."""
        try:
            collection = self.get_collection('users')
            result = collection.update_one(
                {'user_id': user_id}, 
                {"$set": {'bio': bio}},
                upsert=True
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            logger.error(f"Error updating bio for user {user_id}: {e}")
            raise
    
    # Confession related methods
    async def create_confession(self, confession_data: Dict) -> Optional[Dict]:
        """Create a new confession."""
        try:
            collection = self.get_collection('confessions')
            result = collection.insert_one(confession_data)
            return collection.find_one({"_id": result.inserted_id})
        except Exception as e:
            logger.error(f"Error creating confession: {e}")
            raise
    
    async def get_pending_confessions(self) -> List[Dict]:
        """Get all pending confessions."""
        try:
            collection = self.get_collection('confessions')
            return list(collection.find({'status': 'pending'}))
        except Exception as e:
            logger.error(f"Error getting pending confessions: {e}")
            raise
    
    async def update_confession_status(self, confession_id: str, status: str, channel_msg_id: int = None) -> bool:
        """Update confession status and optionally set channel message ID."""
        try:
            collection = self.get_collection('confessions')
            update_data = {'status': status}
            if channel_msg_id is not None:
                update_data['channel_msg_id'] = channel_msg_id
            
            from bson.objectid import ObjectId
            result = collection.update_one(
                {'_id': ObjectId(confession_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating confession {confession_id}: {e}")
    
    # Comment related methods
    async def add_comment(self, comment_data: Dict) -> Optional[Dict]:
        """Add a comment to a confession."""
        try:
            collection = self.get_collection('comments')
            result = collection.insert_one(comment_data)
            return collection.find_one({"_id": result.inserted_id})
        except Exception as e:
            logger.error(f"Error adding comment: {e}")
            raise
    
    async def get_comments(self, confession_id: str) -> List[Dict]:
        """Get all comments for a confession."""
        try:
            collection = self.get_collection('comments')
            from bson.objectid import ObjectId
            return list(collection.find({'confession_id': ObjectId(confession_id)}).sort('created_at', 1))
        except Exception as e:
            logger.error(f"Error getting comments for confession {confession_id}: {e}")
            raise
    
    # Admin methods
    async def get_stats(self) -> Dict[str, int]:
        """Get statistics about confessions."""
        try:
            collection = self.get_collection('confessions')
            total = await collection.count_documents({})
            pending = await collection.count_documents({'status': 'pending'})
            
            return {
                'total': total,
                'pending': pending,
                'approved': total - pending
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            raise
            
    async def get_user_confessions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get confessions made by a specific user."""
        try:
            collection = self.get_collection('confessions')
            return list(collection.find(
                {'user_id': user_id},
                sort=[('created_at', -1)],
                limit=limit
            ))
        except Exception as e:
            logger.error(f"Error getting confessions for user {user_id}: {e}")
            return []
            
    async def get_user_comments(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get comments made by a specific user."""
        try:
            collection = self.get_collection('comments')
            return list(collection.find(
                {'user_id': user_id},
                sort=[('created_at', -1)],
                limit=limit
            ))
        except Exception as e:
            logger.error(f"Error getting comments for user {user_id}: {e}")
            return []
            
    async def update_user_emoji(self, user_id: int, emoji: str) -> bool:
        """Update user's profile emoji."""
        try:
            collection = self.get_collection('users')
            result = collection.update_one(
                {'user_id': user_id},
                {'$set': {'emoji': emoji}},
                upsert=True
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            logger.error(f"Error updating emoji for user {user_id}: {e}")
            return False

# Singleton instance
db = Database()
