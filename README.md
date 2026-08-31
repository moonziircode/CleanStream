# CleanStream Player 🎬 (Anti-PopUp & Ad-Free)

Server lokal dan pemutar web mandiri untuk memutar video streaming secara bersih tanpa iklan, pop-up, pop-under, maupun deteksi adblocker.

Sangat optimal untuk:
- 📱 **iPhone / iPad (Safari iOS)**
- 💻 **Desktop (Mac / Windows / Linux)**
- 📺 **AirPlay & Picture-in-Picture**

---

## 🚀 Cara Menjalankan Secara Lokal

Buka terminal di direktori ini, lalu jalankan:

```bash
python3 scripts/local_server.py
```

Server akan langsung aktif dan menampilkan alamat akses:
* **Komputer (Mac):** `http://localhost:8888`
* **iPhone / iPad:** `http://<IP_LOKAL_ANDA>:8888`

---

## ✨ Fitur Utama

- **HTTP Range Support (RFC 7233):** Mendukung seeking / fast-forward / rewind instan di iOS AVPlayer dan Safari.
- **Smart Referer Injection:** Mengatasi proteksi Hotlink `HTTP 403 Forbidden` secara otomatis.
- **QR Code Sharing:** Buka antarmuka pemutar di perangkat mobile dalam hitungan detik.
- **Riwayat Pemutaran:** Menyimpan riwayat video yang pernah diputar di *localStorage* browser.
- **Tombol Unduh Langsung:** Mengunduh file mentah `.mp4` dengan 1 klik.
