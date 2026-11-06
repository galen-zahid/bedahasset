// CUSBE Native Importer (tahap 2)
// Baca CANVA_PACKAGE.json dari program rebuild -> susun semua elemen di halaman Canva:
// shape asli (warna bisa diganti), teks asli (bisa diketik), gambar (bisa diganti).
import { Button, Rows, Text } from "@canva/app-ui-kit";
import { addElementAtPoint } from "@canva/design";
import { useState } from "react";
import * as styles from "styles/components.css";

type El = {
  type: "shape" | "text" | "image";
  name: string;
  left: number;
  top: number;
  width: number;
  height?: number;
  // shape
  paths?: { d: string; fill: { color: string } }[];
  viewBox?: { left: number; top: number; width: number; height: number };
  // text
  text?: string;
  fontSize?: number;
  color?: string;
  fontWeight?: string;
  textAlign?: string;
  // image
  dataUrl?: string;
};

type Pkg = {
  format: string;
  version: number;
  source: string;
  width: number;
  height: number;
  elements: El[];
  warnings: string[];
  summary: { shape: number; image: number; text: number };
};

const readText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(file);
  });

const toCanva = (e: El): any => {
  if (e.type === "shape") {
    return {
      type: "shape",
      paths: e.paths,
      viewBox: e.viewBox,
      top: e.top,
      left: e.left,
      width: e.width,
      height: e.height,
    };
  }
  if (e.type === "text") {
    return {
      type: "text",
      children: [e.text ?? ""],
      top: e.top,
      left: e.left,
      width: e.width,
      fontSize: e.fontSize,
      color: e.color,
      fontWeight: e.fontWeight ?? "normal",
      textAlign: e.textAlign ?? "start",
    };
  }
  return {
    type: "image",
    dataUrl: e.dataUrl,
    altText: { text: e.name, decorative: false },
    top: e.top,
    left: e.left,
    width: e.width,
    height: e.height,
  };
};

export const App = () => {
  const [pkg, setPkg] = useState<Pkg | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const onFile = async (f: File | undefined) => {
    setError("");
    setLog([]);
    setPkg(null);
    if (!f) return;
    try {
      const p = JSON.parse(await readText(f)) as Pkg;
      if (p.format !== "cusbe-canva-package" || !Array.isArray(p.elements)) {
        throw new Error("bukan file CANVA_PACKAGE.json dari program rebuild");
      }
      setPkg(p);
    } catch (e) {
      setError("File tidak valid: " + String(e));
    }
  };

  const assemble = async () => {
    if (!pkg) return;
    setBusy(true);
    const out: string[] = [];
    let ok = 0;
    for (let i = 0; i < pkg.elements.length; i++) {
      const e = pkg.elements[i];
      try {
        await addElementAtPoint(toCanva(e));
        ok++;
      } catch (err) {
        out.push(`GAGAL ${e.name} (${e.type}): ${String(err)}`);
      }
      setLog([`Menyusun ${i + 1}/${pkg.elements.length}...`, ...out]);
    }
    setLog([`Selesai: ${ok} dari ${pkg.elements.length} elemen berhasil.`, ...out]);
    setBusy(false);
  };

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Text>CUSBE Native Importer</Text>
        <Text size="small">
          1) Buat desain dengan ukuran yang tertulis di bawah setelah memilih file. 2) Pilih
          CANVA_PACKAGE.json dari folder out\nama_desain. 3) Klik Susun.
        </Text>
        <input type="file" accept=".json,application/json" onChange={(e) => onFile(e.target.files?.[0])} />
        {error && <Text tone="critical">{error}</Text>}
        {pkg && (
          <Rows spacing="1u">
            <Text>
              {pkg.source} - ukuran desain {pkg.width} x {pkg.height} px
            </Text>
            <Text size="small">
              {pkg.summary.shape} shape asli, {pkg.summary.text} teks asli, {pkg.summary.image} gambar
            </Text>
            {pkg.warnings.map((w, i) => (
              <Text key={i} size="small" tone="tertiary">
                - {w}
              </Text>
            ))}
            <Button variant="primary" onClick={assemble} disabled={busy} loading={busy} stretch>
              Susun di halaman ini
            </Button>
          </Rows>
        )}
        {log.map((m, i) => (
          <Text key={i} size="small">
            {m}
          </Text>
        ))}
      </Rows>
    </div>
  );
};
