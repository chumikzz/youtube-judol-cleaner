
# 🎯 YouTube Spam Cleaner

Aplikasi Python berbasis Flask untuk mendeteksi dan menghapus komentar spam dari video di saluran YouTube menggunakan YouTube Data API v3.

---

## ✨ Fitur Utama

✅ Autentikasi OAuth 2.0  
✅ Deteksi komentar spam berdasarkan keyword yang telah ditentukan  
✅ Pemrosesan beberapa video terbaru (jumlah video bisa ditentukan)  
✅ Penghapusan otomatis komentar spam menggunakan API  
✅ Export hasil ke file log (dengan timestamp)  
✅ Antarmuka web sederhana via Flask

---

## 🚀 Cara Menjalankan

1. **Clone repository ini:**

```bash
git clone https://github.com/chumikzz/youtube-judol-cleaner.git
cd youtube-judol-cleaner
```

2. **Siapkan virtual environment (opsional tapi disarankan):**

```bash
python -m venv venv
venv\Scripts\activate     # untuk Windows
source venv/bin/activate  # untuk macOS/Linux
```

3. **Install dependensi:**

```bash
pip install -r requirements.txt
```

> Jika file `requirements.txt` belum dibuat, kamu bisa generate dengan:
> ```bash
> pip freeze > requirements.txt
> ```

4. **Letakkan file kredensial:**
   - Pastikan kamu punya file `client_secret.json` dari Google Cloud Console.
   - Simpan file tersebut di folder utama project (satu level dengan `app.py`).

5. **Jalankan aplikasi:**

```bash
python app.py
```

6. **Buka browser ke:**
```
http://localhost:5000
```

---

## ⚙️ Konfigurasi Penting

- `client_secret.json`: File kredensial Google OAuth2.
- `CHANNEL_ID`: Diatur langsung di `app.py`, ubah sesuai ID channel YouTube milikmu.
- Keyword spam bisa disesuaikan di variabel `KEYWORDS`.

---

## 📁 Struktur Folder

```
YouTube-Spam-Cleaner/
│
├── app.py               # Aplikasi utama Flask
├── client_secret.json   # File kredensial (JANGAN DIUPLOAD!)
├── .gitignore           # File yang diabaikan oleh Git
├── Logs/                # Folder hasil log pembersihan
├── Static/              # (opsional) asset HTML/CSS
├── Scripts/             # (opsional) skrip tambahan
└── README.md            # Dokumen ini
```

---

## 🔒 Keamanan

⚠️ Jangan pernah mengupload `client_secret.json` atau `token.json` ke GitHub.  
Pastikan `.gitignore` kamu sudah melindungi file-file sensitif seperti:

```gitignore
client_secret.json
token.json
log_*.txt
Logs/
```

---

## 📄 Lisensi

MIT License © 2025 — [@chumikzz](https://github.com/chumikzz)

---

## ❤️ Kontribusi

Pull request dan masukan sangat diterima!  
Silakan fork project ini dan sesuaikan sesuai kebutuhanmu. Bila perlu bantuan, open saja issue.
