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
