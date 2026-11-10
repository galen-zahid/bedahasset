**Runner PowerShell VECTALLY**

Runner ini mengotomasi pekerjaan lokal yang sudah memiliki resep. PowerShell mengatur antrean, backup, proses Python/Node, audit sumber, validasi JSON dan log. Python/OpenCV/Pillow/resvg mengerjakan operasi gambar. Ini bukan model AI yang dilatih ulang, dan bukan mesin generik yang sudah memahami seluruh84 gambar.

Status goal masih paused. Saat penyusunan handoff hanya Status/Doctor/Audit yang diuji; rebuild tidak dijalankan ulang dan Canva tidak diubah.

**Perintah**

~~~powershell
Set-Location 'C:/Users/HP/Documents/Codex/2026-11-07/files-mentioned-by-the-user-training'

# Baca status snapshot.
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Status

# Periksa runtime lokal; tidak memasang paket.
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Doctor

# Verifikasi 84 hash sumber dan paket kandidat yang terdaftar.
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Audit

# Jalankan hanya setelah pengguna meminta melanjutkan.
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action BuildGraphics -Codes S03
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action BuildGraphics -AllSupported
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Compose -Codes S04
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Compare -Codes S06
~~~

Di sesi PowerShell interaktif, beberapa kode bisa diberikan sebagai array:

~~~powershell
./handoff/Vectally.ps1 -Action BuildGraphics -Codes @('S01','S02','S03','S04','S06')
~~~

Jangan mengubah execution policy sistem untuk menjalankan ini. Gunakan sesi PowerShell yang memang diizinkan pada mesin pengguna.

**Kemampuan yang sudah dihubungkan**

| Action | Dukungan |
|---|---|
| Status | Snapshot84 sumber |
| Doctor | Python, dependency render, Node |
| Audit | Semua84 source SHA256; 12 kandidat Story/Highlight yang dikurasi |
| BuildGraphics | S01, S02, S03, S04, S06 |
| Compose | S02, S04, S06, memakai hasil fit yang sudah ada |
| Compare | S03/S04 memakai laporan ekspor19page yang sudah disimpan; S06 memakai actual PNG yang sudah disimpan |

AllSupported berarti semua resep untuk action itu, bukan semua84. Kode yang belum punya resep ditolak secara eksplisit. S05 builder lengkap tidak diaktifkan karena juga menghasilkan eksperimen teks yang pernah ditolak. Rebuild Highlight belum diaktifkan di runner ini: ada patch manual/native yang bisa hilang jika mengimpor ulang paket dasarnya, terutama H05.

**Output dan perilaku**

- Log dan laporan berada di handoff/runs/{waktu}-{action}.
- Sebelum BuildGraphics/Compose, folder output target disalin ke backup di run tersebut.
- Tidak ada recursive delete, move, penutupan proses, instalasi, perubahan akun, atau perubahan sistem.
- Proses dijalankan berurutan dan dihentikan jika sebuah tahap gagal.
- Compare menganalisis ekspor yang SUDAH ada; tidak mengambil ekspor baru dari Canva.
- Audit exit0 berarti pemeriksaan yang diterapkan tidak menemukan blocker; bukan sumber1:1/buyer PASS.
- Audit exit2 berarti ada sumber/paket/font bermasalah. S06 Asap heavy memang harus diblokir.
- Audit font hanya berlaku pada katalog akun yang sudah tertangkap. Font yang belum punya metadata memerlukan pemeriksaan Canva.
- Build/Compose bisa menimpa kandidat lokal, bukan halaman Canva. Backup tersedia. Jangan rebuild semua sembarang demi menghitung progress.

**Batas otomatisasi**

Belum ada impor native Canva otomatis dalam skrip PowerShell ini. Paket JSON harus dimasukkan lewat CUSBE Native Importer di Canva, atau integrasi resmi lain yang benar-benar mendukung operasi yang dibutuhkan. Native gradient, TypeCraft, font upload/kit permission dan buyer editing belum diotomasi oleh runner ini.

Membuat S07 baru tidak cukup mengganti nama file S06. Struktur objek, occlusion, mask dan copy berbeda. AI/manusia perlu menulis resep semantic dan inventory awal; sesudah itu PowerShell dapat menjalankan resep berulang kali tanpa AI mengendalikan setiap langkah.

**Menambahkan resep**

1. Buat builder baru yang membaca source asli dan menghasilkan ASSETS_PACKAGE.json, INVENTORY.json, GEOMETRY-AUDIT.json serta render.
2. Daftarkan engine, script, args dan folder output di jobs.json.
3. Tambahkan jumlah komponen semantik yang diharapkan. Mask IoU saja tidak mendeteksi komponen yang sama sekali tidak ikut diekstrak.
4. Jalankan Audit pada output nyata.
5. Uji actual import/export Canva dan buyer edit; baru perbarui status bukti.
6. Jangan menambahkan langkah publish/share atau GUI takeover ke batch lokal tanpa permintaan pengguna.

**Runner Python lintas platform (cloud / Linux / macOS)**

`handoff/vectally.py` menjalankan `jobs.json` yang SAMA dengan perilaku yang sama (backup, log di `handoff/runs`, audit paket/font menghentikan run). PowerShell tetap runner lokal.

~~~bash
python3 -m venv .venv && .venv/bin/pip install -r handoff/requirements-cloud.txt
python3 handoff/vectally.py Status
python3 handoff/vectally.py Doctor
python3 handoff/vectally.py Audit                       # exit 2: blocker S06 Asap heavy (diharapkan)
python3 handoff/vectally.py BuildGraphics --codes S03
python3 handoff/vectally.py Compose --codes S04
python3 handoff/vectally.py Verify --all-supported      # rebuild di salinan sementara, bandingkan dgn paket tersimpan
~~~

Path: resep membaca `VECTALLY_ROOT` dan `VECTALLY_SOURCES` lewat `work/vpaths.py` (default root repo dan `sources/VECTALLY`). Di PowerShell: `-SourceRoot <folder>`. Font Windows hanya dipakai untuk LABEL LAPORAN; di luar Windows diganti DejaVu Sans Bold (atau `VECTALLY_REPORT_FONT`). Font COPY DESAIN tidak tersentuh.
