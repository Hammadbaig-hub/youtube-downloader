import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "default"))

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )
