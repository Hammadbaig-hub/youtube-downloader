"""
create_admin.py — Run this once to create the first super-admin account.
Usage: python create_admin.py
"""

from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()

    existing = Admin.query.filter_by(username='admin').first()
    if existing:
        print("Admin already exists. Nothing changed.")
    else:
        admin = Admin(
            username      = 'admin',
            email         = 'admin@vidflow.com',
            password_hash = generate_password_hash('admin123'),
            is_super_admin = True,
        )
        db.session.add(admin)
        db.session.commit()
        print("=" * 40)
        print("Admin created successfully!")
        print("  URL:      http://localhost:5000/admin/login")
        print("  Username: admin")
        print("  Password: admin123")
        print("=" * 40)
        print("IMPORTANT: Change the password after first login!")
