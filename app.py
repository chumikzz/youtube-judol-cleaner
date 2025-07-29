import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask, redirect, request, url_for, render_template_string, session
import datetime
import re
import unicodedata
import pickle
import requests

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

app = Flask(__name__)
app.secret_key = 'ganti-ini-dengan-yang-lebih-kuat'

# --- KONFIGURASI --- #
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CLIENT_SECRET = 'client_secret.json'
CHANNEL_ID = 'UCkqDgAg-mSqv_4GSNMlYvPw'
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# --- SPAM KEYWORDS --- #
KEYWORDS = list(set([
    'pulau', 'pulauwin', 'pluto', 'plut088', 'pluto88', 'probet855',
    'mona', 'mona4d', 'alexis17', 'soundeffect', 'mudahwin',
    'akunpro', 'boterpercaya', 'maxwin', 'pulau777', 'weton88',
    'plutowin', 'plutowinn', 'pluto8', 'pulowin', 'pulauw', 'plu88',
    'pulautoto', '홋홐홇혼홐홒홄홉',
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

# --- DISCORD LOGGER --- #
def send_log_to_discord(lines, waktu):
    if not DISCORD_WEBHOOK_URL:
        return

    if lines:
        content = f"🧹 **{len(lines)} komentar spam berhasil dihapus** pada `{waktu}`\n\n"
        content += "\n".join([
            f"🗑️ [Video: {line['video_id']}] {line['text']}" for line in lines
        ])
    else:
        content = f"✅ Tidak ada komentar spam ditemukan pada `{waktu}`."

    payload = {"content": content[:1900]}  # max limit Discord 2000 char
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        app.logger.error(f"Gagal kirim log ke Discord: {e}")

# --- ROUTES --- #
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
        redirect_uri='http://localhost:5000/oauth2callback'
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
        redirect_uri='http://localhost:5000/oauth2callback'
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

    waktu = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    send_log_to_discord(deleted_comments, waktu)

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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
