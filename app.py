from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return "Seedr Bridge Active."

# --- AUTH ENDPOINTS ---
@app.route('/auth/code', methods=['GET'])
def get_code():
    url = "https://www.seedr.cc/oauth_device/create"
    params = {"client_id": "seedr_xbmc"}
    try:
        resp = requests.get(url, params=params)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/auth/token', methods=['GET'])
def get_token():
    device_code = request.args.get('device_code')
    url = "https://www.seedr.cc/oauth_device/token"
    params = {
        "client_id": "seedr_xbmc",
        "grant_type": "device_token",
        "device_code": device_code
    }
    try:
        resp = requests.get(url, params=params)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        resp = requests.post(url, data=payload)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)})

# --- 2. LIST FILES (Fixed Kodi Method) ---
@app.route('/list-files', methods=['POST'])
def list_files():
    data = request.json
    token = data.get('token')
    folder_id = data.get('folder_id', "0")
    
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # We go BACK to the endpoint that works for your token
    url = "https://www.seedr.cc/oauth_test/resource.php"
    
    # We add 'content_type' which is required by some versions of this API
    payload = {
        "access_token": token,
        "func": "get_folder",
        "folder_id": str(folder_id),
        "content_type": "video" 
    }
    
    try:
        print(f"Opening folder {folder_id} via Kodi Resource...")
        resp = requests.post(url, data=payload)
        
        # If empty response (server error), try without content_type
        if not resp.text:
            print("Retrying without content_type...")
            del payload['content_type']
            resp = requests.post(url, data=payload)

        return jsonify(resp.json())
    except Exception as e:
        # Return the raw text if JSON fails, so we can see the error
        return jsonify({"error": str(e), "raw_response": resp.text if 'resp' in locals() else "No response"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
