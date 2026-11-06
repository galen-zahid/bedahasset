// CUSBE Native Importer - TAHAP 1 (uji kelayakan)
// Menguji: (1) foto dari file lokal, (2) shape poligon asli (pita), (3) teks asli,
// semuanya di posisi tertentu, dan urutan tumpukannya (foto -> pita -> teks).
// Pakai di desain ukuran 1122 x 1402 px (ukuran KINRAVA A01).
import { Button, Rows, Text } from "@canva/app-ui-kit";
import { addElementAtPoint } from "@canva/design";
import { useState } from "react";
import * as styles from "styles/components.css";

const readAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });

export const App = () => {
  const [log, setLog] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const say = (m: string) => setLog((l) => [...l, m]);

  const run = async () => {
    setLog([]);
    // 1) FOTO (paling bawah)
    if (file) {
      try {
        const dataUrl = await readAsDataUrl(file);
        await addElementAtPoint({
          type: "image",
          dataUrl,
          altText: { text: "photo module", decorative: false },
          top: 0,
          left: 0,
          width: 1122,
          height: 1402,
        });
        say("OK  foto");
      } catch (e) {
        say("GAGAL foto: " + String(e));
      }
    } else {
      say("(lewati foto: belum pilih file)");
    }
    // 2) PITA = shape poligon asli (warna bisa diganti)
    try {
      await addElementAtPoint({
        type: "shape",
        paths: [{ d: "M 0 0 L 796.5 626.2 L 732.4 707.8 L 0 132.1 Z", fill: { color: "#f0471d" } }],
        viewBox: { top: 0, left: 0, width: 796.5, height: 707.8 },
        top: 233.7,
        left: 0,
        width: 796.5,
        height: 707.8,
      });
      say("OK  pita (shape)");
    } catch (e) {
      say("GAGAL pita: " + String(e));
    }
    // 3) TEKS asli (paling atas)
    try {
      await addElementAtPoint({
        type: "text",
        children: ["BUILT IN THE"],
        top: 111,
        left: 640,
        width: 460,
        fontSize: 110,
        fontWeight: "bold",
        color: "#f7f2e7",
        textAlign: "start",
      });
      say("OK  teks");
    } catch (e) {
      say("GAGAL teks: " + String(e));
    }
    say("Selesai. Cek: posisi, urutan (foto bawah, pita tengah, teks atas), dan apakah bisa diedit.");
  };

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Text>CUSBE Importer - uji tahap 1 (desain 1122 x 1402)</Text>
        <input type="file" accept="image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button variant="primary" onClick={run} stretch>
          Tes: tambah foto + pita + teks
        </Button>
        {log.map((m, i) => (
          <Text key={i} size="small">
            {m}
          </Text>
        ))}
      </Rows>
    </div>
  );
};
