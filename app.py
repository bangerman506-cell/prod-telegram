from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- CONFIGURATION ---
# We act exactly like the Kodi plugin
HEADERS = {
    "User-Agent": "Seedr Kodi/1.0.3",
    "Content-Type": "application/x-www-form-urlencoded"
}

@app.route('/')
def home():
    return "Seedr Kodi Bridge Active"

# --- 1. ADD MAGNET ---
@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    data = request.json
    token = data.get('token')
    magnet = data.get('magnet')
    
    if not token or not magnet:
        return jsonify({"error": "Missing params"}), 400
        
    url = "https://www.seedr.cc/oauth_test/resource.php"
    payload = {
        "access_token": token,
        "func": "add_torrent",
        "torrent_magnet": magnet
    }
    
    try:
        # Uses Kodi Endpoint
        resp = requests.post(url, data=payload, headers=HEADERS)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"result": False, "error": str(e)})

# --- 2. LIST FILES (Corrected) ---
@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    token = data.get('token')
    folder_id = data.get('folder_id', "0")
    
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # STRATEGY: Use Standard API but with KODI HEADERS
    # This tricks Seedr into thinking the Kodi app is asking for the file list
    url = "https://www.seedr.cc/api/folder"
    
    payload = {
        "access_token": token,
        "folder_id": str(folder_id)
    }
    
    try:
        print(f"Listing folder {folder_id} as Kodi...")
        resp = requests.post(url, data=payload, headers=HEADERS)
        
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
