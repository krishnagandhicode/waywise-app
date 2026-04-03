import os

from backend.app import app


if __name__ == '__main__':
    run_host = os.getenv('FLASK_RUN_HOST', '127.0.0.1')
    run_port = int(os.getenv('PORT', os.getenv('FLASK_RUN_PORT', '5000')))
    debug_mode = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes', 'on')
    app.run(host=run_host, port=run_port, debug=debug_mode)
