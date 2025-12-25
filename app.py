from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- AUTH ENDPOINTS (Keep these for generating tokens) ---
@app.route('/auth/code', methods=['GET'])
def get_code():
    # ... (Keep existing logic or simplify)
    return jsonify({"message": "Use /auth/token with device_code"})

@app.route('/auth/token', methods=['GET'])
def get_token():
    # ... (Keep existing logic)
    return jsonify({"message": "Token generator"})

# --- MAIN BRIDGE ---

@app.route('/')
def home():
    return "Seedr Bridge Active."

# --- 1. ADD MAGNET (Updated to match your notes) ---
@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    data = request.json
    token = data.get('token')
    magnet = data.get('magnet')
    
    if not token or not magnet:
        return jsonify({"error": "Missing params"}), 400
        
    # URL from your notes
    url = "https://www.seedr.cc/oauth_test/resource.php?json=1"
    
    # HEADERS: authorization is Key!
    headers = {
        "User-Agent": "Seedr Kodi/1.0.3",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # BODY: action=add_magnet
    payload = {
        "action": "add_magnet",
        "magnet": magnet
    }
    
    try:
        resp = requests.post(url, data=payload, headers=headers)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)})

# --- 2. LIST FILES (Updated to match your notes) ---
@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    token = data.get('token')
    folder_id = data.get('folder_id', "0")
    
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # URL from your notes: /fs/folder/{id}/items
    url = f"https://www.seedr.cc/fs/folder/{folder_id}/items"
    
    # HEADERS: This is the magic part
    headers = {
        "User-Agent": "Seedr Kodi/1.0.3",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        print(f"Listing folder {folder_id} with Bearer Header...")
        resp = requests.get(url, headers=headers)
        
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
