import os
import threading
import asyncio
import requests
import queue
import uuid
import time
from io import IOBase
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import UserAlreadyParticipant, FloodWait, ChannelPrivate, ChatAdminRequired

app = Flask(__name__)

# --- CONFIGURATION ---
API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")

if API_ID:
    try:
        API_ID = int(API_ID)
    except:
        pass

HEADERS_STREAM = {
    "User-Agent": "Seedr Android/1.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

# --- 1. SMART STREAMER ---
class SmartStream(IOBase):
    def __init__(self, url, name):
        super().__init__()
        self.url = url
        self.name = name
        self.mode = 'rb'
        print(f"STREAM: Connecting to {url[:40]}...", flush=True)
        try:
            head = requests.head(url, allow_redirects=True, timeout=10, headers=HEADERS_STREAM)
            self.total_size = int(head.headers.get('content-length', 0))
            print(f"STREAM: Size {self.total_size} bytes ({self.total_size/1024/1024:.1f}MB)", flush=True)
        except Exception as e:
            print(f"STREAM WARNING: {e}", flush=True)
            self.total_size = 0
        
        self.response = requests.get(url, stream=True, timeout=30, headers=HEADERS_STREAM)
        self.raw = self.response.raw
        self.raw.decode_content = True
        self.current_pos = 0
        self._closed = False
    
    def read(self, size=-1):
        if self._closed: 
            raise ValueError("I/O closed")
        data = self.raw.read(size)
        if data: 
            self.current_pos += len(data)
        return data
    
    def seek(self, offset, whence=0):
        if whence == 0: 
            self.current_pos = offset
        elif whence == 1: 
            self.current_pos += offset
        elif whence == 2: 
            self.current_pos = self.total_size + offset
        return self.current_pos
    
    def tell(self): 
        return self.current_pos
    
    def close(self):
        if not self._closed:
            self._closed = True
            if hasattr(self, 'response'): 
                self.response.close()
    
    def fileno(self): 
        return None

# --- 2. ASYNC UPLOAD LOGIC (SMART STRATEGY WITH INVITE LINK SUPPORT) ---
async def perform_upload(file_url, chat_target, caption, filename):
    """
    Smart Upload Strategy:
    - Invite links (https://t.me/+...) for private channels → Forces access refresh
    - Usernames (@channel) for public channels → Always resolvable
    - Numeric IDs as fallback → Uses message fetch to refresh access
    """
    async with Client(
        "bot_session", 
        api_id=API_ID, 
        api_hash=API_HASH, 
        bot_token=BOT_TOKEN, 
        workdir="/tmp"
    ) as app:
        print("WORKER: Bot connected!", flush=True)
        
        final_chat_id = None
        chat_str = str(chat_target).strip()
        
        # --- STRATEGY 1: INVITE LINK (PRIVATE CHANNELS) ---
        if "t.me/+" in chat_str or "joinchat" in chat_str:
            print(f"WORKER: 🔗 Invite link detected", flush=True)
            try:
                # Extract hash from link
                if "t.me/+" in chat_str:
                    invite_hash = chat_str.split("t.me/+")[1].split("?")[0].split("/")[0]
                elif "joinchat/" in chat_str:
                    invite_hash = chat_str.split("joinchat/")[1].split("?")[0].split("/")[0]
                
                print(f"WORKER: Extracted hash: {invite_hash[:10]}...", flush=True)
                
                # Use join_chat to refresh access (even if already member)
                try:
                    chat = await app.join_chat(chat_str)
                    final_chat_id = chat.id
                    print(f"WORKER: ✅ Joined/Refreshed → ID: {final_chat_id}", flush=True)
                    
                except UserAlreadyParticipant:
                    # Already in channel, fetch via message history
                    print("WORKER: Already in channel, fetching ID via messages...", flush=True)
                    try:
                        async for msg in app.get_chat_history(chat_str, limit=1):
                            final_chat_id = msg.chat.id
                            print(f"WORKER: ✅ Got ID from message: {final_chat_id}", flush=True)
                            break
                    except Exception as e2:
                        print(f"WORKER WARNING: Message fetch failed: {e2}", flush=True)
                        # Last resort: try get_chat
                        try:
                            chat = await app.get_chat(chat_str)
                            final_chat_id = chat.id
                            print(f"WORKER: ✅ Got ID from get_chat: {final_chat_id}", flush=True)
                        except Exception as e3:
                            raise Exception(f"Cannot resolve invite link: {e3}")
                
                except FloodWait as e:
                    print(f"WORKER: ⏳ FloodWait {e.value}s, waiting...", flush=True)
                    await asyncio.sleep(e.value)
                    chat = await app.join_chat(chat_str)
                    final_chat_id = chat.id
                    
                except Exception as e:
                    print(f"WORKER ERROR: Invite link failed: {e}", flush=True)
                    raise Exception(f"Cannot access channel via invite link: {e}")
        
        # --- STRATEGY 2: PUBLIC USERNAME ---
        elif chat_str.startswith("@"):
            print(f"WORKER: 👤 Public username: {chat_str}", flush=True)
            try:
                chat = await app.get_chat(chat_str)
                final_chat_id = chat.id
                print(f"WORKER: ✅ Resolved to ID: {final_chat_id}", flush=True)
            except Exception as e:
                raise Exception(f"Username resolution failed: {e}")
        
        # --- STRATEGY 3: NUMERIC ID (FALLBACK WITH REFRESH) ---
        elif chat_str.lstrip("-").isdigit():
            final_chat_id = int(chat_str)
            print(f"WORKER: 🔢 Using numeric ID: {final_chat_id}", flush=True)
            
            # Try to refresh access hash via message fetch
            try:
                print("WORKER: Refreshing access hash via message fetch...", flush=True)
                async for msg in app.get_chat_history(final_chat_id, limit=1):
                    print(f"WORKER: ✅ Access refreshed via message {msg.id}", flush=True)
                    break
            except Exception as e:
                print(f"WORKER: ⚠️ Could not refresh via messages: {e}", flush=True)
                # Try get_chat as fallback
                try:
                    chat_info = await app.get_chat(final_chat_id)
                    print(f"WORKER: ✅ Verified via get_chat: {chat_info.title}", flush=True)
                except Exception as e2:
                    print(f"WORKER: ⚠️ Verification failed: {e2} (will try upload anyway)", flush=True)
        
        else:
            raise Exception(
                f"Invalid format: {chat_str}\n"
                "Use: https://t.me/+... (private) OR @username (public) OR -100... (numeric)"
            )
        
        if not final_chat_id:
            raise Exception("Could not resolve chat ID")
        
        # --- UPLOAD VIDEO ---
        with SmartStream(file_url, filename) as stream:
            if stream.total_size == 0:
                raise Exception("File size is 0. Seedr link expired.")
            
            print(f"WORKER: 📤 Uploading {filename} ({stream.total_size/1024/1024:.1f}MB) to {final_chat_id}...", flush=True)
            
            try:
                msg = await app.send_video(
                    chat_id=final_chat_id,
                    video=stream,
                    caption=caption,
                    file_name=filename,
                    supports_streaming=True,
                    progress=lambda c, t: print(
                        f"📊 Progress: {c/1024/1024:.1f}/{t/1024/1024:.1f}MB ({c*100//t}%)", 
                        flush=True
                    ) if c % (50*1024*1024) < 1024*1024 else None
                )
                
                # Generate private message link
                clean_id = str(msg.chat.id).replace('-100', '')
                private_link = f"https://t.me/c/{clean_id}/{msg.id}"
                
                print(f"WORKER: ✅ Upload complete! Link: {private_link}", flush=True)
                
                return {
                    "success": True,
                    "message_id": msg.id,
                    "chat_id": msg.chat.id,
                    "file_id": msg.video.file_id,
                    "file_unique_id": msg.video.file_unique_id,
                    "private_link": private_link,
                    "file_size": msg.video.file_size,
                    "duration": msg.video.duration,
                    "width": msg.video.width,
                    "height": msg.video.height
                }
                
            except ChatAdminRequired:
                raise Exception("Bot is not an admin in this channel. Please promote the bot.")
            except ChannelPrivate:
                raise Exception("Bot has no access to this private channel. Add it as admin or use invite link.")
            except FloodWait as e:
                raise Exception(f"Telegram rate limit. Wait {e.value} seconds and try again.")
            except Exception as e:
                raise Exception(f"Upload failed: {str(e)}")

# --- 3. QUEUE WORKER ---
JOB_QUEUE = queue.Queue()
JOBS = {} 
WORKER_THREAD = None
WORKER_LOCK = threading.Lock()

def worker_loop():
    """Background worker that processes upload queue"""
    print("SYSTEM: 🚀 Queue Worker Started", flush=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        job_id = None
        try:
            job_id, data = JOB_QUEUE.get()
            print(f"SYSTEM: 📋 Processing Job {job_id}", flush=True)
            JOBS[job_id]['status'] = 'processing'
            JOBS[job_id]['started'] = time.time()
            
            result = loop.run_until_complete(perform_upload(
                file_url=data['url'],
                chat_target=data['chat_id'],
                caption=data.get('caption', ''),
                filename=data.get('filename', 'video.mp4')
            ))
            
            JOBS[job_id]['status'] = 'done'
            JOBS[job_id]['result'] = result
            JOBS[job_id]['completed'] = time.time()
            print(f"SYSTEM: ✅ Job {job_id} completed successfully!", flush=True)
            
        except Exception as e:
            error_msg = str(e)
            print(f"SYSTEM: ❌ Job {job_id} failed: {error_msg}", flush=True)
            if job_id:
                JOBS[job_id]['status'] = 'failed'
                JOBS[job_id]['error'] = error_msg
                JOBS[job_id]['failed'] = time.time()
        finally:
            if job_id:
                JOB_QUEUE.task_done()
            
            # Cleanup old jobs (keep last 100)
            if len(JOBS) > 100:
                old_jobs = sorted(JOBS.items(), key=lambda x: x[1].get('created', 0))[:50]
                for old_id, _ in old_jobs:
                    del JOBS[old_id]
                print("SYSTEM: 🧹 Cleaned up old jobs", flush=True)

def ensure_worker_alive():
    """Start worker thread if not running (thread-safe)"""
    global WORKER_THREAD
    with WORKER_LOCK:
        if WORKER_THREAD is None or not WORKER_THREAD.is_alive():
            print("SYSTEM: 🔄 Starting worker thread...", flush=True)
            WORKER_THREAD = threading.Thread(target=worker_loop, daemon=True)
            WORKER_THREAD.start()

# --- FLASK ROUTES ---
@app.route('/')
def home(): 
    """Health check endpoint"""
    ensure_worker_alive()
    return jsonify({
        "status": "online",
        "queue_size": JOB_QUEUE.qsize(),
        "total_jobs": len(JOBS),
        "worker_alive": WORKER_THREAD.is_alive() if WORKER_THREAD else False
    })

@app.route('/upload-telegram', methods=['POST'])
def upload_telegram():
    """
    Upload video to Telegram
    POST Body:
    {
        "url": "https://seedr.cc/...",
        "chat_id": "https://t.me/+InviteHash" OR "@moviessquares" OR "-1003558592981",
        "caption": "Movie Title (1080p)",
        "filename": "movie.mp4"
    }
    """
    data = request.json
    
    if not data or not data.get('url'):
        return jsonify({"error": "Missing 'url' parameter"}), 400
    if not data.get('chat_id'):
        return jsonify({"error": "Missing 'chat_id' parameter"}), 400
    
    ensure_worker_alive()
    
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        'status': 'queued',
        'created': time.time(),
        'request': {
            'chat_id': data.get('chat_id'),
            'filename': data.get('filename', 'video.mp4')
        }
    }
    JOB_QUEUE.put((job_id, data))
    
    print(f"API: 📥 Job {job_id} queued for chat {data.get('chat_id')}", flush=True)
    
    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Upload job queued successfully"
    })

