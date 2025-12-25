import os
import threading
import asyncio
import requests
import sys
from flask import Flask, request, jsonify
from pyrogram import Client

app = Flask(__name__)

# --- CONFIGURATION ---
# Check if keys exist and print status (MASKED)
API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")

print("--- SYSTEM STARTUP CHECK ---")
print(f"API_ID Present: {bool(API_ID)}")
print(f"API_HASH Present: {bool(API_HASH)}")
print(f"BOT_TOKEN Present: {bool(BOT_TOKEN)}")
if BOT_TOKEN:
    print(f"Token starts with: {BOT_TOKEN[:5]}...")

HEADERS = {
    "User-Agent": "Seedr Android/1.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

# --- STREAM CLASS (With Logging) ---
class HTTPStream:
    def __init__(self, url, filename):
        self.url = url
        self.name = filename
        print(f"DEBUG: Initiating connection to Seedr for {filename}...")
        try:
            self.response = requests.get(url, stream=True, timeout=10)
            self.response.raise_for_status()
            print(f"DEBUG: Connection established! Status Code: {self.response.status_code}")
            self.raw = self.response.raw
        except Exception as e:
            print(f"DEBUG: Failed to connect to Seedr: {e}")
            raise e

    def read(self, chunk_size):
        # We won't log every read (too spammy), but if it hangs, we know it's here
        return self.raw.read(chunk_size)

# --- WORKER ---
def upload_worker(file_url, chat_id, caption):
    print(f"WORKER: Thread started for chat {chat_id}")
    
    # 1. Create Loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("WORKER: Event loop created")

    # 2. Define Upload Task
    async def perform_upload():
        print("WORKER: Initializing Pyrogram Client...")
        try:
            async with Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True) as app:
                print("WORKER: Bot Connected to Telegram!")
                
                print("WORKER: Preparing Stream...")
                stream = HTTPStream(file_url, "video.mp4")
                
                print("WORKER: Starting upload... (This takes time)")
                await app.send_video(
                    chat_id=int(chat_id),
                    video=stream,
                    caption=caption,
                    supports_streaming=True,
                    progress=lambda current, total: print(f"Upload Progress: {current/1024/1024:.1f} MB") if current % (5*1024*1024) == 0 else None
                )
                print("WORKER: Upload Success!")
        except Exception as e:
            print(f"WORKER ERROR: {e}")
            import traceback
            traceback.print_exc()

    # 3. Run
    try:
        loop.run_until_complete(perform_upload())
    except Exception as e:
        print(f"LOOP ERROR: {e}")
    finally:
        loop.close()
        print("WORKER: Cleanup done")

# --- ROUTES ---
@app.route('/')
def home():
    return "Seedr Bridge Active."

@app.route('/upload-telegram', methods=['POST'])
def upload_telegram():
    data = request.json
    file_url = data.get('url')
    chat_id = data.get('chat_id')
    caption = data.get('caption', "Uploaded via Automation")
    
    print(f"REQUEST: Received upload request for {file_url[:20]}...")

    if not file_url or not chat_id:
        return jsonify({"error": "Missing params"}), 400

    thread = threading.Thread(target=upload_worker, args=(file_url, chat_id, caption))
    thread.start()
    
    return jsonify({"status": "Upload started"})

# --- EXISTING ROUTES (Add Magnet, List Files, Get Link) ---
# (Paste your previous Add/List/Get-Link routes here if you want, 
# or just test the upload part for now. 
# For simplicity, I assume you kept the previous routes below this line)
# ... [PASTE PREVIOUS ROUTES HERE IF NEEDED, OR USE FILE AS IS FOR UPLOAD TEST] ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
