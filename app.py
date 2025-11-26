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

    # 1. Setup headers for the "seedr_xbmc" client (Official Kodi App)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Seedr Kodi/1.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # 2. Use the Official API Endpoint for Devices
    url = "https://www.seedr.cc/api/folder/magnet/add"
    
    # 3. Payload
    payload = {
        "torrent_magnet": magnet_link,
        "folder_id": 0  # 0 means root folder
    }

    print(f"Adding magnet with token: {token[:5]}...")
    
    # 4. Send Request
    response = requests.post(url, data=payload, headers=headers)
    
    # 5. Return Result
    return jsonify({
        "status_code": response.status_code,
        "seedr_response": response.json() if response.text else "No content"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
