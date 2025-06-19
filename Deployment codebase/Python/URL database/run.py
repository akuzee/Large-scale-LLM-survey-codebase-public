from URL_database import app

if __name__ == '__main__':
    # Run on port 5001 to avoid conflict with AirPlay on macOS
    app.run(host='0.0.0.0', port=5001, debug=True) 