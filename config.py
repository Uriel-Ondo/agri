import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SRS_SERVER = os.getenv('SRS_SERVER')
    SRS_RTMP_PORT = int(os.getenv('SRS_RTMP_PORT'))
    SRS_HTTP_PORT = int(os.getenv('SRS_HTTP_PORT'))
    REDIS_HOST = os.getenv('REDIS_HOST')
    REDIS_PORT = int(os.getenv('REDIS_PORT'))
    REDIS_DB = int(os.getenv('REDIS_DB'))
    PUBLIC_DOMAIN = os.getenv('PUBLIC_DOMAIN')