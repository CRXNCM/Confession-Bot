from database import db

def create_indexes():
    """Create necessary indexes for the reports collection."""
    try:
        # Create index for reporter_id
        db.get_collection('reports').create_index('reporter_id')
        
        # Create index for comment_id
        db.get_collection('reports').create_index('comment_id')
        
        # Create index for status
        db.get_collection('reports').create_index('status')
        
        # Create compound index for common queries
        db.get_collection('reports').create_index([
            ('status', 1),
            ('created_at', -1)
        ])
        
        print("Successfully created report indexes")
        return True
    except Exception as e:
        print(f"Error creating indexes: {e}")
        return False

if __name__ == "__main__":
    create_indexes()
