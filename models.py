from datetime import datetime
from typing import Optional, List, Dict, Any
from pymongo import ASCENDING
from database import db  # Import the Database instance

# Collections
USERS_COLLECTION = db.get_collection('users')
CONFESSIONS_COLLECTION = db.get_collection('confessions')
COMMENTS_COLLECTION = db.get_collection('comments')

class User:
    @staticmethod
    def get_user(user_id: int) -> Optional[Dict]:
        """Get user by Telegram user ID."""
        user = USERS_COLLECTION.find_one({"user_id": user_id})
        if not user:
            return None
        # Ensure all fields exist
        user.setdefault('emoji', '👤')  # Default emoji
        user.setdefault('nickname', None)
        user.setdefault('bio', None)
        return user

    @staticmethod
    def get_or_create_user(user_data: Dict) -> Dict:
        """Get existing user or create a new one if not exists."""
        user = USERS_COLLECTION.find_one({"user_id": user_data["user_id"]})
        if not user:
            return User.create_user(user_data)
        return user

    @staticmethod
    def create_user(user_data: Dict) -> Dict:
        """Create a new user with default values."""
        now = datetime.utcnow()
        user_data.update({
            "emoji": user_data.get("emoji", "👤"),
            "nickname": user_data.get("nickname"),
            "bio": user_data.get("bio"),
            "created_at": now,
            "updated_at": now
        })
        result = USERS_COLLECTION.insert_one(user_data)
        return USERS_COLLECTION.find_one({"_id": result.inserted_id})

    @staticmethod
    def _update_user_field(user_id: int, field: str, value: Any) -> bool:
        """Generic method to update a user field."""
        result = USERS_COLLECTION.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    field: value,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    @classmethod
    def update_user_emoji(cls, user_id: int, emoji: str) -> bool:
        """Update user's profile emoji."""
        return cls._update_user_field(user_id, "emoji", emoji)

    @classmethod
    def update_user_nickname(cls, user_id: int, nickname: str) -> bool:
        """Update user's nickname."""
        # Limit nickname length
        if len(nickname) > 20:
            nickname = nickname[:20]
        return cls._update_user_field(user_id, "nickname", nickname)

    @classmethod
    def update_user_bio(cls, user_id: int, bio: str) -> bool:
        """Update user's bio."""
        # Limit bio length
        if len(bio) > 500:
            bio = bio[:500]
        return cls._update_user_field(user_id, "bio", bio)
    
    @classmethod
    def get_user_profile(cls, user_id: int) -> Dict:
        """Get user's profile information."""
        user = cls.get_user(user_id)
        if not user:
            return {
                "emoji": "👤",
                "nickname": "Anonymous",
                "bio": None,
                "confession_count": 0
            }
        
        # Get confession count
        confession_count = CONFESSIONS_COLLECTION.count_documents({
            "user_id": user_id,
            "status": "approved"
        })
        
        return {
            "emoji": user.get("emoji", "👤"),
            "nickname": user.get("nickname") or "Anonymous",
            "bio": user.get("bio"),
            "confession_count": confession_count
        }

class Confession:

    CATEGORIES = [
        "General",
        "Love",
        "Friendship",
        "Family",
        "Work",
        "School",
        "Confession",
        "Advice",
        "Rant",
        "Other"
    ]

    @staticmethod
    def get_categories() -> List[str]:
        """Get the list of available categories."""
        return Confession.CATEGORIES

    @staticmethod
    def is_valid_category(category: str) -> bool:
        """Check if a category is valid."""
        return category in Confession.CATEGORIES

    @staticmethod
    def create_confession(confession_data: Dict) -> Dict:
        """Create a new confession with category validation."""
        # Set default category if not provided
        if 'category' not in confession_data or not confession_data['category']:
            confession_data['category'] = "General"
        
        # Validate category
        if not Confession.is_valid_category(confession_data['category']):
            confession_data['category'] = "General"  # Default to General if invalid
            
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
        comment_data.setdefault("likes", 0)
        comment_data.setdefault("dislikes", 0)
        comment_data.setdefault("parent_comment_id", None)
        # Assign a sequential roll number per confession for top-level comments only
        if not comment_data.get("parent_comment_id"):
            last = COMMENTS_COLLECTION.find({"confession_id": comment_data["confession_id"], "parent_comment_id": None})\
                .sort("roll_no", -1).limit(1)
            last_roll = 0
            for doc in last:
                last_roll = doc.get("roll_no", 0)
            comment_data["roll_no"] = last_roll + 1
        result = COMMENTS_COLLECTION.insert_one(comment_data)
        return COMMENTS_COLLECTION.find_one({"_id": result.inserted_id})

    @staticmethod
    def get_comments(confession_id: str) -> List[Dict]:
        """Get all comments for a confession."""
        # Top-level comments only, ordered by roll number if present, else created_at
        cursor = COMMENTS_COLLECTION.find({
            "confession_id": confession_id,
            "parent_comment_id": None
        }).sort([("roll_no", 1), ("created_at", 1)])
        return list(cursor)

    @staticmethod
    def get_comment(comment_id: Any) -> Optional[Dict]:
        return COMMENTS_COLLECTION.find_one({"_id": comment_id})

    @staticmethod
    def like_comment(comment_id: Any) -> None:
        COMMENTS_COLLECTION.update_one({"_id": comment_id}, {"$inc": {"likes": 1}})

    @staticmethod
    def dislike_comment(comment_id: Any) -> None:
        COMMENTS_COLLECTION.update_one({"_id": comment_id}, {"$inc": {"dislikes": 1}})

    @staticmethod
    def add_reply(parent_comment_id: Any, reply_data: Dict) -> Dict:
        reply_data["parent_comment_id"] = parent_comment_id
        reply_data["created_at"] = datetime.utcnow()
        reply_data["updated_at"] = datetime.utcnow()
        reply_data.setdefault("likes", 0)
        reply_data.setdefault("dislikes", 0)
        result = COMMENTS_COLLECTION.insert_one(reply_data)
        return COMMENTS_COLLECTION.find_one({"_id": result.inserted_id})
