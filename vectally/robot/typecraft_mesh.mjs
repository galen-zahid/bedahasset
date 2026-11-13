// setMesh versi tahan banting, dikembangkan dari typecraft_ui_geometry.mjs milik Codex.
// Perubahan: titik pegangan dikelompokkan ke 2 baris x 5 titik berjarak sama; titik yang tertutup
// huruf (terdeteksi 9) ditebak dari jarak tetangga; blob ekstra (lubang huruf) dibuang.
// Kalau tetap gagal, kanvas dan daftar blob dikembalikan untuk diagnosis.
export async function setMesh2(e, quad) {
  const c = e.querySelector('canvas[id^="paper-view-"]'); if (!c) throw new Error('Warp canvas absent');
  function blobs() {
    const w = c.width, h = c.height, d = c.getContext('2d').getImageData(0, 0, w, h).data, seen = new Uint8Array(w * h), out = [];
    const white = i => d[i * 4] > 245 && d[i * 4 + 1] > 245 && d[i * 4 + 2] > 245 && d[i * 4 + 3] > 200;
    for (let k = 0; k < w * h; k++) {
      if (seen[k] || !white(k)) continue; const q = [k]; seen[k] = 1; let n = 0, sx = 0, sy = 0, minx = w, miny = h, maxx = 0, maxy = 0;
      while (q.length) { const p = q.pop(), x = p % w, y = Math.floor(p / w); n++; sx += x; sy += y; minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y); for (const j of [p - 1, p + 1, p - w, p + w]) if (j >= 0 && j < w * h && !seen[j] && white(j)) { seen[j] = 1; q.push(j); } }
      if (n > 5 && n < 200 && maxx - minx < 18 && maxy - miny < 18) out.push({ x: sx / n, y: sy / n, n, bw: maxx - minx + 1, bh: maxy - miny + 1 });
    }
    return out;
  }
  function row5(r) {
    // pilih/lengkapi 5 titik berjarak sama dari kandidat satu baris
    r.sort((a, b) => a.x - b.x);
    if (r.length === 5) return r;
    if (r.length > 5) { // buang yang paling tidak bulat / paling kecil sampai 5
      const score = p => Math.abs(p.bw - p.bh) + (p.n < 30 ? 5 : 0);
      while (r.length > 5) { let worst = 0; for (let i = 1; i < r.length; i++) if (score(r[i]) > score(r[worst])) worst = i; r.splice(worst, 1); }
      return r;
    }
    if (r.length === 4) { // satu titik hilang: cari celah terlebar lalu isi di tengahnya
      const gaps = [1, 2, 3].map(i => r[i].x - r[i - 1].x), med = gaps.slice().sort((a, b) => a - b)[1];
      let gi = gaps.indexOf(Math.max(...gaps));
      if (Math.max(...gaps) < 1.5 * med) { // celah rata: titik hilang di ujung
        const left = r[0].x - med, right = r[3].x + med;
        return left >= 0 ? [{ x: left, y: r[0].y, guessed: true }, ...r] : [...r, { x: right, y: r[3].y, guessed: true }];
      }
      const a = r[gi], b = r[gi + 1]; r.splice(gi + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, guessed: true }); return r;
    }
    throw new Error('Row has ' + r.length + ' handles');
  }
  function points() {
    const all = blobs();
    if (all.length < 8) throw new Error('Expected ten visible warp handles, got ' + all.length);
    const ys = all.map(p => p.y).sort((a, b) => a - b), mid = (ys[0] + ys[ys.length - 1]) / 2;
    const top = row5(all.filter(p => p.y < mid)), bot = row5(all.filter(p => p.y >= mid));
    return [...top, ...bot];
  }
  const minx = Math.min(...quad.map(p => p[0])), maxx = Math.max(...quad.map(p => p[0])), miny = Math.min(...quad.map(p => p[1])), maxy = Math.max(...quad.map(p => p[1]));
  const s = Math.min((c.width - 120) / (maxx - minx), (c.height - 120) / (maxy - miny));
  const q = quad.map(p => [(p[0] - (minx + maxx) / 2) * s + c.width / 2, (p[1] - (miny + maxy) / 2) * s + c.height / 2]);
  const targets = [];
  for (const [a, b] of [[q[0], q[1]], [q[3], q[2]]]) for (let i = 0; i < 5; i++) targets.push({ x: a[0] + (b[0] - a[0]) * i / 4, y: a[1] + (b[1] - a[1]) * i / 4 });
  let before; try { before = points(); } catch (err) { return { error: err.message, blobs: blobs(), canvas: c.toDataURL('image/png') }; }
  let after, maxError;
  async function drag(from, to) {
    const r = c.getBoundingClientRect(), doc = e.ownerDocument;
    const emit = (target, type, x, y, buttons) => target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: doc.defaultView, clientX: r.left + x * r.width / c.width, clientY: r.top + y * r.height / c.height, button: 0, buttons }));
    emit(c, 'mousedown', from.x, from.y, 1); for (let i = 1; i <= 12; i++) { emit(doc, 'mousemove', from.x + (to.x - from.x) * i / 12, from.y + (to.y - from.y) * i / 12, 1); await new Promise(r => setTimeout(r, 20)); } emit(doc, 'mouseup', to.x, to.y, 0);
  }
  // setelah digeser, baris atas/bawah bisa bertumpuk (teks miring tajam): kenali tiap titik dari
  // posisi terakhir yang diketahui (pelacakan), bukan dari pembagian baris
  function track(known) {
    const bs = blobs(), used = new Set(), out = [];
    for (const k of known) {
      let best = -1, bd = 1e9;
      bs.forEach((b, j) => { if (used.has(j)) return; const dd = Math.hypot(b.x - k.x, b.y - k.y); if (dd < bd) { bd = dd; best = j; } });
      if (best < 0 || bd > 25) out.push({ x: k.x + 999, y: k.y, lost: true }); else { used.add(best); out.push(bs[best]); }  // hilang = galat besar, jangan dianggap tepat
    }
    return out;
  }
  let lostCount = 0;
  let current = before.map(p => ({ x: p.x, y: p.y }));
  for (let pass = 0; pass < 3; pass++) {
    for (let i = 0; i < 10; i++) if (Math.hypot(current[i].x - targets[i].x, current[i].y - targets[i].y) > 0.7) { await drag(current[i], targets[i]); current[i] = { ...targets[i] }; }
    await new Promise(r => setTimeout(r, 1200));
    after = track(targets);
    // titik yang tertutup huruf (lost) sudah digeser ke target; nilai dari titik yang terlihat saja
    const seen = after.map((p, i) => [p, i]).filter(([p]) => !p.lost);
    lostCount = after.length - seen.length;
    maxError = seen.length ? Math.max(...seen.map(([p, i]) => Math.hypot(p.x - targets[i].x, p.y - targets[i].y))) : 999;
    if (lostCount > 2) maxError = 999;
    current = after.map((p, i) => p.lost ? { ...targets[i] } : { x: p.x, y: p.y });
    if (maxError <= 1.5) break;
  }
  return { quad, before, targets, after, maxError, lostCount, guessed: before.filter(p => p.guessed).length };
}
