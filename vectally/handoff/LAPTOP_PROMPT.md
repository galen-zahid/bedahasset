# Prompt pindah ke sesi LAPTOP (Claude Code lokal, Windows)

Salin semua teks di bawah garis ke sesi Claude Code yang berjalan di laptop
(buka PowerShell di `D:\bedahasset`, jalankan `claude`, lalu tempel).

---

Lanjutkan proyek VECTALLY dari sesi cloud. **Jangan mulai dari nol.** Balas saya dalam bahasa Indonesian, santai, dan ringkas. Sebelum kerja besar, diskusikan dulu kalau saya minta diskusi. Jangan setengah jadi, dan jangan boros limit.

## 0. Sinkronisasi dulu
```powershell
cd D:\bedahasset
git fetch origin ccr-6e448746-jedgxp
git checkout ccr-6e448746-jedgxp
git pull origin ccr-6e448746-jedgxp
```
Commit terakhir dari cloud adalah `a183c52` (snapshot VECTALLY plus port path). Semua pekerjaan VECTALLY ada di folder `vectally\`.

Baca dalam urutan ini:
1. `vectally\CLAUDE.md`
2. `vectally\README_CLOUD.md`
3. `vectally\handoff\REPORT_VECTALLY.md`
4. `vectally\handoff\STATE.json`
5. `vectally\handoff\VECTALLY_STATUS.csv`
6. `vectally\handoff\CLOUD_SESSION_LOG.md` (hasil sesi cloud)
7. `vectally\handoff\jobs.json`
8. `vectally\handoff\POWERSHELL.md`

## 1a. Riwayat singkat seluruh sesi sebelumnya
1. Awalnya kita membuat CLI `split.py` dan pipeline untuk membedah desain PNG flat buatan AI (KINRAVA, DORVAN, VECTALLY) menjadi layer yang bisa diedit.
2. Pipeline itu berkembang jadi mode **rebuild** (`pipeline\rebuild\`):
   - background foto dibersihkan dengan satu kali inpaint (pita lama dan atlet dihapus tanpa bekas);
   - vektor jadi shape native Canva;
   - teks jadi teks native.
3. Setup laptop yang sudah beres:
   - `setup.bat`: reportlab, wordninja, vtracer, resvg;
   - node v22.16.0 dan npm 10.9.2;
   - `@canva/cli`, sudah `canva login`.
4. App dibuat dengan `--distribution=public`, karena app private butuh Canva Enterprise.
5. Uji di Canva:
   - Tahap 1 OK (foto, pita, teks).
   - Tahap 2: 15/15 elemen OK. Ada masalah background (sisa stripe dan bekas atlet), lalu diperbaiki.
6. Importer diubah supaya bisa memilih banyak file, dan setiap desain jadi satu halaman baru.
7. Saya menjalankan batch 18 desain di laptop: 18 ok, butuh sekitar 35 menit. Paketnya dikumpulkan di `D:\bedahasset\paket`.
   - Setelah itu tombol "Susun semua" tidak muncul. Penyebabnya server lama masih memegang port 8080. Solusinya matikan proses itu, jalankan `canva apps start` lagi, lalu reload app.
8. Setelah itu datang snapshot VECTALLY dari Google Drive (`VECTALLY_CLOUD_INPUT_20261110.zip`). Isinya sudah diekstrak ke folder `vectally\` di repo dan dilanjutkan di sesi cloud (lihat bagian 4).

## 1. Konteks proyek
- **Pipeline rebuild** (`pipeline\rebuild\*`, CLI `split.py`) mengubah desain PNG flat menjadi `CANVA_PACKAGE.json`, berisi shape native, teks native, dan gambar.
- **CUSBE Native Importer** adalah app Canva (Apps SDK) di `D:\cusbe-importer`. Sumbernya ada di `canva_importer\app.tsx` di repo.
  - App ID: `AAHOGHKNaHM`. Distribusinya public, tapi app tetap draft dan **jangan dipublikasikan**.
  - Jalankan dengan `canva apps start` di `D:\cusbe-importer`, yang melayani `localhost:8080`, lalu buka Preview dari Developer Portal.
  - Kalau port 8080 sudah dipakai, matikan proses lama dulu (`netstat -ano | findstr :8080`, lalu `taskkill /PID <pid> /F`).
  - App bisa memilih banyak `CANVA_PACKAGE.json` sekaligus, dan setiap file jadi satu halaman baru lewat `addPage` (batas 10 halaman per 10 detik).
  - Sumber app yang lengkap ada di `vectally\app-source`. Folder `vectally\handoff\app-source` hanya snapshot lama.
- Sudah terbukti di Canva:
  - Tahap 1 (teks, shape, foto; warna dan isi teks bisa diganti) dan tahap 2 (15/15 elemen) lolos.
  - Batch 18 desain (KINRAVA, DORVAN, VECTALLY) hasilnya 18 ok dan 0 gagal. Paketnya dikumpulkan di `D:\bedahasset\paket`.
  - Masukan saya untuk impor 18 desain itu **belum diberikan**.

## 2. Target VECTALLY
- **84 sumber:** 48 Feed, 30 Story, 6 Highlight, ditambah halaman EDIT GUIDE.
- Status sekarang: **0 final, 17 punya draft Canva, 67 belum siap.**
- Desain di Canva:
  - Desain utama `DAHaawX9Fm8` (11 halaman).
  - Desain uji `DAHabUK1x7c` (20 halaman). S01–S06 ada di halaman 3 dan 8–13, H01–H06 di halaman 15–20.
- **Jangan bilang 100%** sebelum struktur, fidelity terhadap sumber, dan buyer edit-test semuanya terbukti.

## 3. Aturan wajib
- Kelompokkan per aset, bukan per warna.
- Badan benda harus utuh, termasuk bagian yang tertutup objek lain.
- Shadow dan highlight ikut grup asetnya.
- Kebijakan copy (hybrid, sudah disetujui):
  - Copy biasa dibuat sebagai teks native.
  - Display type juga native kalau font, ukuran, spasi, dan rotasi bisa mencapainya.
  - Warp yang sungguhan pakai TypeCraft (Edit → Update).
  - SVG polos hanya untuk dekorasi yang bukan copy.
- **Jangan** ubah copy jadi vektor statis atau raster.
- **Jangan** matikan validasi font, dan jangan ganti font diam-diam.
- Katalog font (`handoff\FONT_CATALOGUE.json`):
  - Asap: normal, medium, semibold, bold.
  - Asap Condensed: normal, bold.
  - Archivo Black: normal saja.
- **S06 Asap heavy memang diblokir.** Guard-nya jangan diturunkan.
- Jangan impor paket eksperimen hanya untuk mengejar log sukses.
- Kerja deterministik dijalankan lewat script dan `jobs.json`, bukan dikerjakan ulang manual per objek.
- Jangan commit ZIP besar sebagai satu file.
- Jangan masukkan password atau cookie ke prompt.
- Jangan kirim pesan ke orang lain.
- Saya **menolak** desktop takeover dan pertanyaan izin yang berulang-ulang.
- DORVAN dan KINRAVA dikerjakan **setelah** VECTALLY selesai.

## 4. Yang sudah dikerjakan di cloud (jangan diulang)
- `python handoff\cloud_audit.py`: 84/84 hash cocok. Satu-satunya blocker adalah S06 (`FONT_VARIANT_UNAVAILABLE Asap heavy`), sesuai harapan.
- 23 resep di `vectally\work\` sudah diport.
  - Path sumber tidak lagi `D:\download\VECTALLY` tapi lewat `work\vpaths.py`, dengan env `VECTALLY_ROOT` dan `VECTALLY_SOURCES`. Default-nya root repo dan `sources\VECTALLY`.
  - Font Segoe hanya dipakai untuk label laporan.
- Runner Python lintas platform `handoff\vectally.py` memakai `jobs.json` yang sama. Perintahnya: Status, Doctor, Audit, BuildGraphics, Compose, Compare, Verify.
- `Vectally.ps1` tetap jadi runner lokal. Sudah ditambah `-SourceRoot` dan pengaturan `VECTALLY_ROOT`. **Belum dites karena cloud tidak punya pwsh. Tes ini paling awal.**
- Hasil reproduksi:
  - S01, S03, S04: identik byte per byte.
  - S02, S06: hasil render identik, 0 piksel beda (urutan titik berbeda, kemungkinan karena versi numpy).
- Compose untuk S06 menghitung tinggi teks 73.8/69, sedangkan paket kurasi memakai tinggi asli Canva 73.3/68.5. **Jangan timpa paket S06 dengan output Compose.** Catatannya ada di `jobs.json`.
- Canva **tidak diubah** dari cloud.
  - Konektor Canva di cloud tidak bisa memilih font family. `add_text`/`format_text` hanya punya bold/normal/italic, jadi impor lewat konektor = ganti font diam-diam. Karena itu impor teks harus lewat CUSBE (Apps SDK, `fontRef`).
  - Konektor bisa `insert_shape` (1 path, 1 warna per shape), `group_elements`, `replace_text`, dan `insert_fill`.
  - Ide yang belum diuji: `replace_text` pada kotak teks yang font-nya sudah benar mungkin mempertahankan font-nya.

## 5. Langkah pertama di laptop
1. Tes runner PowerShell:
   ```powershell
   cd D:\bedahasset\vectally
   pwsh -File handoff\Vectally.ps1 -Action Doctor
   pwsh -File handoff\Vectally.ps1 -Action Audit
   ```
   Kalau `pwsh` tidak ada, pakai `powershell -ExecutionPolicy Bypass -File ...`.
   Hasil yang diharapkan: exit 2 dengan satu-satunya blocker S06. Bandingkan dengan `python handoff\vectally.py Audit`.
2. Tanyakan keputusan saya soal S06 Asap heavy, salah satu dari:
   - (a) upload Asap Black/900 ke Kit Merek;
   - (b) sengaja pakai Asap bold dengan selisih ketebalan yang diterima;
   - (c) tunda S06.
3. Lanjutkan sesuai prioritas di REPORT_VECTALLY:
   1. Rapikan font face native.
   2. Selesaikan headline/copy S01–S05 dan fidelity S06, tanpa merusak aset yang sudah bagus.
   3. Buat inventaris dan resep untuk S07–S30 dan 43 Feed sisanya.
      - S07 sudah diamati: kurva perjalanan di belakang 3 penanda, grafik pertumbuhan, 2 ikon dokumen, pita "THREE", dan 2 aksen hijau.
   4. Pulihkan gradien.
   5. Jalankan buyer edit-test.
   6. Satukan 84 halaman plus EDIT GUIDE.
   7. Verifikasi link final dan akses saya.
4. Impor ke Canva lewat CUSBE.
   - Sebelum menulis ke Canva, cek dulu koneksi atau tool yang benar-benar tersedia.
   - Jangan klaim Canva sudah diperbarui kalau belum ada bukti, misalnya screenshot atau hasil read-design.

## 5b. Lampiran
Tidak ada yang perlu dilampirkan selain prompt ini. Semuanya sudah ada di disk atau di git:
- Di git (`git pull`):
  - sumber 84 PNG (`vectally\sources\VECTALLY`);
  - handoff, resep, font, dan paket kandidat;
  - source app;
  - pipeline dan importer.
- Di laptop (bukan di git):
  - `D:\cusbe-importer`, proyek app Canva yang dijalankan;
  - `D:\bedahasset\paket`, hasil batch 18 desain;
  - login Canva CLI.

ZIP dari Google Drive tidak perlu diunduh lagi karena isinya sudah ada di repo.

## 6. Cara kerja dengan saya
- Kasih perintah PowerShell lengkap dengan `cd`-nya, supaya saya bisa jalankan sendiri.
- Commit dan push ke branch `ccr-6e448746-jedgxp` setiap selesai satu bagian yang jelas.
