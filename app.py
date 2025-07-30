import os
import datetime
import re
import unicodedata
import pickle
import pytz
from flask import Flask, redirect, request, url_for, render_template_string, session
from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.discovery import build as build_gdrive
from googleapiclient.http import MediaFileUpload

# --- Flask App ---
app = Flask(__name__)
app.secret_key = 'ganti-ini-dengan-yang-lebih-kuat'

# Pastikan Railway dianggap HTTPS
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --- Konfigurasi ---
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

# Pakai CLIENT_SECRET_JSON dari env var atau fallback lokal
if 'CLIENT_SECRET_JSON' in os.environ:
    CLIENT_SECRET = '/tmp/client_secret.json'
    with open(CLIENT_SECRET, 'w') as f:
        f.write(os.environ['CLIENT_SECRET_JSON'])
else:
    CLIENT_SECRET = 'client_secret.json'

CHANNEL_ID = 'UCkqDgAg-mSqv_4GSNMlYvPw'
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

# Tentukan URL redirect sesuai environment
if os.environ.get("RAILWAY_ENVIRONMENT"):
    REDIRECT_URI = "https://youtube-judol-cleaner-production.up.railway.app/oauth2callback"
else:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    REDIRECT_URI = "http://localhost:5000/oauth2callback"

# --- Daftar Kata Spam ---
KEYWORDS = list(set([
    'pulau', 'pulauwin', 'pluto', 'plut088', 'pluto88', 'probet855',
    'mona', 'mona4d', 'alexis17', 'soundeffect', 'mudahwin',
    'akunpro', '혗혜혓혈혜혞혐형', 'maxwin', 'pulau777', 'weton88',
    'plutowin', 'plutowinn', 'pluto8', 'pulowin', 'pulauw', 'plu88',
    'pulautoto', 'tempatnyaparapemenangsejatiberkumpul',
    'bahkandilaguremix', 'bergabunglahdenganpulau777',
    '퓟퓤퓛퓐퓤퓦퓘퓝', '홿횄홻홰횄횆홸홽'
]))

# --- Fungsi Cek Spam ---
def normalize_text(text):
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text)
    return text.replace(" ", "").lower()

def is_spam(text):
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in KEYWORDS)

# --- Autentikasi ---
def get_youtube_service():
    if 'credentials' not in session:
        return None
    creds = pickle.loads(session['credentials'])
    return build('youtube', 'v3', credentials=creds)

# --- Ambil Video Terbaru ---
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

# --- Proses Komentar ---
def process_video_comments(youtube, video_id):
    nextPageToken = None
    deleted_comments = []
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
                deleted_comments.append({
                    'video_id': video_id,
                    'text': text
                })

        nextPageToken = res.get('nextPageToken')
        if not nextPageToken:
            break
    return deleted_comments

# --- Upload Log ke Google Drive ---
FOLDER_ID = '1Elns-lVNWfD4993wOA24_QHNtQJRvpE2'

if 'SERVICE_ACCOUNT_JSON' in os.environ:
    SERVICE_ACCOUNT_FILE = '/tmp/service_account.json'
    with open(SERVICE_ACCOUNT_FILE, 'w') as f:
        f.write(os.environ['SERVICE_ACCOUNT_JSON'])
else:
    SERVICE_ACCOUNT_FILE = 'service_account.json'

def upload_log_to_drive(filename):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive_service = build_gdrive("drive", "v3", credentials=creds)
    file_metadata = {
        "name": filename,
        "parents": [FOLDER_ID]
    }
    media = MediaFileUpload(filename, mimetype="text/plain")
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    print(f"✅ Log berhasil diupload ke Google Drive. File ID: {file.get('id')}")

# --- Routes ---
@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    return render_template_string("""
        <h2>🩹 YouTube Spam Cleaner</h2>
        <form action="/run" method="post">
            <button type="submit">Mulai Bersihkan Komentar Spam</button>
        </form>
    """)

@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
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

    video_ids = get_latest_video_ids(youtube, CHANNEL_ID)
    deleted_comments = []
    for vid in video_ids:
        deleted_comments += process_video_comments(youtube, vid)

    waktu = datetime.datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')

    log_filename = f'log_{datetime.datetime.now(JAKARTA_TZ).strftime("%Y%m%d_%H%M%S")}.txt'
    with open(log_filename, 'w', encoding='utf-8') as f:
        if deleted_comments:
            for c in deleted_comments:
                f.write(f"Video: {c['video_id']}\nIsi: {c['text']}\n\n")
        else:
            f.write(f"Tidak ada komentar spam ditemukan pada {waktu}")

    upload_log_to_drive(log_filename)

    return render_template_string("""
        <h2>✅ {{ count }} komentar spam berhasil dihapus pada {{ waktu }}</h2>
        {% if comments %}
            <h3>Detail Komentar Spam:</h3>
            <ul>
                {% for c in comments %}
                    <li>
                        <b>Video:</b> {{ c.video_id }}<br>
                        <b>Isi:</b> {{ c.text }}
                    </li><br>
                {% endfor %}
            </ul>
        {% else %}
            <p>👍 Tidak ada komentar spam ditemukan saat ini.</p>
        {% endif %}
        <a href="/">⬅️ Kembali</a>
    """, count=len(deleted_comments), waktu=waktu, comments=deleted_comments)

# --- Main ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
