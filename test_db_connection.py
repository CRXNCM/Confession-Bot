   import pymongo
   from pymongo import MongoClient
   import os
   from dotenv import load_dotenv

   load_dotenv()

   MONGODB_URI = os.getenv('MONGODB_URI')
   print(f"Attempting to connect to: {MONGODB_URI.split('@')[-1].split('/')[0]}...")

   try:
       client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
       client.server_info()  # Force a connection test
       print("✅ Successfully connected to MongoDB!")
       print(f"Server version: {client.server_info()['version']}")
       print("Available databases:", client.list_database_names())
   except Exception as e:
       print(f"❌ Connection failed: {e}")