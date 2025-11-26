from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/add-magnet', methods=['POST'])
def add_magnet_to_seedr():
    data = request.json
    token = data.get('token')
    magnet_link = data.get('magnet')

    if not token or not magnet_link:
        return jsonify({"success": False, "error": "Missing token or magnet"}), 400

    print(f"--- STARTING ATTEMPT FOR {token[:5]}... ---")

    # --- METHOD 1: The "Kodi" Method (Resource PHP) ---
    # This is how the Official Kodi Addon works.
    print("Trying Method 1 (Kodi Resource)...")
    url_1 = "https://www.seedr.cc/oauth_test/resource.php"
    payload_1 = {
        "access_token": token,
        "func": "add_torrent",
        "torrent_magnet": magnet_link
    }
    try:
        resp = requests.post(url_1, data=payload_1)
        if resp.status_code == 200 and "result" in resp.text:
            return jsonify({"success": True, "method": "1", "response": resp.json()})
    except Exception as e:
        print(f"Method 1 Error: {e}")


    # --- METHOD 2: The "REST" Method (Bearer Token) ---
    # This is how modern apps work.
    print("Trying Method 2 (REST Bearer)...")
    url_2 = "https://www.seedr.cc/rest/transfer/magnet"
    headers_2 = {"Authorization": f"Bearer {token}"}
    payload_2 = {"magnet": magnet_link}
    try:
        resp = requests.post(url_2, data=payload_2, headers=headers_2)
        if resp.status_code == 200:
             return jsonify({"success": True, "method": "2", "response": resp.json()})
    except Exception as e:
        print(f"Method 2 Error: {e}")


    # --- METHOD 3: The "API" Method (Mixed) ---
    # Fallback for older accounts.
    print("Trying Method 3 (API Folder)...")
    url_3 = "https://www.seedr.cc/api/folder/magnet/add"
    payload_3 = {
        "access_token": token,
        "magnet": magnet_link,
        "folder_id": 0
    }
    try:
        resp = requests.post(url_3, data=payload_3)
        if resp.status_code == 200:
             return jsonify({"success": True, "method": "3", "response": resp.json()})
    except Exception as e:
        print(f"Method 3 Error: {e}")

    # --- FAILURE ---
    return jsonify({
        "success": False, 
        "error": "All methods failed. Check token validity.",
        "last_status": resp.status_code if 'resp' in locals() else "Unknown"
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
