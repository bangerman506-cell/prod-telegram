from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- HELPER: KODI METHOD ---
def call_kodi_endpoint(token, func, extra_params={}):
    url = "https://www.seedr.cc/oauth_test/resource.php"
    payload = {
        "access_token": token,
        "func": func
    }
    payload.update(extra_params)
    
    try:
        resp = requests.post(url, data=payload)
        return resp.json()
    except Exception as e:
        return {"result": False, "error": str(e)}

@app.route('/')
def home():
    return "Seedr Bridge Active"

# --- 1. ADD MAGNET ---
@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    data = request.json
    token = data.get('token')
    magnet = data.get('magnet')
    
    if not token or not magnet:
        return jsonify({"error": "Missing params"}), 400
        
    # Use Method 1 (Kodi)
    response = call_kodi_endpoint(token, "add_torrent", {"torrent_magnet": magnet})
    return jsonify(response)

# --- 2. LIST FILES (NEW) ---
@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # Get Root Folder Structure
    response = call_kodi_endpoint(token, "get_folder", {"folder_id": "0"})
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
