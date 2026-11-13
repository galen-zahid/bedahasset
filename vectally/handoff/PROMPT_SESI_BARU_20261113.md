# Prompt sesi baru: VECTALLY (lanjutan 13 Nov 2026)

Salin semua di bawah garis ke sesi baru.

---

Lanjutkan proyek VECTALLY di `D:\bedahasset\vectally`, branch git `ccr-6e448746-jedgxp`, commit terakhir `b28703a`. Saya designer, bukan programmer. Jawab dalam Bahasa Indonesia, ringkas, dan kritis. Eksekusi langsung kalau aman. Status harus jujur: SOURCE WRITTEN / RENDERED / TECHNICAL PASS / VISUAL PASS / USER APPROVED.

## Tujuan
Ada 84 desain PNG VECTALLY (Feed A01–A?, Story S01–S?, Highlight H01–H?) di `vectally\sources\VECTALLY\`. Semuanya mau dijadikan template Canva yang editable:
- aset berupa shape native, tanpa PNG;
- teks bisa diketik;
- headline memakai TypeCraft (bisa miring dan tebal, tetap bisa diketik).

Semuanya dijalankan lewat **satu command PowerShell, tanpa AI saat berjalan**. AI hanya dipakai sekali per desain untuk menulis resep.

## Metode yang sudah disepakati (gaya Codex)
Kualitas Codex berasal dari **resep per desain yang ditulis tangan**: poligon, kurva dan primitif yang diukur dari sumber, satu grup per benda fisik. Bukan dari jiplak otomatis. Batch otomatis lama dan mesin inventory (`work\inventory_engine.py`) hasilnya kalah, dan user menilai jelek. Jangan dipakai lagi sebagai jalur utama.

- **Mesin Codex disalin** ke `recipes\codex_scene.py` (Scene, ink, export), dari `D:\bedahasset\VECTALLY_CODEX_TOOLKIT_20261112\engine\vector_batch.py`.
- **Alat ukur** `recipes\measure.py` mengeluarkan titik sudut poligon per warna dari PNG sumber. Pakai ini untuk menulis resep.
- **Contoh resep lengkap:** `recipes\a09.py`. Isinya pecahan latar, plat, angka 3 3D, kartu ikon dengan primitif (rrot, bar, arcband, ellipse), dan huruf di-outline dari sumber sebagai aset `lettering`.
- **Teks native:** `recipes\codex_native.py` (FONTS, fit_text, measure_box, export_native) disalin dari Codex `vectally_approved_native.py`. Teks bertanda `typecraft=` tidak masuk paket, karena dibuat robot.
- **Titik sudut TypeCraft:** `recipes\typecraft_quads.py <KODE>` mengukur 4 titik sudut tinta headline dari sumber. Teks lurus memakai `rect=True`. Spesifikasinya di dict `HEADLINES`.
- **Font brand terkunci:** League Gothic (display), Archivo Black (impact), Asap (body). Di TypeCraft dipakai "League Gothic Condensed Regular".
- **10 kode sudah punya resep Codex di toolkit:** A03, A07, A20, A27, A45, S01–S04, S06. Pakai resep itu, jangan dibuat ulang.
- **Folder Codex hanya dibaca, jangan diubah:** `D:\bedahasset\VECTALLY_CODEX_TOOLKIT_20261112`, `C:\Users\HP\Documents\Codex\...`, `D:\Codex\cusbe-remote-mcp`. Pengecualian: folder upload `uploads\vectally-recipes\`.

## Robot Canva (sudah jalan)
- `robot\canva_robot.mjs` dibangkitkan oleh `robot\_build_robot.py`. **Edit `_build_robot.py`, lalu jalankan ulang.** Robot ini dikembangkan dari robot Codex `a07_fresh_gateway.mjs`. Isinya: buat desain baru, drop paket ke app `cusbe-importer`, lalu "Susun", lalu N TypeCraft (Distorsi kustom 10 titik memakai `robot\typecraft_mesh.mjs`), atur posisi X/Y/Lebar, lalu ekspor PNG ke `D:\download`.
- `robot\prepare_job.py <KODE> [--outline '{"*":6}' | '{"NEED":9}'] [--box-json file]` menulis `outputs\VECTALLY-canva\<KODE>\JOB.json` dan menyalin paket ke gateway uploads.
- **Satu command:** `vectally\Run-Canva.ps1 -Code A09`, yang menjalankan resep, titik sudut, job, lalu robot.
- **Cara menjalankan robot manual:**
  ```
  cd D:\bedahasset\vectally
  $env:CUSBE_GATEWAY_ROOT='D:/Codex/cusbe-remote-mcp'
  & 'D:\Node js\node.exe' robot\canva_robot.mjs outputs\VECTALLY-canva\A09\JOB.json --full
  ```
  Jalankan di latar belakang, karena satu run bisa memakan beberapa menit. Bukti tiap run tersimpan di `outputs\VECTALLY-canva\A09\runs\<waktu>\`: FULL_RESULT.json, CANVA_EXPORT.png, *_MESH.json, atau FAILED.json kalau gagal.
- **Syarat sebelum robot jalan:**
  - Akses privileged CUSBE dibuka oleh user sendiri: `& 'D:\Codex\cusbe-remote-mcp\scripts\Authorize-Privileged.ps1' -Minutes 1440`. Claude tidak boleh membukanya sendiri.
  - Chrome profil **"Work"** (folder `Profile 3`) terbuka dan sudah login Canva, dengan ekstensi Playwright aktif. Claude boleh membukanya dengan `chrome.exe --profile-directory="Profile 3"`.
  - Gateway butuh sekitar 64 detik untuk menyala. Sambungan browser kadang habis waktu di percobaan pertama. Tunggu sekitar 20 detik lalu ulangi.
- **Perbaikan yang sudah ada di robot:**
  - Batas tunggu nyala gateway 240 detik.
  - Ukuran browser diatur ke 1500×1000.
  - Tab dibawa ke depan, dan drop dicoba ulang kalau gagal.
  - Judul desain opsional.
  - Teks terang diberi distorsi saat masih berwarna gelap, lalu warnanya diganti lewat "Perbarui elemen".
  - Titik pegangan 2×5 dengan penebakan titik yang tertutup huruf, plus pelacakan posisi.
  - Pilihan elemen dilepas dengan mengklik tombol "Halaman".
  - Efek garis tepi lewat `setOutline` (preset tepi ke-2, Ketebalan 1–20), warnanya disamakan dengan huruf memakai `pickColorAt(1, ...)`.

## Status A09 (desain pilot)
- **Aset:** `outputs\VECTALLY-resep\A09\` (resep, 123 shape), dan versi native `A09-NATIVE\` (74 shape, 8 grup, 1 teks logo).
- **Canva tanpa tepi:** robot sukses, desain [DAHaxB2U5e4](https://www.canva.com/design/DAHaxB2U5e4/rfCmsb4QrPmnc0x4GP7w9g/edit). Posisi dan ukuran 4 headline (SIGNS, YOUR BOOKS, NEED, ATTENTION.) pas dengan sumber, tapi **tinta hanya 73–82% dari sumber** (terlalu tipis).
  - Radius tepi yang dibutuhkan, dalam px ekspor: SIGNS ~7,5, YOUR BOOKS ~2, NEED ≥8, ATTENTION. ~6,5.
  - Pembanding: `outputs\VECTALLY-canva\A09\CMP_sumber_canva_PASS1.png`.
- **Run kalibrasi tepi ketebalan 6 untuk semua headline:** SUKSES, desain [DAHayXlnVCM](https://www.canva.com/design/DAHayXlnVCM/oIdbD-pyz4s1H4eN1x7TMA/edit). Bukti di `outputs\VECTALLY-canva\A09\runs\2026-11-13T09-07-55-200Z\CANVA_EXPORT.png`. **BELUM DIUKUR.**

## Langkah berikutnya
1. Ukur `CANVA_EXPORT.png` run kalibrasi terhadap sumber, per headline: rasio tinta, IoU, dan kotak tinta. Pakai mask per warna dan ROI yang sama seperti di `typecraft_quads.py`.
2. Hitung ketebalan per headline. Ketebalan baru = 6 × (radius yang dibutuhkan / radius yang didapat). Kalau kotak tinta membesar karena tepi, koreksi lewat `--box-json`.
3. Jalankan ulang lewat `prepare_job.py A09 --outline '{...}'`, lalu robot. Tunjukkan perbandingan sumber vs Canva ke user, dan minta ACC.
4. Setelah A09 di-ACC: terapkan pola yang sama ke desain berikutnya. Tulis resep `recipes\<kode>.py` dan isi `HEADLINES` di `typecraft_quads.py`. Bangun pustaka benda (koin, map, struk, kartu ikon, jam) supaya bisa dipakai ulang.

## Catatan lain
- Di akun Canva user ada sekitar 17 desain uji bernama `VECTALLY A09 RESEP AUTO …` atau "Desain tanpa judul". Yang dipakai hanya DAHaxB2U5e4 dan DAHayXlnVCM. Jangan menghapus apa pun tanpa izin user.
- `robot\_explore.mjs` adalah skrip penjelajah UI TypeCraft yang hanya membaca. Dipakai untuk menemukan kontrol "Jarak antar-huruf" (range -1..1) dan "Efek garis tepi".
- Aturan global user ada di `C:\Users\HP\.claude\CLAUDE.md`: source-first, jangan menimpa file, biaya nol, minta izin sebelum publish atau hapus.
