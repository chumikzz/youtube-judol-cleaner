import sys
import datetime
import os
import re
import unicodedata
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# --- ✅ KONFIGURASI --- #
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CHANNEL_ID = 'UCkqDgAg-mSqv_4GSNMlYvPw'  # Ganti dengan Channel ID kamu
CLIENT_SECRET = 'client_secret_channelB.json'  # File JSON OAuth

# --- ✅ KATA-KATA KUNCI SPAM --- #
KEYWORDS = list(set([
    'pulau', 'pulauwin', 'pluto', 'plut088', 'pluto88', 'probet855',
    'mona', 'mona4d', 'alexis17', 'soundeffect', 'mudahwin',
    'akunpro', 'boterpercaya', 'maxwin', 'pulau777', 'weton88',
    'plutowin', 'plutowinn', 'pluto8', 'pulowin', 'pulauw', 'plu88',
    'pulautoto', 'tempatnyaparapemenangsejatiberkumpul',
    'bahkandilaguremix', 'bergabunglahdenganpulau777'
]))

# --- ✅ NORMALISASI & CEK SPAM --- #
def normalize_text(text):
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text)
    text = text.replace(" ", "").lower()
    return text

def is_spam(text):
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in KEYWORDS)

# --- ✅ AUTENTIKASI TANPA LOGIN ULANG --- #
def get_authenticated_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)

# --- ✅ AMBIL 2 VIDEO TERBARU --- #
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

# --- ✅ HAPUS KOMENTAR SPAM DI VIDEO --- #
def process_video_comments(youtube, video_id):
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
                print(f"🚫 Menghapus komentar spam: {text[:60]}...")
                youtube.comments().setModerationStatus(
                    id=comment_id,
                    moderationStatus="rejected"
                ).execute()
                deleted_count += 1

        nextPageToken = res.get('nextPageToken')
        if not nextPageToken:
            break

    return deleted_count

# --- ✅ MAIN FUNCTION --- #
def main():
    # Buat folder logs jika belum ada
    os.makedirs("logs", exist_ok=True)

    now = datetime.datetime.now()
    log_filename = f"logs/log_spam_{now.strftime('%Y-%m-%d_%H-%M')}.txt"

    # Simpan output asli terminal
    original_stdout = sys.stdout

    try:
        with open(log_filename, 'w', encoding='utf-8') as f:
            sys.stdout = f
            sys.stderr = f

            print(f"🕒 Waktu dijalankan: {now}")
            youtube = get_authenticated_service()

            channel_info = youtube.channels().list(part='snippet', mine=True).execute()
            print("✅ Mengakses channel:", channel_info['items'][0]['snippet']['title'])

            print("🔍 Mengecek 2 video terbaru...")
            video_ids = get_latest_video_ids(youtube, CHANNEL_ID)

            total_deleted = 0
            for vid in video_ids:
                print(f"▶️ Video ID: {vid}")
                deleted = process_video_comments(youtube, vid)
                total_deleted += deleted

            print(f"✅ Total komentar spam dihapus: {total_deleted}")
            print("📁 Laporan disimpan di:", log_filename)

    finally:
        # Restore ke terminal
        sys.stdout = original_stdout
        print(f"✅ Selesai. Log: {log_filename}")

# --- ✅ EKSEKUSI SCRIPT --- #
if __name__ == '__main__':
    main()
