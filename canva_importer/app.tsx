// CUSBE Native Importer (tahap 2)
// Baca CANVA_PACKAGE.json dari program rebuild -> susun semua elemen di halaman Canva:
// shape asli (warna bisa diganti), teks asli (bisa diketik), gambar (bisa diganti).
import { Button, Rows, Text } from "@canva/app-ui-kit";
import { addElementAtPoint, addPage } from "@canva/design";
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const parsePkg = async (f: File): Promise<Pkg> => {
  const p = JSON.parse(await readText(f)) as Pkg;
  if (p.format !== "cusbe-canva-package" || !Array.isArray(p.elements)) {
    throw new Error("bukan file CANVA_PACKAGE.json dari program rebuild");
  }
  return p;
};

export const App = () => {
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const onFiles = async (list: FileList | null) => {
    setErrors([]);
    setLog([]);
    setPkgs([]);
    if (!list) return;
    const ok: Pkg[] = [];
    const bad: string[] = [];
    for (const f of Array.from(list)) {
      try {
        ok.push(await parsePkg(f));
      } catch (e) {
        bad.push(`${f.name}: ${String(e)}`);
      }
    }
    setPkgs(ok);
    setErrors(bad);
  };

  // current page (single package, old behaviour)
  const assembleHere = async (pkg: Pkg) => {
    const fails: string[] = [];
    for (const e of pkg.elements) {
      try {
        await addElementAtPoint(toCanva(e));
      } catch (err) {
        fails.push(`GAGAL ${e.name} (${e.type}): ${String(err)}`);
      }
    }
    return fails;
  };

  // every package -> its own new page, with its own size, all elements in one call
  const assembleAsPages = async () => {
    setBusy(true);
    const out: string[] = [];
    let done = 0;
    for (let i = 0; i < pkgs.length; i++) {
      const p = pkgs[i];
      setLog([`Halaman ${i + 1}/${pkgs.length}: ${p.source}...`, ...out]);
      try {
        await addPage({
          title: p.source.slice(0, 255),
          dimensions: { width: p.width, height: p.height },
          elements: p.elements.map(toCanva),
        } as any);
        done++;
      } catch (err) {
        // fallback: empty page first, then the elements one by one onto it
        try {
          await addPage({ title: p.source.slice(0, 255), dimensions: { width: p.width, height: p.height } } as any);
          await sleep(600);
          const fails = await assembleHere(p);
          done++;
          out.push(`${p.source}: disusun per elemen (${String(err).slice(0, 80)})`);
          fails.forEach((f) => out.push(`${p.source}: ${f}`));
        } catch (err2) {
          out.push(`GAGAL ${p.source}: ${String(err2)}`);
        }
      }
      await sleep(1100); // Canva limit: 10 halaman / 10 detik
    }
    setLog([`Selesai: ${done} dari ${pkgs.length} desain jadi halaman baru.`, ...out]);
    setBusy(false);
  };

  const onlyOne = async () => {
    setBusy(true);
    const fails = await assembleHere(pkgs[0]);
    setLog([`Selesai: ${pkgs[0].elements.length - fails.length} dari ${pkgs[0].elements.length} elemen.`, ...fails]);
    setBusy(false);
  };

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Text>CUSBE Native Importer</Text>
        <Text size="small">
          Pilih SATU atau BANYAK file CANVA_PACKAGE.json (tahan Ctrl untuk pilih banyak). Setiap desain
          jadi halaman baru dengan ukuran aslinya.
        </Text>
        <input type="file" multiple accept=".json,application/json" onChange={(e) => onFiles(e.target.files)} />
        {errors.map((m, i) => (
          <Text key={"e" + i} size="small" tone="critical">
            {m}
          </Text>
        ))}
        {pkgs.length > 0 && (
          <Rows spacing="1u">
            <Text>{pkgs.length} desain dipilih</Text>
            {pkgs.map((p, i) => (
              <Text key={"p" + i} size="small">
                - {p.source} ({p.width}x{p.height}): {p.summary.shape} shape, {p.summary.text} teks, {p.summary.image} gambar
              </Text>
            ))}
            <Button variant="primary" onClick={assembleAsPages} disabled={busy} loading={busy} stretch>
              Susun semua (1 desain = 1 halaman baru)
            </Button>
            {pkgs.length === 1 && (
              <Button variant="secondary" onClick={onlyOne} disabled={busy} stretch>
                Susun di halaman yang sedang dibuka
              </Button>
            )}
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
