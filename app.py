import os
import re
import unicodedata
import pickle
import datetime
import pytz
import json
import requests
from flask import Flask, redirect, request, url_for, render_template_string, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# --- Load OAuth config from ENV ---
if 'CLIENT_SECRET_JSON' not in os.environ:
    raise RuntimeError("⚠️ CLIENT_SECRET_JSON tidak ditemukan di environment variable!")
try:
    CLIENT_CONFIG = json.loads(os.environ['CLIENT_SECRET_JSON'])
    print(f"✅ CLIENT_CONFIG loaded, keys: {list(CLIENT_CONFIG.keys())}")
except json.JSONDecodeError as e:
    raise RuntimeError(f"⚠️ CLIENT_SECRET_JSON invalid JSON: {e}")

# --- Flask app ---
app = Flask(__name__)
# ambil secret key dari ENV, fallback ke string (ganti di production!)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ganti-ini-dengan-yang-lebih-kuat")

# ProxyFix agar Railway dianggap HTTPS
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --- Konfigurasi YouTube & OAuth ---
SCOPES      = ['https://www.googleapis.com/auth/youtube.force-ssl']
CHANNEL_ID  = 'UCkqDgAg-mSqv_4GSNMlYvPw'
# Redirect URI: Railway vs lokal
if os.environ.get("RAILWAY_ENVIRONMENT"):
    REDIRECT_URI = "https://youtube-judol-cleaner-production.up.railway.app/oauth2callback"
else:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    REDIRECT_URI = "http://localhost:5000/oauth2callback"

# Discord webhook (optional)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# --- Kata kunci spam ---
KEYWORDS = list(set([
    'pulau','pulauwin','pluto','plut088','pluto88','probet855',
    'mona','mona4d','alexis17','soundeffect','mudahwin',
    'akunpro','boterpercaya','maxwin','pulau777','weton88',
    'plutowin','plutowinn','pluto8','pulowin','pulauw','plu88',
    'pulautoto','tempatnyaparapemenangsejatiberkumpul',
    'bahkandilaguremix','bergabunglahdenganpulau777',
    '퓟퓤퓛퓐퓤퓦퓘퓝','홿횄홻홰횄횆홸홽'
]))

def normalize_text(text):
    t = unicodedata.normalize('NFKD', text)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^\w\s]', '', t)
    return t.replace(" ", "").lower()

def is_spam(text):
    return any(k in normalize_text(text) for k in KEYWORDS)

# --- YouTube API helpers ---
def get_youtube_service():
    if 'credentials' not in session:
        return None
    creds = pickle.loads(session['credentials'])
    return build('youtube', 'v3', credentials=creds)

def get_latest_video_ids(youtube, channel_id, count=2):
    req = youtube.search().list(
        part="id", channelId=channel_id,
        order="date", maxResults=count,
        type="video"
    )
    res = req.execute()
    return [item['id']['videoId'] for item in res['items']]

def process_video_comments(youtube, video_id):
    nextPageToken = None
    deleted = []
    while True:
        res = youtube.commentThreads().list(
            part="snippet", videoId=video_id,
            maxResults=100, pageToken=nextPageToken,
            textFormat="plainText"
        ).execute()
        for itm in res.get('items', []):
            com = itm['snippet']['topLevelComment']
            cid, txt = com['id'], com['snippet']['textDisplay']
            if is_spam(txt):
                youtube.comments().setModerationStatus(
                    id=cid, moderationStatus="rejected"
                ).execute()
                deleted.append({'video_id': video_id, 'text': txt})
        nextPageToken = res.get('nextPageToken')
        if not nextPageToken:
            break
    return deleted

# --- Discord logging ---
def send_log_to_discord(lines, waktu):
    if not DISCORD_WEBHOOK_URL:
        return
    if lines:
        content = f"**🧹 {len(lines)} komentar spam dihapus ({waktu})**\n" + \
                  "\n".join(f"[{l['video_id']}] {l['text']}" for l in lines)
    else:
        content = f"👍 Tidak ada komentar spam ditemukan pada {waktu}."
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=10)
    except Exception as e:
        app.logger.error(f"Failed to send Discord log: {e}")

# --- Routes ---
@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    return render_template_string("""
        <h2>🧹 YouTube Spam Cleaner</h2>
        <form action="/run" method="post">
          <label>Jumlah video:</label>
          <input type="number" name="video_count" value="2" min="1" max="50">
          <button type="submit">Mulai Bersihkan Komentar Spam</button>
        </form>
    """)

@app.route('/login')
def login():
    flow = Flow.from_client_config(
        CLIENT_CONFIG, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        state=session.get('state'),
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request.url)
    session['credentials'] = pickle.dumps(flow.credentials)
    return redirect(url_for('index'))

@app.route('/run', methods=['POST'])
def run_cleaner():
    youtube = get_youtube_service()
    if not youtube:
        return redirect(url_for('login'))

    # validasi input
    try:
        cnt = int(request.form.get('video_count', 2))
    except ValueError:
        cnt = 2
    cnt = max(1, min(50, cnt))

    videos = get_latest_video_ids(youtube, CHANNEL_ID, count=cnt)
    deleted = []
    for v in videos:
        deleted += process_video_comments(youtube, v)

    waktu = datetime.datetime.now(pytz.timezone("Asia/Jakarta"))\
                    .strftime('%Y-%m-%d %H:%M')
    send_log_to_discord(deleted, waktu)

    return render_template_string("""
        <h2>✅ {{ count }} komentar spam berhasil dihapus pada {{ waktu }}</h2>
        {% if comments %}
          <h3>Detail Komentar Spam:</h3><ul>
            {% for c in comments %}
              <li><b>Video:</b> {{ c.video_id }}<br><b>Isi:</b> {{ c.text }}</li><br>
            {% endfor %}
          </ul>
        {% else %}
          <p>👍 Tidak ada komentar spam ditemukan saat ini.</p>
        {% endif %}
        <a href="/">⬅️ Kembali</a>
    """, count=len(deleted), waktu=waktu, comments=deleted)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
