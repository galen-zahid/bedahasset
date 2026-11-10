// CUSBE Native Importer (tahap 2)
// Baca CANVA_PACKAGE.json dari program rebuild -> susun semua elemen di halaman Canva:
// shape asli (warna bisa diganti), teks asli (bisa diketik), gambar (bisa diganti).
import { Button, Rows, Text } from "@canva/app-ui-kit";
import { addElementAtPoint, addPage, createRichtextRange } from "@canva/design";
import type { FontWeight } from "@canva/design";
import { findFonts, requestFontSelection } from "@canva/asset";
import { useState } from "react";
import * as styles from "styles/components.css";
import { inspectCurrentPage } from "./inspection";
import { applyNativeRepair, validatePlan } from "./native_repair";
import type { NativeRepairPlan } from "./native_repair";

type El = {
  type: "shape" | "text" | "image" | "group";
  name: string;
  left: number;
  top: number;
  width: number;
  height?: number;
  children?: El[];
  rotation?: number;
  fontFamily?: string;
  fontRef?: string;
  // shape
  paths?: { d: string; fill: { color: string } }[];
  viewBox?: { left: number; top: number; width: number; height: number };
  // text
  text?: string;
  fontSize?: number;
  color?: string;
  fontWeight?: FontWeight;
  fontStyle?: "normal" | "italic";
  letterSpacingEm?: number;
  lineHeightEm?: number;
  textAlign?: "start" | "center" | "end" | "justify";
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
  summary: { shape: number; image: number; text: number; group?: number };
};

const readText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(file);
  });

