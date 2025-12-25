import os
import threading
import asyncio
import requests
import time
from flask import Flask, request, jsonify
from pyrogram import Client

app = Flask(__name__)

# --- CONFIGURATION ---
API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")

# Ensure API_ID is an integer
if API_ID:
    try:
        API_ID = int(API_ID)
    except:
        print("Error: API_ID must be an integer")

HEADERS = {
    "User-Agent": "Seedr Android/1.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

# --- WORKER: UPLOAD ENGINE ---
def upload_worker(file_url, chat_id, caption):
    print(f"WORKER: Starting upload to {chat_id}")
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def perform_upload():
        async with Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True) as app:
            print("WORKER: Bot connected!")
            
            try:
                # 1. Connect to Seedr Stream
                print("WORKER: Connecting to file stream...")
                # We use stream=True to not download it to memory
                response = requests.get(file_url, stream=True, timeout=30)
                
                # 2. THE FIX: Monkey Patch the Raw Object
                # Instead of a custom class, we use the raw socket and label it
                stream = response.raw
                stream.name = "video.mp4" # Pyrogram needs a filename
                stream.mode = "rb"        # Pyrogram needs to know it's binary
                stream.decode_content = True 

                print("WORKER: Stream Ready. Sending to Telegram...")
                
                # 3. Upload
                await app.send_video(
                    chat_id=int(chat_id),
                    video=stream,
                    caption=caption,
                    supports_streaming=True,
                    progress=lambda current, total: print(f"Progress: {current/1024/1024:.2f} MB") if current % (5*1024*1024) == 0 else None
                )
                print("WORKER: Upload Success!")
                
            except Exception as e:
                print(f"WORKER ERROR: {e}")
                import traceback
                traceback.print_exc()

    # Run the async loop
    try:
        loop.run_until_complete(perform_upload())
    except Exception as e:
        print(f"LOOP ERROR: {e}")
    finally:
        loop.close()

# --- ROUTES ---

@app.route('/')
def home():
    return "Seedr-Telegram Bridge Active."

@app.route('/upload-telegram', methods=['POST'])
def upload_telegram():
    data = request.json
    file_url = data.get('url')
    chat_id = data.get('chat_id')
    caption = data.get('caption', "Uploaded via Automation")
    
    if not file_url or not chat_id:
        return jsonify({"error": "Missing params"}), 400

    # Start background process
    thread = threading.Thread(target=upload_worker, args=(file_url, chat_id, caption))
    thread.start()
    
    return jsonify({"status": "Upload started"})

# --- EXISTING SEEDR ROUTES (UNCHANGED) ---

@app.route('/auth/code', methods=['GET'])
def get_code():
    try:
        resp = requests.get("https://www.seedr.cc/oauth_device/create", params={"client_id": "seedr_xbmc"})
        return jsonify(resp.json())
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/auth/token', methods=['GET'])
def get_token():
    try:
        resp = requests.get("https://www.seedr.cc/oauth_device/token", params={"client_id": "seedr_xbmc", "grant_type": "device_token", "device_code": request.args.get('device_code')})
        return jsonify(resp.json())
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    try:
        resp = requests.post("https://www.seedr.cc/oauth_test/resource.php?json=1", data={"access_token": request.json.get('token'), "func": "add_torrent", "torrent_magnet": request.json.get('magnet')})
        return jsonify(resp.json())
    except Exception as e: return jsonify({"error": str(e)})

@app.route('/list-files', methods=['POST'])
def list_files():
    # Force Folder ID strategy
    data = request.json
    token = data.get('token')
    folder_id = data.get('folder_id', "0")
    
    # We use the brute force listing method that worked for you
    url = "https://www.seedr.cc/api/folder"
    params = {
        "access_token": token,
        "folder_id": str(folder_id),
        "id": str(folder_id),
        "folder": str(folder_id)
    }
    try:
        # User-Agent header is critical for listing
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = requests.get(url, params=params, headers=headers)
        return jsonify(resp.json())
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/get-link', methods=['POST'])
def get_link():
    try:
        resp = requests.post("https://www.seedr.cc/oauth_test/resource.php?json=1", data={"access_token": request.json.get('token'), "func": "fetch_file", "folder_file_id": str(request.json.get('file_id'))})
        return jsonify(resp.json())
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