@app.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    """
    Check job status
    GET /job-status/{job_id}
    """
    ensure_worker_alive()
    
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    
    return jsonify(job)

# --- WEB PAGE TO GET CHAT ID (PUBLIC CHANNELS) ---
@app.route('/get-id')
def get_id_page():
    """Web page to get channel ID (for public channels only)"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Get Channel ID</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        h1 { color: #0088cc; }
        input { width: 100%; padding: 10px; margin: 10px 0; font-size: 16px; box-sizing: border-box; }
        button { background: #0088cc; color: white; padding: 10px 20px; border: none; cursor: pointer; font-size: 16px; border-radius: 5px; }
        button:hover { background: #006699; }
        #result { margin-top: 20px; padding: 15px; background: #f0f0f0; border-radius: 5px; }
        .error { color: red; }
        .success { color: green; font-weight: bold; }
        .note { background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>🔍 Get Telegram Channel ID</h1>
    <div class="note">
        <strong>Note:</strong> This tool only works for <strong>public channels</strong> (with @username).
        <br>For private channels, use the invite link directly in your n8n workflow.
    </div>
    <p>Enter your public channel username (with or without @):</p>
    <input type="text" id="username" placeholder="@moviessquares or moviessquares" />
    <button onclick="getID()">Get ID</button>
    <div id="result"></div>

    <script>
        async function getID() {
            const input = document.getElementById('username').value.trim();
            const result = document.getElementById('result');
            
            if (!input) {
                result.innerHTML = '<p class="error">Please enter a username</p>';
                return;
            }
            
            const username = input.startsWith('@') ? input : '@' + input;
            result.innerHTML = '<p>Loading...</p>';
            
            try {
                const response = await fetch('/api/get-id', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    result.innerHTML = `<p class="error">Error: ${data.error}</p>`;
                } else {
                    result.innerHTML = `
                        <h3>✅ Success!</h3>
                        <p><strong>Channel:</strong> ${data.title}</p>
                        <p><strong>Username:</strong> ${data.username || 'N/A'}</p>
                        <p class="success">Numeric ID: ${data.id}</p>
                        <p><em>Copy this ID and use it in your n8n workflow.</em></p>
                    `;
                }
            } catch (err) {
                result.innerHTML = `<p class="error">Network error: ${err.message}</p>`;
            }
        }
    </script>
</body>
</html>
    '''

@app.route('/api/get-id', methods=['POST'])
def api_get_id():
    """API endpoint to resolve public channel username to ID"""
    try:
        username = request.json.get('username', '').strip()
        if not username:
            return jsonify({"error": "Username required"}), 400
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def fetch():
            async with Client("temp", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir="/tmp") as app:
                chat = await app.get_chat(username)
                return {
                    "id": chat.id,
                    "title": chat.title,
                    "username": chat.username,
                    "type": str(chat.type)
                }
        
        result = loop.run_until_complete(fetch())
        loop.close()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- CHECK PRIVATE CHANNEL ACCESS ---
@app.route('/check-private/<chat_id>')
def check_private_channel(chat_id):
    """
    Check if bot can access a private channel
    Visit: https://your-url.onrender.com/check-private/-1003558592981
    """
    try:
        chat_id_int = int(chat_id)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def test_access():
            async with Client(
                "test_session", 
                api_id=API_ID, 
                api_hash=API_HASH, 
                bot_token=BOT_TOKEN, 
                workdir="/tmp"
            ) as app:
                try:
                    # Try to get chat info
                    chat = await app.get_chat(chat_id_int)
                    
                    # Try to get member count
                    try:
                        member_count = await app.get_chat_members_count(chat_id_int)
                    except:
                        member_count = "Unknown"
                    
                    # Try to get bot's status
                    try:
                        me = await app.get_me()
                        member = await app.get_chat_member(chat_id_int, me.id)
                        bot_status = str(member.status)
                    except:
                        bot_status = "Unknown"
                    
                    return {
                        "success": True,
                        "access": "✅ Bot has access",
                        "id": chat.id,
                        "title": chat.title,
                        "type": str(chat.type),
                        "username": chat.username,
                        "members": member_count,
                        "bot_status": bot_status
                    }
                except ChannelPrivate:
                    return {
                        "success": False,
                        "access": "❌ Bot cannot access this private channel",
                        "error": "ChannelPrivate",
                        "solution": "Add the bot as an administrator or use the invite link"
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "access": "❌ Error accessing channel",
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
        
        result = loop.run_until_complete(test_access())
        loop.close()
        
        # Return JSON if requested
        if request.args.get('format') == 'json':
            return jsonify(result)
        
        # Return HTML
        if result.get('success'):
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Channel Access Check</title>
    <style>
        body {{ font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }}
        .success {{ color: green; font-size: 24px; font-weight: bold; }}
        .info {{ background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .code {{ background: #282c34; color: #61dafb; padding: 10px; border-radius: 5px; font-family: monospace; }}
    </style>
</head>
<body>
    <h1>🔍 Channel Access Test</h1>
    <p class="success">{result['access']}</p>
    <div class="info">
        <p><strong>ID:</strong> {result['id']}</p>
        <p><strong>Title:</strong> {result['title']}</p>
        <p><strong>Type:</strong> {result['type']}</p>
        <p><strong>Username:</strong> {result.get('username', 'N/A (Private)')}</p>
        <p><strong>Members:</strong> {result.get('members', 'N/A')}</p>
        <p><strong>Bot Status:</strong> {result.get('bot_status', 'N/A')}</p>
    </div>
    <h3>✅ Your bot can upload to this channel!</h3>
    <p>Use this ID in your n8n workflow:</p>
    <div class="code">{result['id']}</div>
</body>
</html>
            """
        else:
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Channel Access Check</title>
    <style>
        body {{ font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }}
        .error {{ color: red; font-size: 24px; font-weight: bold; }}
        .solution {{ background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107; }}
    </style>
