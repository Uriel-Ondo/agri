import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')
    SRS_SERVER = os.getenv('SRS_SERVER', 'localhost')
    SRS_RTMP_PORT = int(os.getenv('SRS_RTMP_PORT', 1935))
    SRS_HTTP_PORT = int(os.getenv('SRS_HTTP_PORT', 8080))
    
    REDIS_HOST = os.getenv('REDIS_HOST')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))