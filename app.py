import os
import datetime
import re
import unicodedata
import pickle
import requests
import pytz
from flask import Flask, redirect, request, url_for, render_template_string, session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# --- Tes Webhook Saat Start ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL:
    print("⚠️ ERROR: DISCORD_WEBHOOK_URL tidak ditemukan di environment variable!")
else:
    print("✅ DISCORD_WEBHOOK_URL ditemukan, mengirim pesan tes ke Discord...")
    try:
        test_payload = {
            "content": "✅ *Bot YouTube Spam Cleaner* berhasil terhubung ke Discord Webhook!"
        }
        resp = requests.post(DISCORD_WEBHOOK_URL, json=test_payload, timeout=10)
        if resp.status_code == 204:
            print("✅ Pesan tes berhasil dikirim ke Discord.")
        else:
            print(f"⚠️ Gagal kirim pesan tes. Status: {resp.status_code}, Response: {resp.text}")
    except Exception as e:
        print(f"❌ ERROR saat kirim pesan tes: {e}")

# --- Flask App ---
app = Flask(__name__)
app.secret_key = 'ganti-ini-dengan-yang-lebih-kuat'

# --- Konfigurasi ---
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CLIENT_SECRET = 'client_secret.json'
CHANNEL_ID = 'UCkqDgAg-mSqv_4GSNMlYvPw'

# Zona waktu Jakarta
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

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

# --- Kirim Log ke Discord ---
def send_log_to_discord(lines, waktu):
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')  # dibaca ulang
    if not webhook_url:
        app.logger.warning("DISCORD_WEBHOOK_URL not set. Skipping Discord log.")
        return

    if lines:
        content = f"**🧹 {len(lines)} komentar spam berhasil dihapus ({waktu})**\n"
        content += "\n".join(
            [f"[Video: {line['video_id']}] {line['text']}" for line in lines]
        )
    else:
        content = f"👍 Tidak ada komentar spam ditemukan pada {waktu}."

    payload = {"content": content}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 204:
            app.logger.error(f"Discord webhook error: {resp.status_code} - {resp.text}")
    except Exception as e:
        app.logger.error(f"Failed to send Discord log: {e}")

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
        redirect_uri='https://youtube-judol-cleaner-production.up.railway.app/oauth2callback'
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

    video_ids = get_latest_video_ids(youtube, CHANNEL_ID)
    deleted_comments = []
    for vid in video_ids:
        deleted_comments += process_video_comments(youtube, vid)

    waktu = datetime.datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')

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

# --- Main ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
