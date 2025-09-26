import os
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, OperationFailure
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI')
if not MONGODB_URI:
    print("Error: MONGODB_URI not found in environment variables")
    sys.exit(1)

# Add retryWrites and w=majority to the connection string if not present
if 'retryWrites' not in MONGODB_URI:
    MONGODB_URI += '&retryWrites=true&w=majority' if '?' in MONGODB_URI else '?retryWrites=true&w=majority'

DB_NAME = "confession_bot"

# Initialize MongoDB client with error handling
try:
    # Test the connection
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)  # 5 second timeout
    client.server_info()  # Will raise an exception if connection fails
    db = client[DB_NAME]
    print("✅ Successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
    print(f"Connection string: {MONGODB_URI.split('@')[-1] if '@' in MONGODB_URI else MONGODB_URI}")
    print("Please check your MONGODB_URI in the .env file and ensure your IP is whitelisted in MongoDB Atlas.")
    sys.exit(1)

# Collections
USERS_COLLECTION = db.users
CONFESSIONS_COLLECTION = db.confessions
COMMENTS_COLLECTION = db.comments

def init_db():
    """Initialize database indexes."""
    try:
        # Users collection indexes
        USERS_COLLECTION.create_index([("user_id", ASCENDING)], unique=True)
        
        # Confessions collection indexes
        CONFESSIONS_COLLECTION.create_index([("user_id", ASCENDING)])
        CONFESSIONS_COLLECTION.create_index([("status", ASCENDING)])
        CONFESSIONS_COLLECTION.create_index([("created_at", ASCENDING)])
        
        # Comments collection indexes
        COMMENTS_COLLECTION.create_index([("confession_id", ASCENDING)])
        COMMENTS_COLLECTION.create_index([("user_id", ASCENDING)])
        COMMENTS_COLLECTION.create_index([("created_at", ASCENDING)])
        
        print("✅ Database indexes created successfully!")
    except Exception as e:
        print(f"❌ Error creating database indexes: {e}")
        # Don't exit here, as the app might still work without indexes
        pass

class User:
    @staticmethod
    def get_user(user_id: int) -> Optional[Dict]:
        """Get user by Telegram user ID."""
        return USERS_COLLECTION.find_one({"user_id": user_id})

    @staticmethod
    def create_user(user_data: Dict) -> Dict:
        """Create a new user."""
        user_data["created_at"] = datetime.utcnow()
        user_data["updated_at"] = datetime.utcnow()
        result = USERS_COLLECTION.insert_one(user_data)
        return USERS_COLLECTION.find_one({"_id": result.inserted_id})

    @staticmethod
    def update_user_bio(user_id: int, bio: str) -> bool:
        """Update user's bio."""
        result = USERS_COLLECTION.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "bio": bio,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0

class Confession:
    @staticmethod
    def create_confession(confession_data: Dict) -> Dict:
        """Create a new confession."""
        confession_data["status"] = "pending"
        confession_data["created_at"] = datetime.utcnow()
        confession_data["updated_at"] = datetime.utcnow()
        result = CONFESSIONS_COLLECTION.insert_one(confession_data)
        return CONFESSIONS_COLLECTION.find_one({"_id": result.inserted_id})

    @staticmethod
    def get_pending_confessions() -> List[Dict]:
        """Get all pending confessions."""
        return list(CONFESSIONS_COLLECTION.find({"status": "pending"}))

    @staticmethod
    def update_confession_status(confession_id: str, status: str, channel_msg_id: int = None) -> bool:
        """Update confession status and optionally set channel message ID."""
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        if channel_msg_id is not None:
            update_data["channel_msg_id"] = channel_msg_id
            
        result = CONFESSIONS_COLLECTION.update_one(
            {"_id": confession_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

class Comment:
    @staticmethod
    def add_comment(comment_data: Dict) -> Dict:
        """Add a comment to a confession."""
        comment_data["created_at"] = datetime.utcnow()
        comment_data["updated_at"] = datetime.utcnow()
        result = COMMENTS_COLLECTION.insert_one(comment_data)
        return COMMENTS_COLLECTION.find_one({"_id": result.inserted_id})

    @staticmethod
    def get_comments(confession_id: str) -> List[Dict]:
        """Get all comments for a confession."""
        return list(COMMENTS_COLLECTION.find({"confession_id": confession_id}).sort("created_at", 1))
