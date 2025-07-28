import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask, redirect, request, url_for, render_template_string, session
import datetime
import re
import unicodedata
import pickle
import json

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

app = Flask(__name__)
app.secret_key = 'ganti-ini-dengan-yang-lebih-kuat'

# --- KONFIGURASI --- #
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CLIENT_SECRET_JSON_CONTENT = os.getenv('CLIENT_SECRET_JSON')
CLIENT_SECRET_FILE = 'client_secret.json'

# Hanya buat file jika belum ada dan variabel tersedia
if CLIENT_SECRET_JSON_CONTENT and not os.path.exists(CLIENT_SECRET_FILE):
    with open(CLIENT_SECRET_FILE, 'w') as f:
        f.write(CLIENT_SECRET_JSON_CONTENT)

CHANNEL_ID = 'UCkqDgAg-mSqv_4GSNMlYvPw'

# --- SPAM KEYWORDS --- #
KEYWORDS = list(set([
    'pulau', 'pulauwin', 'pluto', 'plut088', 'pluto88', 'probet855',
    'mona', 'mona4d', 'alexis17', 'soundeffect', 'mudahwin',
    'akunpro', 'boterpercaya', 'maxwin', 'pulau777', 'weton88',
    'plutowin', 'plutowinn', 'pluto8', 'pulowin', 'pulauw', 'plu88',
    'pulautoto', 'tempatnyaparapemenangsejatiberkumpul',
    'bahkandilaguremix', 'bergabunglahdenganpulau777'
]))

def normalize_text(text):
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text)
    return text.replace(" ", "").lower()

def is_spam(text):
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in KEYWORDS)

def get_youtube_service():
    if 'credentials' not in session:
        return None
    creds = pickle.loads(session['credentials'])
    return build('youtube', 'v3', credentials=creds)

def get_latest_video_ids(youtube, channel_id, count=2):
    req = youtube.search().list(
        part="id",
        channelId=channel_id,
        order="date",
        maxResults=count,
        type="video"
    )
    res = req.execute()
    return [item['id']['videoId'] for item in res['items']]

def process_video_comments(youtube, video_id, log_lines):
    nextPageToken = None
    deleted_count = 0
    while True:
        res = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=nextPageToken,
            textFormat="plainText"
        ).execute()

        for item in res.get('items', []):
            comment = item['snippet']['topLevelComment']
            comment_id = comment['id']
            text = comment['snippet']['textDisplay']
            if is_spam(text):
                youtube.comments().setModerationStatus(
                    id=comment_id,
                    moderationStatus="rejected"
                ).execute()
                deleted_count += 1
                log_lines.append(f"[{video_id}] Dihapus: {text.strip()}")

        nextPageToken = res.get('nextPageToken')
        if not nextPageToken:
            break
    return deleted_count

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    return render_template_string("""
        <h2>🧹 YouTube Spam Cleaner</h2>
        <form action="/run" method="post">
            <label>Jumlah video yang ingin dibersihkan:</label>
            <input type="number" name="video_count" min="1" max="50" value="2" required>
            <br><br>
            <button type="submit">Mulai Bersihkan Komentar Spam</button>
        </form>
    """)

@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri='https://youtube-judol-cleaner-production.up.railway.app/oauth2callback'
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri='https://youtube-judol-cleaner-production.up.railway.app/oauth2callback'
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session['credentials'] = pickle.dumps(creds)
    return redirect(url_for('index'))

@app.route('/run', methods=['POST'])
def run_cleaner():
    youtube = get_youtube_service()
    if not youtube:
        return redirect(url_for('login'))

    video_count = int(request.form.get('video_count', 2))
    video_ids = get_latest_video_ids(youtube, CHANNEL_ID, count=video_count)

    total_deleted = 0
    log_lines = []
    for vid in video_ids:
        total_deleted += process_video_comments(youtube, vid, log_lines)

    waktu = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    log_filename = f"spam_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    if log_lines:
        with open(log_filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(log_lines))

    return f"✅ {total_deleted} komentar spam berhasil dihapus pada {waktu}.<br>Log disimpan ke: <b>{log_filename}</b>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
