from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    google_id  = db.Column(db.String(100), unique=True, nullable=False)
    name       = db.Column(db.String(100))
    email      = db.Column(db.String(100), unique=True)
    avatar     = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    downloads  = db.relationship('Download', backref='user', lazy=True)


class Download(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title     = db.Column(db.String(200))
    platform  = db.Column(db.String(50), default='YouTube')
    quality   = db.Column(db.String(20))
    file_size = db.Column(db.String(20))
    date      = db.Column(db.DateTime, default=datetime.utcnow)


class Admin(UserMixin, db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(50), unique=True)
    email          = db.Column(db.String(100), unique=True)
    password_hash  = db.Column(db.String(200))
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    last_login     = db.Column(db.DateTime)


class SiteStats(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    date                = db.Column(db.Date, default=datetime.utcnow)
    total_downloads     = db.Column(db.Integer, default=0)
    total_users         = db.Column(db.Integer, default=0)
    youtube_downloads   = db.Column(db.Integer, default=0)
    instagram_downloads = db.Column(db.Integer, default=0)
    tiktok_downloads    = db.Column(db.Integer, default=0)
    facebook_downloads  = db.Column(db.Integer, default=0)
    twitter_downloads   = db.Column(db.Integer, default=0)
    vimeo_downloads     = db.Column(db.Integer, default=0)
