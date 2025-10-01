"""
Migration script to add category field to existing confessions.
Run this script once to update the database schema.
"""
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# Import database after path is set
from database import db

def update_confessions_schema():
    """Add category field to all existing confessions if it doesn't exist."""
    try:
        collection = db.get_collection('confessions')
        
        # Update all confessions that don't have a category field
        result = collection.update_many(
            {"category": {"$exists": False}},
            {"$set": {"category": "General"}}
        )
        
        print(f"✅ Updated {result.modified_count} confessions with default category.")
        
        # Create an index on the category field for better query performance
        collection.create_index("category")
        print("✅ Created index on 'category' field.")
        
    except Exception as e:
        print(f"❌ Error updating confessions: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    print("Starting database migration: Adding category to confessions...")
    load_dotenv()  # Load environment variables
    
    if update_confessions_schema():
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed. Please check the error messages above.")
