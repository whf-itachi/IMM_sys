from app.main import create_app
from app.config.app_config import HOST, PORT, DEBUG

app = create_app()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)