</head>
<body>
    <h1>🔍 Channel Access Test</h1>
    <p class="error">{result['access']}</p>
    <div class="solution">
        <h3>🔧 Solution:</h3>
        <p><strong>Use the invite link instead of numeric ID!</strong></p>
        <ol>
            <li>Open your private channel in Telegram</li>
            <li>Go to channel settings → <strong>Invite Links</strong></li>
            <li>Copy the invite link (https://t.me/+...)</li>
            <li>Use that link in your n8n workflow's chat_id field</li>
        </ol>
        <p>The invite link will force the bot to refresh access on every request.</p>
    </div>
    <p><strong>Error:</strong> {result.get('error', 'Unknown')}</p>
    <p><strong>Error Type:</strong> {result.get('error_type', 'N/A')}</p>
</body>
</html>
            """
        
        return html
        
    except ValueError:
        return jsonify({"error": "Invalid chat ID format. Use numeric ID like -1003558592981"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- FORCE JOIN ROUTE (SESSION REFRESH) ---
@app.route('/force-join/<chat_id>')
def force_join(chat_id):
    """
    Force bot to refresh access to a channel
    Visit: https://your-url.onrender.com/force-join/-1003558592981
    """
    try:
        chat_id_int = int(chat_id)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def do_join():
            async with Client(
                "bot_session", 
                api_id=API_ID, 
                api_hash=API_HASH, 
                bot_token=BOT_TOKEN, 
                workdir="/tmp"
            ) as app:
                try:
                    print(f"Attempting to fetch messages from {chat_id_int}...", flush=True)
                    async for message in app.get_chat_history(chat_id_int, limit=1):
                        print(f"✅ Successfully accessed message: {message.id}", flush=True)
                        return {
                            "success": True,
                            "method": "get_chat_history",
                            "message": "Bot can now access the channel",
                            "chat_id": chat_id_int
                        }
                    
                    chat = await app.get_chat(chat_id_int)
                    return {
                        "success": True,
                        "method": "get_chat",
                        "title": chat.title,
                        "chat_id": chat_id_int
                    }
                    
                except Exception as e:
                    return {
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
        
        result = loop.run_until_complete(do_join())
        loop.close()
        
        if result.get('success'):
            html = f"""
<!DOCTYPE html>
<html>
<head><title>Force Join Result</title>
<style>
    body {{ font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }}
    .success {{ color: green; font-size: 20px; font-weight: bold; }}
</style>
</head>
<body>
    <h1>✅ Success!</h1>
    <p class="success">Bot session updated successfully</p>
    <p><strong>Chat ID:</strong> {result['chat_id']}</p>
    <p><strong>Method:</strong> {result.get('method', 'N/A')}</p>
    <p>You can now try uploading to this channel.</p>
    <p><a href="/check-private/{chat_id}">Re-check access</a></p>
</body>
</html>
            """
        else:
            html = f"""
<!DOCTYPE html>
<html>
<head><title>Force Join Result</title>
<style>
    body {{ font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }}
    .error {{ color: red; }}
</style>
</head>
<body>
    <h1>❌ Failed</h1>
    <p class="error">Could not access channel</p>
    <p><strong>Error:</strong> {result.get('error', 'Unknown')}</p>
    <p><strong>Error Type:</strong> {result.get('error_type', 'N/A')}</p>
    <h3>Solution:</h3>
    <p>Use the <strong>invite link</strong> instead of numeric ID in your n8n workflow.</p>
</body>
</html>
            """
        
        return html
        
    except ValueError:
        return jsonify({"error": "Invalid chat ID"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- SEEDR ROUTES ---
@app.route('/add-magnet', methods=['POST'])
def add_magnet():
    """Add magnet to Seedr"""
    try:
        resp = requests.post(
            "https://www.seedr.cc/oauth_test/resource.php?json=1",
            data={
                "access_token": request.json.get('token'),
                "func": "add_torrent",
                "torrent_magnet": request.json.get('magnet')
            },
            timeout=30
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/list-files', methods=['POST'])
def list_files():
    """List Seedr files in folder"""
    try:
        data = request.json
        token = data.get('token')
        folder_id = str(data.get('folder_id', "0"))
        
        if folder_id == "0":
            url = "https://www.seedr.cc/api/folder"
        else:
            url = f"https://www.seedr.cc/api/folder/{folder_id}"
        
        resp = requests.get(
            url, 
            params={"access_token": token}, 
            headers=HEADERS_STREAM,
            timeout=30
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-link', methods=['POST'])
def get_link():
    """Get download link from Seedr"""
    try:
        resp = requests.post(
            "https://www.seedr.cc/oauth_test/resource.php?json=1",
            data={
                "access_token": request.json.get('token'),
                "func": "fetch_file",
                "folder_file_id": str(request.json.get('file_id'))
            },
            timeout=30
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("=" * 50, flush=True)
    print("🚀 Seedr-Telegram Bridge Starting", flush=True)
    print("=" * 50, flush=True)
    ensure_worker_alive()
    app.run(host='0.0.0.0', port=10000)