const toCanva = (e: El): any => {
  if (e.type === "group") {
    return { type: "group", children: (e.children ?? []).map(toCanva),
      left: e.left, top: e.top, width: e.width, height: e.height, rotation: e.rotation ?? 0 };
  }
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
    if (e.letterSpacingEm !== undefined || e.lineHeightEm !== undefined) {
      const range = createRichtextRange();
      const added = range.appendText(e.text ?? "");
      range.formatParagraph(added.bounds, {
        ...(e.fontRef ? { fontRef: e.fontRef as any } : {}),
        fontSize: e.fontSize,
        color: e.color,
        fontWeight: e.fontWeight ?? "normal",
        fontStyle: e.fontStyle ?? "normal",
        textAlign: e.textAlign ?? "start",
        ...(e.letterSpacingEm !== undefined ? { letterSpacingEm: e.letterSpacingEm } : {}),
        ...(e.lineHeightEm !== undefined ? { lineHeightEm: e.lineHeightEm } : {}),
      });
      return { type: "richtext", range, top: e.top, left: e.left,
        width: e.width, rotation: e.rotation ?? 0 };
    }
    return {
      type: "text",
      children: [e.text ?? ""],
      top: e.top,
      left: e.left,
      width: e.width,
      fontSize: e.fontSize,
      color: e.color,
      fontWeight: e.fontWeight ?? "normal",
      fontStyle: e.fontStyle ?? "normal",
      textAlign: e.textAlign ?? "start",
      rotation: e.rotation ?? 0,
      ...(e.fontRef ? { fontRef: e.fontRef } : {}),
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

// Resolve requested installed Canva font names, rather than inventing font IDs.
const resolvePackageFonts = async (pkg: Pkg) => {
  const requestedRefs: string[] = [];
  let hasExplicitFont = false;
  const collectRefs = (elements: El[]) => elements.forEach((e) => {
    if (e.children) collectRefs(e.children);
    if (e.type === "text" && (e.fontFamily || e.fontRef)) hasExplicitFont = true;
    if (e.type === "text" && e.fontRef) requestedRefs.push(e.fontRef);
  });
  collectRefs(pkg.elements);
  if (!hasExplicitFont) return;
  const { fonts: defaultFonts } = await findFonts();
  const { fonts: referencedFonts } = requestedRefs.length
    ? await findFonts({ fontRefs: [...new Set(requestedRefs)] as any })
    : { fonts: [] };
  const fonts = [...defaultFonts, ...referencedFonts];
  const walk = (elements: El[]) => elements.forEach((e) => {
    if (e.children) walk(e.children);
    if (e.type !== "text") return;
    const match = e.fontFamily
      ? fonts.find((f) => f.name.toLowerCase() === e.fontFamily?.toLowerCase())
      : e.fontRef ? fonts.find((f) => f.ref === e.fontRef) : undefined;
    if ((e.fontFamily || e.fontRef) && !match) throw new Error(
      `Font Canva tidak tersedia: ${e.fontFamily ?? e.fontRef}. Pilih padanan sebelum impor.`);
    if (!match) return;
    e.fontRef = match.ref;
    const weight = e.fontWeight ?? "normal";
    const style = e.fontStyle ?? "normal";
    const face = match.weights.find((w) => w.weight === weight);
    if (!face?.styles.includes(style)) throw new Error(
      `Font ${match.name} tidak menyediakan varian ${weight}/${style}. Impor dihentikan agar font tidak diganti diam-diam.`);
  });
  // Validate every explicit selection, including legacy package references.
  walk(pkg.elements);
};

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
  const [packageFont, setPackageFont] = useState("");
  const choosePackageFont = async () => {
    try {
      const choice = await requestFontSelection();
      if (choice.type !== "completed") return;
      setPkgs((current) => current.map((p) => ({ ...p, elements: p.elements.map((e) =>
        e.type === "text" ? { ...e, fontRef: choice.font.ref, fontFamily: undefined } : e) })));
      setPackageFont(choice.font.name);
      setLog([`FONT_CATALOGUE ${JSON.stringify(choice.font)}`]);
    } catch (error) { setLog([String(error)]); }
  };
  const [inspection, setInspection] = useState<Record<string, unknown>>();
  const [repairPlan, setRepairPlan] = useState<NativeRepairPlan>();
  const [repairAccepted, setRepairAccepted] = useState(false);
  const [repairCount, setRepairCount] = useState(0);
  const loadRepair = async (file?: File) => {
    setRepairPlan(undefined);
    setRepairAccepted(false);
    if (!file) return;
    try { setRepairPlan(validatePlan(JSON.parse(await readText(file)))); }
    catch (error) { setLog([String(error)]); }
  };
  const repair = async () => {
    if (!repairPlan || !repairAccepted || repairCount >= 2) return;
    setBusy(true);
    try {
      const result = await applyNativeRepair(repairPlan);
      setRepairCount((n) => n + 1);
      setInspection(result);
      setLog(["Aksen diganti menjadi path native. Uji warna, visual, dan buyer masih diperlukan."]);
    } catch (error) { setLog([`Perbaikan dihentikan: ${String(error)}. Periksa salinan kandidat sebelum mencoba lagi.`]); }
    finally { setBusy(false); }
  };
  const inspect = async () => {
    setBusy(true);
    setInspection(undefined);
    try {
      setInspection(await inspectCurrentPage());
      setLog(["Inspeksi selesai. QA struktur, visual, dan buyer belum diuji."]);
    } catch (error) {
      setLog([`Inspeksi tidak tersedia: ${String(error)}. Gunakan pemeriksaan manual di Canva.`]);
    } finally {
      setBusy(false);
    }
  };

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
      if (!p) continue;
      setLog([`Halaman ${i + 1}/${pkgs.length}: ${p.source}...`, ...out]);
      try { await resolvePackageFonts(p); }
      catch (error) { out.push(`GAGAL ${p.source}: ${String(error)}`); continue; }
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
    const pkg = pkgs[0];
    if (!pkg) return;
    setBusy(true);
    try { await resolvePackageFonts(pkg); }
    catch (error) { setLog([String(error)]); setBusy(false); return; }
    const fails = await assembleHere(pkg);
    setLog([`Selesai: ${pkg.elements.length - fails.length} dari ${pkg.elements.length} elemen.`, ...fails]);
    setBusy(false);
  };

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Text>CUSBE Native Importer — audit font v4</Text>
        <Text size="small">Mode B — inspeksi kandidat Magic Layers. Buka salinan kandidat terlebih dahulu. Perbaikan otomatis belum diaktifkan.</Text>
        <Button variant="secondary" onClick={inspect} disabled={busy} stretch>Inspeksi halaman saat ini</Button>
        <Text size="small">Perbaikan aksen native: pilih rencana JSON hasil audit.</Text>
        <input type="file" accept=".json" disabled={busy} onChange={(e) => loadRepair(e.target.files?.[0])} />
        {repairPlan && <>
          <Text size="small">{repairPlan.targets.length} aksen raster akan diganti. Warna menjadi solid; gradien dan tekstur aksen akan hilang.</Text>
          <label><input type="checkbox" checked={repairAccepted} onChange={(e) => setRepairAccepted(e.target.checked)} />Saya membuka salinan kandidat dan menerima warna solid pada aksen ini.</label>
          <Button variant="secondary" disabled={busy || !repairAccepted || repairCount >= 2} onClick={repair}>Terapkan perbaikan aksen</Button>
        </>}
        {inspection && <>
          <Text size="small">{JSON.stringify(inspection.breakdown)}</Text>
          <a href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(inspection, null, 2))}`} download="CUSBE_CANVA_INSPECTION.json">Simpan laporan inspeksi JSON</a>
        </>}
        <Text size="small">Mode A — susun paket lokal</Text>
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
            <Button variant="secondary" onClick={choosePackageFont} disabled={busy} stretch>Pilih font teks paket</Button>
            {packageFont && <Text size="small">Font paket: {packageFont}</Text>}
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
