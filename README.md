# CleanStream Player 🎬 (Anti-PopUp & Ad-Free)

Server lokal dan pemutar web mandiri untuk mengekstrak dan memutar video dari tautan **Streamrizz**, **Vidoy**, dan jaringan sejenisnya tanpa iklan, pop-up, pop-under, maupun deteksi adblocker.

Sangat optimal untuk:
- 📱 **iPhone / iPad (Safari iOS)**
- 💻 **Desktop (Mac / Windows / Linux)**
- 📺 **AirPlay & Picture-in-Picture**

---

## 🚀 Cara Menjalankan

Buka terminal di direktori ini, lalu jalankan:

```bash
python3 scripts/local_server.py
```

Server akan langsung aktif dan menampilkan alamat akses:
* **Komputer (Mac):** `http://localhost:8888`
* **iPhone / iPad:** `http://<IP_LOKAL_ANDA>:8888` (misal: `http://192.168.1.5:8888`)

---

## 📱 Cara Memutar di iPhone / iPad

1. Pastikan iPhone terhubung ke jaringan **Wi-Fi yang sama** dengan komputer Mac Anda.
2. Buka aplikasi **Kamera** di iPhone, lalu arahkan ke **QR Code** yang muncul di layar web CleanStream di komputer Anda (atau ketik langsung alamat `http://192.168.x.x:8888` di Safari iPhone).
3. Tempel (*paste*) link Streamrizz/Vidoy (contoh: `https://streamrizz.com/e/l4mvca58up19`), lalu tekan **Putar Sekarang**.
4. Video akan langsung terputar di pemutar bawaan iOS secara mulus, tanpa pop-up iklan sama sekali!

---

## ✨ Fitur Utama

- **Zero Dependency:** Menggunakan modul bawaan Python 3 standar (`http.server`, `urllib`), tanpa perlu `pip install`.
- **HTTP Range Support (RFC 7233):** Mendukung seeking / fast-forward / rewind instan di iOS AVPlayer dan Safari.
- **Smart Referer Injection:** Mengatasi proteksi Hotlink `HTTP 403 Forbidden` secara otomatis di sisi server lokal.
- **QR Code Sharing:** Buka antarmuka atau video di perangkat mobile dalam hitungan detik.
- **Riwayat Pemutaran:** Menyimpan riwayat video yang pernah diputar di *localStorage* browser.
- **Tombol Unduh Langsung:** Mengunduh file mentah `.mp4` dengan 1 klik.
