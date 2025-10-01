"""
Migration script to update the confessions collection to support multiple categories.
"""
import os
import sys
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

def migrate():
    """Run the migration."""
    # Get MongoDB connection string from environment or use default
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    db_name = os.getenv('MONGODB_DB', 'confession_bot')
    
    try:
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Get the confessions collection
        confessions: Collection = db['confessions']
        
        # Update all documents that have a 'category' field to use 'categories' array
        result = confessions.update_many(
            {"category": {"$exists": True}},
            [
                {
                    "$set": {
                        "categories": {"$cond": {
                            "if": {"$isArray": ["$category"]},
                            "then": "$category",
                            "else": ["$category"]
                        }}
                    }
                },
                {"$unset": "category"}
            ]
        )
        
        print(f"Successfully migrated {result.modified_count} confessions to support multiple categories.")
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}", file=sys.stderr)
        return False
    finally:
        client.close()

if __name__ == "__main__":
    if migrate():
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed!", file=sys.stderr)
        sys.exit(1)
