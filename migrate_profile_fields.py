"""
Migration script to add profile fields to existing users.
Run this script to update your database schema.
"""
import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

def main():
    # Load environment variables
    load_dotenv()
    
    # Get MongoDB connection string
    MONGODB_URI = os.getenv('MONGODB_URI')
    if not MONGODB_URI:
        print("Error: MONGODB_URI not found in environment variables")
        sys.exit(1)
        
    # Add retryWrites and w=majority if not present
    if 'retryWrites' not in MONGODB_URI:
        MONGODB_URI += '&retryWrites=true&w=majority' if '?' in MONGODB_URI else '?retryWrites=true&w=majority'
    
    # Connect to MongoDB
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client.get_database("confession_bot")
        users = db.users
        
        print("✅ Successfully connected to MongoDB!")
        
        # Update all users to include the new fields if they don't exist
        result = users.update_many(
            {},
            {
                "$setOnInsert": {
                    "emoji": "👤",
                    "nickname": None,
                    "bio": None,
                    "created_at": None,
                    "updated_at": None
                }
            },
            upsert=False
        )
        
        print(f"✅ Updated {result.matched_count} user documents with default profile fields")
        
        # Set emoji for users who don't have it
        result = users.update_many(
            {"emoji": {"$exists": False}},
            {"$set": {"emoji": "👤"}}
        )
        print(f"✅ Set default emoji for {result.matched_count} users")
        
        # Set default nickname for users who don't have one
        result = users.update_many(
            {"nickname": {"$exists": False}},
            [
                {"$set": {"nickname": {"$concat": ["User ", {"$toString": "$user_id"}]}}}
            ]
        )
        print(f"✅ Set default nicknames for {result.matched_count} users")
        
        # Create indexes if they don't exist
        users.create_index("user_id", unique=True)
        print("✅ Created indexes")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
