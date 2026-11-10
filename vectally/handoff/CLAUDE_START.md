**Mulai di sini — handoff VECTALLY untuk Claude Code**

Tujuan pengguna tetap 84 VECTALLY (48 Feed, 30 Story, 6 Highlight), satu koleksi/link final, aset vector editable per objek, copy dapat diketik ulang, font dan transform mendekati sumber sesuai persetujuan hybrid. Dorvan/Kinrava belum dimulai. Goal sedang PAUSED oleh pengguna. Jangan otomatis melanjutkan rebuild atau mengubah Canva hanya karena membaca handoff ini.

Workspace:
C:/Users/HP/Documents/Codex/2026-11-07/files-mentioned-by-the-user-training

Baca berurutan:

1. REPORT_VECTALLY.md — laporan metode, keputusan, batas dan kegagalan.
2. STATE.json — snapshot terbaru. Ini mengoreksi status lama yang tertinggal.
3. VECTALLY_STATUS.csv — semua 84 sumber, hash, dan status konservatif.
4. POWERSHELL.md dan jobs.json — kemampuan runner yang benar-benar tersedia.
5. Bukti aktual di outputs/VECTALLY-story-repair dan outputs/VECTALLY-native-font-runtime.

**Status yang tidak boleh disalahartikan**

- 17 sumber sudah punya suatu bentuk draft di Canva, BUKAN 17 halaman final.
- 67 sumber belum siap. Tidak ada sertifikasi lengkap tiga gerbang final pada handoff ini.
- Label lama CANVA_NATIVE_TEXT_VERIFIED tidak berarti semua copy/transform sudah 1:1.
- S06 sudah 47 bentuk native, 3 grup, 8 teks native; tetapi Asap heavy tidak tersedia di katalog akun. Importer v4 akan menolak impor ulang kandidat itu. Jangan menurunkan validasi atau diam-diam mengganti ke Bold.
- Prototype memiliki 20 halaman karena ada halaman probe dan versi S01 lama. Itu bukan 20 desain sumber yang selesai.

**Langkah awal tanpa mengubah Canva**

~~~powershell
Set-Location 'C:/Users/HP/Documents/Codex/2026-11-07/files-mentioned-by-the-user-training'
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Status
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Doctor
powershell -NoProfile -File ./handoff/Vectally.ps1 -Action Audit
~~~

Audit boleh berakhir exit2: itu menandakan blocker paket/font yang nyata. Jangan mengubahnya menjadi sukses palsu. Jangan menjalankan BuildGraphics/Compose sebelum pengguna meminta kelanjutan.

**Setelah pengguna melanjutkan**

- Prioritas tipografi: selesaikan font face yang tersedia. Varian Google Fonts lokal tidak otomatis sama dengan varian Canva. Asap native saat audit hanya sampai Bold, bukan Black900. League Gothic condensed75 belum tersedia native.
- Pertahankan keluarga League Gothic, Archivo Black, Asap yang diminta; jangan mengambil font lain tanpa keputusan yang jelas.
- Ordinary copy native. Display yang masih bisa dicapai dengan font/size/spacing/rotate tetap native. Distorsi sesungguhnya memakai TypeCraft yang dapat diedit melalui Edit → Update, sesuai persetujuan pengguna. Jangan memakai SVG copy statis sebagai pengganti.
- Lanjutkan resep objek S07–S30 dan Feed lainnya. Setiap resep baru harus punya inventory semantic, rekonstruksi bagian tertutup, paket, audit dan render.
- Jalankan pekerjaan deterministik lewat runner; gunakan AI/manusia untuk pengertian objek, geometri yang tersembunyi, dan penilaian visual.
- Jangan menganggap ekspor lokal sama dengan ekspor Canva. Periksa actual native structure, actual PNG, perbandingan sumber, dan buyer test.

**Sesi Canva terakhir — tidak menjamin tab/session tetap hidup**

Main11page draft:
https://www.canva.com/design/DAHaawX9Fm8/q-iGCT-epdpWj0UB7AXKGA/edit

Isolated20page prototype:
https://www.canva.com/design/DAHabUK1x7c/XAKU7ev4LnkxUjedsUkoGw/edit

App:
D:/cusbe-importer

Private draft code upload:
https://www.canva.com/developers/app/AAHOGHKNaHM/version/1/code-upload

Importer saat pause memuat PROBE penolakan Asap heavy, lalu font paketnya dipilih Asap Condensed untuk membaca metadata. Jangan menekan assemble sebelum mengganti file dengan paket yang benar. Pemilihan ini tidak menyisipkan elemen ke desain.

Pengguna menolak OS computer use/desktop takeover. Gunakan file, terminal, connector atau browser terisolasi yang diizinkan; jangan ganggu desktop aktif. Jangan membaca private React state, menebak endpoint, mengekstrak token, atau mengakali capability lock CUSBE. Jika gateway benar-benar terkunci, jangan pindah namespace demi bypass. Tidak ada izin mengirim email/chat atau memublikasikan app.

**Definisi selesai**

Seluruh84 sumber terpetakan dan tervalidasi; semua objek memiliki ownership/grup yang benar dan bentuk utuh; teks penting benar-benar dapat diedit melalui workflow yang disetujui; font/transform dan warna ditinjau terhadap sumber; tidak ada crack/objek hilang; tiga gerbang Structure/Fidelity/Buyer terbukti; EDIT GUIDE ada; koleksi/link final benar dan akses pengguna terbukti. Jika salah satu belum terbukti, jangan sebut 100%.
