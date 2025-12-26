import os
import threading
import asyncio
import requests
import queue
import uuid
import time
import re
from io import IOBase
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.raw.functions.messages import CheckChatInvite

app = Flask(__name__)

# --- CONFIGURATION ---
API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")

# Headers for Seedr
HEADERS_STREAM = {
    "User-Agent": "Seedr Android/1.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

# --- 1. SMART STREAMER (IOBase Inheritance - Kept as is) ---
class SmartStream(IOBase):
    def __init__(self, url, name):
        super().__init__()
        self.url = url
        self.name = name
        self.mode = 'rb'
        self.total_size = 0
        self.current_pos = 0
        self._closed = False
        
        print(f"STREAM: Connecting to {url[:40]}...")
        try:
            head = requests.head(url, allow_redirects=True, timeout=10, headers=HEADERS_STREAM)
            self.total_size = int(head.headers.get('content-length', 0))
            print(f"STREAM: Size {self.total_size}")
        except:
            pass

        self.response = requests.get(url, stream=True, timeout=30, headers=HEADERS_STREAM)
        self.raw = self.response.raw
        self.raw.decode_content = True

    def read(self, size=-1):
        if self._closed: raise ValueError("I/O closed")
        data = self.raw.read(size)
        if data: self.current_pos += len(data)
        return data
    
    def seek(self, offset, whence=0):
        if whence == 0: self.current_pos = offset
        elif whence == 1: self.current_pos += offset
        elif whence == 2: self.current_pos = self.total_size + offset
        return self.current_pos
    
    def tell(self): return self.current_pos
    def close(self):
        if not self._closed:
            self._closed = True
            if hasattr(self, 'response'): self.response.close()
    def fileno(self): return None

# --- 2. ASYNC WORKER LOGIC ---
async def process_job(data):
    file_url = data['url']
    chat_target = data['chat_id']
    caption = data['caption']
    filename = data.get('filename', 'video.mp4')

    async with Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir="/tmp") as app:
        print("WORKER: Bot connected!")
        
        target_id = None

        # --- LOGIC: RESOLVE PEER VIA CHECK_INVITE ---
        # If input is a link like https://t.me/+AbCd123...
        if "t.me/+" in str(chat_target) or "joinchat" in str(chat_target):
            try:
                # Extract the hash (the part after +)
                invite_hash = chat_target.split("+")[-1].strip()
                if "joinchat/" in chat_target:
                    invite_hash = chat_target.split("joinchat/")[-1].strip()
                
                print(f"WORKER: Checking Invite Hash: {invite_hash}")
                
                # This RAW function updates Pyrogram's internal peer cache
                # It does NOT join the chat (bots can't), but it learns the Access Hash
                invite_info = await app.invoke(CheckChatInvite(hash=invite_hash))
                
                # Extract Chat ID from the raw result
                # invite_info.chat is a 'Chat' or 'Channel' raw object
                target_id = int(f"-100{invite_info.chat.id}")
                print(f"WORKER: Resolved via Link to ID: {target_id}")
                
            except Exception as e:
                print(f"WORKER WARNING: CheckChatInvite failed: {e}")
                # Fallback: Maybe it's a public link or username
        
        # If not resolved yet, try standard get_chat
        if not target_id:
            try:
                # Try as int if possible
                try: peer = int(chat_target)
                except: peer = chat_target
                
                chat = await app.get_chat(peer)
                target_id = chat.id
                print(f"WORKER: Resolved via get_chat: {target_id}")
            except Exception as e:
                print(f"WORKER ERROR: Could not resolve peer. Error: {e}")
                raise e

        # --- UPLOAD ---
        with SmartStream(file_url, filename) as stream:
            if stream.total_size == 0:
                raise Exception("File size 0. Link expired.")
            
            print(f"WORKER: Streaming to {target_id}...")
            msg = await app.send_video(
                chat_id=target_id,
                video=stream,
                caption=caption,
                file_name=filename,
                supports_streaming=True,
                progress=lambda c, t: print(f"Up: {c/1024/1024:.1f}MB") if c % (20*1024*1024) == 0 else None
            )
            
            # Return Data for n8n
            clean_id = str(msg.chat.id).replace('-100', '')
            return {
                "message_id": msg.id,
                "chat_id": msg.chat.id,
                "file_id": msg.video.file_id,  # Useful for reposting!
                "link": f"https://t.me/c/{clean_id}/{msg.id}"
            }

# --- 3. QUEUE PROCESSOR ---
JOB_QUEUE = queue.Queue()
JOBS = {} 

def worker_thread():
    print("SYSTEM: Queue Worker Started")
    # New Loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        try:
            job_id, data = JOB_QUEUE.get()
            print(f"WORKER: Processing {job_id}")
            JOBS[job_id]['status'] = 'processing'
            
            # Run the async logic in this loop
            result = loop.run_until_complete(process_job(data))
            
            JOBS[job_id]['status'] = 'done'
            JOBS[job_id]['result'] = result
            print("WORKER: Job Done!")
        except Exception as e:
            print(f"WORKER ERROR: {e}")
            if 'job_id' in locals():
                JOBS[job_id]['status'] = 'failed'
                JOBS[job_id]['error'] = str(e)
        finally:
            if 'job_id' in locals(): JOB_QUEUE.task_done()

# Start Worker Immediately
threading.Thread(target=worker_thread, daemon=True).start()

# --- ROUTES ---
@app.route('/')
def home(): return "Ready"

@app.route('/upload-telegram', methods=['POST'])
def upload_telegram():
    data = request.json
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {'status': 'queued', 'submitted_at': time.time()}
    JOB_QUEUE.put((job_id, data))
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    return jsonify(JOBS.get(job_id, {"status": "not_found"}))

# Seedr Routes (Kept minimal as they work)
@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    try:
        return jsonify(requests.post("https://www.seedr.cc/oauth_test/resource.php?json=1", data={"access_token": request.json.get('token'), "func": "add_torrent", "torrent_magnet": request.json.get('magnet')}).json())
    except: return jsonify({})

@app.route('/list-files', methods=['POST'])
def list_files():
    # Android Method
    t = request.json.get('token')
    fid = str(request.json.get('folder_id', "0"))
    url = "https://www.seedr.cc/api/folder" if fid == "0" else f"https://www.seedr.cc/api/folder/{fid}"
    try:
        return jsonify(requests.get(url, params={"access_token": t}, headers=HEADERS_STREAM).json())
    except: return jsonify({})

@app.route('/get-link', methods=['POST'])
def get_link():
    try:
        return jsonify(requests.post("https://www.seedr.cc/oauth_test/resource.php?json=1", data={"access_token": request.json.get('token'), "func": "fetch_file", "folder_file_id": str(request.json.get('file_id'))}).json())
    except: return jsonify({})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
