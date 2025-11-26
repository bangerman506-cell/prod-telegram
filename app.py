from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return "Seedr Bridge Active"

# --- 1. ADD MAGNET (Uses Kodi Method - PROVEN TO WORK) ---
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
        resp = requests.post(url, data=payload)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"result": False, "error": str(e)})

# --- 2. LIST FILES (Uses Standard API - BETTER FOR READING) ---
@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # We use the main API endpoint, passing token in BODY
    url = "https://www.seedr.cc/api/folder"
    payload = {
        "access_token": token,
        "folder_id": 0
    }
    
    try:
        print(f"Listing files for token {token[:5]}...")
        resp = requests.post(url, data=payload)
        
        # Check if response is valid JSON
        try:
            return jsonify(resp.json())
        except:
            # If Seedr sends back HTML error, show it
            print(f"Non-JSON Response: {resp.text}")
            return jsonify({"error": "Seedr returned invalid JSON", "raw_response": resp.text}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
