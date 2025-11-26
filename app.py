from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# SEEDR ENDPOINTS
LOGIN_URL = "https://www.seedr.cc/rest/login"
ADD_MAGNET_URL = "https://www.seedr.cc/rest/transfer/magnet"

# FAKE BROWSER HEADERS (The Magic Fix)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.seedr.cc",
    "Referer": "https://www.seedr.cc/files"
}

@app.route('/add-magnet', methods=['POST'])
def add_magnet_to_seedr():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    magnet_link = data.get('magnet')

    if not username or not password or not magnet_link:
        return jsonify({"success": False, "error": "Missing inputs"}), 400

    # Start a Session
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Step 1: Login
    login_data = {
        'username': username,
        'password': password,
        'type': 'login'
    }
    
    print(f"Attempting login for {username}...")
    login_resp = session.post(LOGIN_URL, data=login_data)
    
    # Check login success
    try:
        login_json = login_resp.json()
    except:
        return jsonify({"success": False, "error": "Login returned non-JSON", "details": login_resp.text}), 401

    if login_resp.status_code != 200 or login_json.get('result') is not True:
         return jsonify({
            "success": False, 
            "error": "Login Failed", 
            "details": login_json
        }), 401

    print("Login Success! Adding magnet...")

    # Step 2: Add Magnet
    magnet_data = {'magnet': magnet_link}
    add_resp = session.post(ADD_MAGNET_URL, data=magnet_data)

    return jsonify(add_resp.json())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
