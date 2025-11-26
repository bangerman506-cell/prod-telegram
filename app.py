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

    # HEADERS
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Seedr Kodi/1.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # API URL
    url = "https://www.seedr.cc/api/folder/magnet/add"
    
    # PAYLOAD (Fixed parameter name)
    payload = {
        "magnet": magnet_link,  # CHANGED FROM 'torrent_magnet' TO 'magnet'
        "folder_id": 0
    }

    print(f"Adding magnet...")
    
    # REQUEST
    response = requests.post(url, data=payload, headers=headers)
    
    # RETURN
    return jsonify({
        "status_code": response.status_code,
        "seedr_response": response.json() if response.text else "No content"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
