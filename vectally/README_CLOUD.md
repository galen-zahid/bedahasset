**Input untuk Claude Code cloud**

Paket cloud memuat handoff sebelumnya, seluruh84 PNG asli, manifest checksum, font, resep, bukti, source app lengkap dan panduan ini. Tidak perlu menambahkan training.zip atau mengunggah ulang semua file satu per satu.

Untuk Claude Code di claude.ai/code, ekstrak isi paket ke repository yang dipilih sesi tersebut. Jangan hanya menyebut lokasi C:/D: dari komputer asal. Cloud bekerja dengan file yang benar-benar ada dalam workspace/repository-nya.

Dokumentasi resmi:
https://code.claude.com/docs/en/claude-code-on-the-web

Struktur penting:

~~~text
README_CLOUD.md
CLAUDE.md
handoff/CLOUD_PROMPT.txt
handoff/CLOUD_SOURCES.json
handoff/cloud_audit.py
handoff/requirements-cloud.txt
handoff/REPORT_VECTALLY.md
handoff/STATE.json
sources/VECTALLY/Feed/*.png
sources/VECTALLY/Story/*.png
sources/VECTALLY/Highlight/*.png
work/
outputs/
app-source/
~~~

Mulai dengan:

~~~bash
python3 handoff/cloud_audit.py
~~~

Audit ini hanya memerlukan standard library Python. Semua84 sumber harus cocok. Exit2 dengan blocker font S06 adalah hasil yang diharapkan, bukan alasan mengubah aturan agar lolos.

Dependency builder gambar dicantumkan dalam handoff/requirements-cloud.txt. Instal di environment cloud yang diizinkan sebelum rebuild:

~~~bash
python3 -m pip install -r handoff/requirements-cloud.txt
~~~

Runner PowerShell asli masih khusus setup lokal. Jangan menganggap powershell.exe atau D:/bedahasset/.venv tersedia di cloud. Gunakan pwsh bila environment memang menyediakannya, atau port runner ke Python/Node dengan job manifest yang sama. Yang perlu otomatis adalah pekerjaan deterministiknya, bukan harus memakai satu jenis shell.

Resep lama juga masih memiliki path sumber Windows dan sebagian path font UI Windows. Sebelum rebuild, port input ke sources/VECTALLY dan output ke root repo. Font Windows yang dipakai untuk LABEL LAPORAN boleh diganti font report yang tersedia; font pada COPY DESAIN tetap harus mengikuti constraint pengguna dan divalidasi. Jangan membuat fallback font desain diam-diam.

Source app di app-source disalin dari proyek D:/cusbe-importer dengan src/styles/scripts/declarations dan config build. node_modules, .env, .npmrc dan credential tidak disertakan. handoff/app-source adalah snapshot sebagian dari paket sebelumnya; gunakan app-source untuk perubahan app selanjutnya.

Koneksi Canva dan CUSBE komputer asal tidak ikut dalam file. Link desain hanya referensi, bukan session login atau hak edit. Jika ingin memperbarui Canva langsung, hubungkan akses/tool Canva yang sesuai pada sesi cloud. Jangan memberikan password/cookie sebagai isi prompt atau ZIP.

Ukuran seluruh sumber melebihi100MB. Jalur upload local-repository bundle pada CLI Claude memiliki batas100MB menurut dokumentasi yang diperiksa; untuk kumpulan lengkap ini gunakan repo GitHub yang dikloning sesi cloud. Jangan commit ZIP besar ini sebagai satu file; ekstrak file-file di dalamnya ke repo.

Status paused dalam STATE adalah kondisi saat handoff. Jika pengguna mengirim CLOUD_PROMPT.txt sebagai instruksi baru untuk melanjutkan, itu permintaan kelanjutan; jangan menafsirkan snapshot paused sebagai larangan permanen.
