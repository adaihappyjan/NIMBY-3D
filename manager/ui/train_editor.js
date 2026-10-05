/* Nimby3D manager: the train editor page.
 *
 * Registers itself in window.N3D_PAGES as { id: 'trains', icon, title, mount(root, ctx), unmount() }.
 * ctx (from the app): call(method, args) -> Promise, t(zh, en), lang, onLang(cb), toast(msg, kind),
 * confirm({title, body, ok, danger}) -> Promise<bool>, openExternal(url), pickFile({title, filters, save, name}),
 * pickFolder({title}), status().
 *
 * Everything the page does goes through the Python side as trains.<method> (manager/trains.py): specs
 * are built there into GOV2 models (manager/trainmodel); this page edits the spec, shows the model in a
 * small WebGL viewer of its own (no network, no libraries), and exports into a mod's nimby3d folder.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------ small helpers
  let ctx = null;
  let root = null;
  const lang = () => (ctx && ctx.lang) || (document.documentElement.lang || "en").slice(0, 2);
  const T = (zh, en) => (ctx && typeof ctx.t === "function" ? ctx.t(zh, en) : (lang() === "zh" ? zh : en));
  const TT = (pair) => (pair ? T(pair[0], pair[1]) : "");
  const esc = (s) => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (id, cls) => `<svg class="i${cls ? " " + cls : ""}" aria-hidden="true"><use href="#${id}"/></svg>`;
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const r4 = (v) => Math.round(v * 10000) / 10000;
  const fmtNum = (v) => (typeof v === "number" ? String(v) : v === undefined || v === null ? "" : String(v));
  const num = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString(lang() === "zh" ? "zh-CN" : "en-US"));
  const kb = (n) => (n >= 1048576 ? (n / 1048576).toFixed(2) + " MB" : Math.round(n / 1024) + " KB");

  function getPath(obj, path) {
    if (!path) return obj;
    let cur = obj;
    for (const k of path.split(".")) {
      if (cur === null || cur === undefined) return undefined;
      cur = cur[/^\d+$/.test(k) ? Number(k) : k];
    }
    return cur;
  }
  function setPath(obj, path, value) {
    const keys = path.split(".");
    let cur = obj;
    for (let i = 0; i < keys.length - 1; i++) {
      const k = /^\d+$/.test(keys[i]) ? Number(keys[i]) : keys[i];
      if (cur[k] === null || cur[k] === undefined || typeof cur[k] !== "object") cur[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
      cur = cur[k];
    }
    const last = /^\d+$/.test(keys[keys.length - 1]) ? Number(keys[keys.length - 1]) : keys[keys.length - 1];
    if (value === undefined) delete cur[last];
    else cur[last] = value;
  }
  // "a.b[2].c" (Python's paths) -> "a.b.2.c"
  const dotPath = (p) => String(p || "").replace(/\[(\d+)\]/g, ".$1");

  const parseNum = (text) => {
    const t = String(text).trim().replace(/,/g, ".").replace(/^\+/, "");
    if (!/^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t)) return null;
    const v = Number(t);
    return Number.isFinite(v) ? v : null;
  };
  const parseList = (text) => {
    const parts = String(text).split(/[\s;,]+/).filter((x) => x !== "");
    const out = [];
    for (const p of parts) {
      const v = parseNum(p);
      if (v === null) return null;
      out.push(v);
    }
    return out;
  };

  // linear RGB <-> the sRGB hex a colour input shows (as the add-on converts)
  const lin2s = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
  const s2lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  function hexOf(col) {
    if (typeof col === "string" && /^#[0-9a-f]{6}$/i.test(col)) return col.toLowerCase();
    if (!Array.isArray(col) || col.length !== 3) return "#808080";
    return "#" + col.map((c) => Math.round(Math.min(1, Math.max(0, lin2s(Number(c) || 0))) * 255).toString(16).padStart(2, "0")).join("");
  }
  const linOf = (hex) => [1, 3, 5].map((i) => r4(s2lin(parseInt(hex.slice(i, i + 2), 16) / 255)));

  function b64bytes(s) {
    const bin = atob(s);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function api(method, args) {
    const r = await ctx.call("trains." + method, args || {});
    if (r && typeof r === "object" && r.ok === false) throw new Error(r.message || r.error || "error");
    if (r && typeof r === "object" && r.ok === true && "result" in r) return r.result;
    return r;
  }
  const errMsg = (e) => (e && e.message ? e.message : String(e));
  const toast = (msg, kind) => { if (ctx && ctx.toast) ctx.toast(msg, kind || "info"); };

  // ------------------------------------------------------------------ the viewer (WebGL, no libraries)
  const VS = `
attribute vec3 aPos; attribute vec3 aNrm; attribute vec4 aCol; attribute vec4 aEmi; attribute vec4 aDoor; attribute float aGroup;
uniform mat4 uVP; uniform vec3 uMin; uniform vec3 uSpan; uniform float uOpenL; uniform float uOpenR;
varying vec3 vN; varying vec4 vC; varying vec4 vE; varying vec3 vW; varying float vG;
void main() {
  vec3 p = uMin + aPos * uSpan;
  float o = aDoor.w > 1.5 ? uOpenR : (aDoor.w > 0.5 ? uOpenL : 0.0);
  o = o * o * (3.0 - 2.0 * o);
  p += aDoor.xyz * o;
  vW = p; vN = aNrm; vC = aCol; vE = aEmi; vG = aGroup;
  gl_Position = uVP * vec4(p, 1.0);
}`;
  const FS = `
precision mediump float;
uniform vec3 uLight; uniform vec3 uEye; uniform float uCut; uniform float uCutSide; uniform float uWire; uniform vec4 uWireCol; uniform float uAlpha;
varying vec3 vN; varying vec4 vC; varying vec4 vE; varying vec3 vW; varying float vG;
void main() {
  if (uCut > 0.5 && vW.z * uCutSide > 0.003 && vG < 2.5) discard;
  if (uCut > 0.5 && vW.z * uCutSide > 0.003 && vG > 3.5) discard;
  if (uWire > 0.5) { gl_FragColor = uWireCol; return; }
  vec3 n = normalize(vN);
  if (!gl_FrontFacing) n = -n;
  vec3 base = pow(vC.rgb, vec3(2.2));
  vec3 V = normalize(uEye - vW);
  float diff = max(dot(n, uLight), 0.0);
  float hemi = 0.5 + 0.5 * n.y;
  vec3 H = normalize(uLight + V);
  float metal = vE.a;
  float sp = pow(max(dot(n, H), 0.0), 48.0) * (0.12 + 0.5 * metal);
  float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0) * 0.08;
  vec3 col = base * (0.22 + 0.28 * hemi + 0.72 * diff) * (1.0 - 0.35 * metal) + sp + rim + pow(vE.rgb, vec3(2.2)) * 1.2;
  gl_FragColor = vec4(pow(col, vec3(1.0 / 2.2)), vC.a * uAlpha);
}`;
  const LVS = `attribute vec3 aPos; uniform mat4 uVP; void main() { gl_Position = uVP * vec4(aPos, 1.0); }`;
  const LFS = `precision mediump float; uniform vec4 uCol; void main() { gl_FragColor = uCol; }`;

  function m4mul(a, b) {
    const o = new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
    return o;
  }
  function m4persp(fovy, aspect, near, far) {
    const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]);
  }
  function v3norm(v) { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
  function v3cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
  function m4look(eye, t, up) {
    const z = v3norm([eye[0] - t[0], eye[1] - t[1], eye[2] - t[2]]);
    const x = v3norm(v3cross(up, z));
    const y = v3cross(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
      -(x[0] * eye[0] + x[1] * eye[1] + x[2] * eye[2]), -(y[0] * eye[0] + y[1] * eye[1] + y[2] * eye[2]), -(z[0] * eye[0] + z[1] * eye[1] + z[2] * eye[2]), 1]);
  }
  function cssColor(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const c = document.createElement("canvas");
    c.width = c.height = 1;
    const g = c.getContext("2d");
    g.fillStyle = "#000";
    g.fillStyle = v;
    g.fillRect(0, 0, 1, 1);
    const d = g.getImageData(0, 0, 1, 1).data;
    return [d[0] / 255, d[1] / 255, d[2] / 255, d[3] / 255];
  }

  class Viewer {
    constructor(canvas, onStatus) {
      this.canvas = canvas;
      this.onStatus = onStatus || (() => {});
      this.mesh = null;
      this.payload = null;
      this.open = 0;
      this.side = "both";
      this.wire = false;
      this.cut = false;
      this.yaw = 0.62; this.pitch = 0.3; this.dist = 30; this.target = [0, 2, 0];
      this.anim = null;
      this.dirty = true;
      this.raf = 0;
      this.disposed = false;
      this._init();
      this._bind();
      this._loop = this._loop.bind(this);
      this.raf = requestAnimationFrame(this._loop);
    }
    _init() {
      const opts = { antialias: true, alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: false };
      let gl = this.canvas.getContext("webgl2", opts);
      this.gl2 = !!gl;
      if (!gl) gl = this.canvas.getContext("webgl", opts) || this.canvas.getContext("experimental-webgl", opts);
      this.gl = gl;
      if (!gl) { this.ok = false; return; }
      this.u32 = this.gl2 || !!gl.getExtension("OES_element_index_uint");
      this.prog = this._program(VS, FS);
      this.lprog = this._program(LVS, LFS);
      this.ok = !!(this.prog && this.lprog);
      this._themeColors();
      if (this.payload) this.setMesh(this.payload, true);
    }
    _program(vs, fs) {
      const gl = this.gl;
      const sh = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
        return s;
      };
      const v = sh(gl.VERTEX_SHADER, vs), f = sh(gl.FRAGMENT_SHADER, fs);
      if (!v || !f) return null;
      const p = gl.createProgram();
      gl.attachShader(p, v);
      gl.attachShader(p, f);
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { console.error(gl.getProgramInfoLog(p)); return null; }
      const info = { p, a: {}, u: {} };
      const na = gl.getProgramParameter(p, gl.ACTIVE_ATTRIBUTES);
      for (let i = 0; i < na; i++) { const a = gl.getActiveAttrib(p, i); info.a[a.name] = gl.getAttribLocation(p, a.name); }
      const nu = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < nu; i++) { const u = gl.getActiveUniform(p, i); info.u[u.name] = gl.getUniformLocation(p, u.name); }
      return info;
    }
    _themeColors() {
      this.gridCol = cssColor("--border-strong", "rgba(128,128,128,.3)");
      this.railCol = cssColor("--text-3", "#888");
      this.wireCol = cssColor("--accent", "#3ddbc4");
      this.dirty = true;
    }
    themeChanged() { if (this.ok) this._themeColors(); }
    _bind() {
      const c = this.canvas;
      this._ptr = new Map();
      this._h = {
        down: (e) => {
          c.setPointerCapture(e.pointerId);
          this._ptr.set(e.pointerId, { x: e.clientX, y: e.clientY, b: e.button, shift: e.shiftKey });
          c.classList.add("te-drag");
        },
        move: (e) => {
          const p = this._ptr.get(e.pointerId);
          if (!p) return;
          const dx = e.clientX - p.x, dy = e.clientY - p.y;
          p.x = e.clientX; p.y = e.clientY;
          if (this._ptr.size >= 2) {
            const pts = [...this._ptr.values()];
            const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
            if (this._pinch) this.dist = Math.min(400, Math.max(1.5, this.dist * this._pinch / Math.max(d, 1)));
            this._pinch = d;
          } else if (p.b === 2 || p.b === 1 || p.shift || e.shiftKey) {
            const s = this.dist * 0.0016;
            const right = [Math.cos(this.yaw), 0, -Math.sin(this.yaw)];
            const up = [-Math.sin(this.pitch) * Math.sin(this.yaw), Math.cos(this.pitch), -Math.sin(this.pitch) * Math.cos(this.yaw)];
            for (let k = 0; k < 3; k++) this.target[k] += (-dx * right[k] + dy * up[k]) * s;
          } else {
            this.yaw -= dx * 0.008;
            this.pitch = Math.min(1.45, Math.max(-1.2, this.pitch + dy * 0.006));
          }
          this.dirty = true;
        },
        up: (e) => {
          this._ptr.delete(e.pointerId);
          this._pinch = 0;
          if (!this._ptr.size) c.classList.remove("te-drag");
        },
        wheel: (e) => {
          e.preventDefault();
          this.dist = Math.min(400, Math.max(1.5, this.dist * Math.exp(e.deltaY * 0.0012)));
          this.dirty = true;
        },
        dbl: () => this.resetView(),
        ctx: (e) => e.preventDefault(),
        lost: (e) => { e.preventDefault(); this.ok = false; this.onStatus("lost"); },
        restored: () => { this._init(); this.onStatus("restored"); this.dirty = true; },
      };
      c.addEventListener("pointerdown", this._h.down);
      c.addEventListener("pointermove", this._h.move);
      c.addEventListener("pointerup", this._h.up);
      c.addEventListener("pointercancel", this._h.up);
      c.addEventListener("wheel", this._h.wheel, { passive: false });
      c.addEventListener("dblclick", this._h.dbl);
      c.addEventListener("contextmenu", this._h.ctx);
      c.addEventListener("webglcontextlost", this._h.lost);
      c.addEventListener("webglcontextrestored", this._h.restored);
      this._ro = new ResizeObserver(() => { this.dirty = true; });
      this._ro.observe(c);
    }
    resetView() {
      if (this.payload) {
        const m = this.payload;
        const len = m.max[0] - m.min[0];
        this.target = [(m.max[0] + m.min[0]) / 2, (m.max[1] + m.min[1]) / 2 * 0.9, 0];
        this.dist = Math.max(6, len * 1.05);
      }
      this.yaw = 0.62; this.pitch = 0.28;
      this.dirty = true;
    }
    view(name) {
      const presets = { side: [0, 0.05], front: [Math.PI / 2, 0.08], three: [0.62, 0.28], top: [0.0001, 1.42] };
      const p = presets[name];
      if (!p) return;
      this.yaw = p[0]; this.pitch = p[1];
      if (name === "front" && this.payload) this.dist = Math.max(8, (this.payload.max[2] - this.payload.min[2]) * 4.2);
      else if (this.payload) this.dist = Math.max(6, (this.payload.max[0] - this.payload.min[0]) * 1.05);
      this.dirty = true;
    }
    setMesh(p, keepView) {
      const first = !this.payload;
      this.payload = p;
      if (!this.ok) return;
      const gl = this.gl;
      this._freeMesh();
      const n = p.count;
      const pos = new Uint16Array(b64bytes(p.positions).buffer);
      const nrm = new Int8Array(b64bytes(p.normals).buffer);
      const mat = b64bytes(p.material);
      const door = b64bytes(p.door);
      const grp = b64bytes(p.group);
      const col = new Uint8Array(n * 4), emi = new Uint8Array(n * 4), dv = new Float32Array(n * 4), gv = new Float32Array(n);
      const mcol = p.materials.map((m) => {
        const h = m.color.slice(1);
        return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), Math.round(Math.min(1, Math.max(0, m.alpha)) * 255)];
      });
      const memi = p.materials.map((m) => {
        const h = (m.emissive || "#000000").slice(1);
        return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), Math.round(Math.min(1, Math.max(0, m.metallic || 0)) * 255)];
      });
      for (let i = 0; i < n; i++) {
        const c = mcol[mat[i]] || [128, 128, 128, 255], e = memi[mat[i]] || [0, 0, 0, 0];
        col.set(c, i * 4);
        emi.set(e, i * 4);
        const d = door[i];
        if (d > 0 && p.doors[d - 1]) {
          const dd = p.doors[d - 1];
          dv[i * 4] = dd.slide[0]; dv[i * 4 + 1] = dd.slide[1]; dv[i * 4 + 2] = dd.slide[2]; dv[i * 4 + 3] = dd.side;
        }
        gv[i] = grp[i];
      }
      const buf = (data, target) => { const b = gl.createBuffer(); gl.bindBuffer(target || gl.ARRAY_BUFFER, b); gl.bufferData(target || gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); return b; };
      const big = p.index_type === "u32";
      if (big && !this.u32) { this.onStatus("u32"); return; }
      const idxBytes = b64bytes(p.indices);
      const idx = big ? new Uint32Array(idxBytes.buffer) : new Uint16Array(idxBytes.buffer);
      // edges for the wireframe, each once
      const seen = new Set();
      const edges = [];
      for (let i = 0; i < idx.length; i += 3) {
        for (let k = 0; k < 3; k++) {
          const a = idx[i + k], b = idx[i + (k + 1) % 3];
          const key = a < b ? a * 2097152 + b : b * 2097152 + a;
          if (!seen.has(key)) { seen.add(key); edges.push(a, b); }
        }
      }
      this.mesh = {
        pos: buf(pos), nrm: buf(nrm), col: buf(col), emi: buf(emi), door: buf(dv), grp: buf(gv),
        idx: buf(idx, gl.ELEMENT_ARRAY_BUFFER), type: big ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT, bytes: big ? 4 : 2,
        total: idx.length, opaque: p.opaque,
        edges: buf(big ? new Uint32Array(edges) : new Uint16Array(edges), gl.ELEMENT_ARRAY_BUFFER), nedges: edges.length,
        min: p.min, span: [p.max[0] - p.min[0] || 1e-6, p.max[1] - p.min[1] || 1e-6, p.max[2] - p.min[2] || 1e-6],
      };
      this._makeGround(p);
      if (first && !keepView) this.resetView();
      this.dirty = true;
    }
    _makeGround(p) {
      const gl = this.gl;
      const L = Math.max(10, (p.max[0] - p.min[0]) / 2 + 4);
      const lines = [];
      for (let x = -Math.ceil(L); x <= Math.ceil(L); x += 1) lines.push(x, 0, -4, x, 0, 4);
      for (let z = -4; z <= 4; z += 1) lines.push(-Math.ceil(L), 0, z, Math.ceil(L), 0, z);
      const rails = [];
      for (const z of [-0.7175, 0.7175]) rails.push(-L - 6, 0.005, z, L + 6, 0.005, z);
      if (this.ground) { gl.deleteBuffer(this.ground.grid); gl.deleteBuffer(this.ground.rails); }
      const mk = (a) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(a), gl.STATIC_DRAW); return b; };
      this.ground = { grid: mk(lines), ngrid: lines.length / 3, rails: mk(rails), nrails: rails.length / 3 };
    }
    _freeMesh() {
      if (!this.mesh || !this.gl) return;
      const gl = this.gl;
      for (const k of ["pos", "nrm", "col", "emi", "door", "grp", "idx", "edges"]) gl.deleteBuffer(this.mesh[k]);
      this.mesh = null;
    }
    setDoors(open, side) { this.open = open; this.side = side; this.dirty = true; }
    playDoors(seconds) {
      const [o, c] = seconds || [1.6, 0.7];
      this.anim = { t0: performance.now(), o, c };
      this.dirty = true;
    }
    stopDoors() { this.anim = null; }
    pause() { this.paused = true; cancelAnimationFrame(this.raf); }
    resume() {
      if (this.disposed || !this.paused) return;
      this.paused = false;
      this.dirty = true;
      this.raf = requestAnimationFrame(this._loop);
    }
    _loop(now) {
      if (this.disposed || this.paused) return;
      this.raf = requestAnimationFrame(this._loop);
      if (this.anim) {
        const a = this.anim;
        const t = ((now - a.t0) / 1000) % (a.o + a.c + 2.2);
        this.open = t < a.o ? t / a.o : t < a.o + 1.1 ? 1 : t < a.o + 1.1 + a.c ? 1 - (t - a.o - 1.1) / a.c : 0;
        if (this.onDoor) this.onDoor(this.open);
        this.dirty = true;
      }
      if (this.dirty) { this.dirty = false; this.draw(); }
    }
    draw() {
      const gl = this.gl;
      if (!this.ok || !gl) return;
      const c = this.canvas;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr));
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const eye = [this.target[0] + this.dist * Math.cos(this.pitch) * Math.sin(this.yaw), this.target[1] + this.dist * Math.sin(this.pitch),
        this.target[2] + this.dist * Math.cos(this.pitch) * Math.cos(this.yaw)];
      const proj = m4persp(0.62, w / h, Math.max(0.05, this.dist / 300), this.dist * 30 + 200);
      const vp = m4mul(proj, m4look(eye, this.target, [0, 1, 0]));
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      // the ground: a metre grid and the two rails
      if (this.ground && this.lprog) {
        const L = this.lprog;
        gl.useProgram(L.p);
        gl.uniformMatrix4fv(L.u.uVP, false, vp);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.depthMask(false);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.ground.grid);
        gl.enableVertexAttribArray(L.a.aPos);
        gl.vertexAttribPointer(L.a.aPos, 3, gl.FLOAT, false, 0, 0);
        const g = this.gridCol;
        gl.uniform4f(L.u.uCol, g[0], g[1], g[2], Math.min(0.6, g[3] + 0.15));
        gl.drawArrays(gl.LINES, 0, this.ground.ngrid);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.ground.rails);
        gl.vertexAttribPointer(L.a.aPos, 3, gl.FLOAT, false, 0, 0);
        const r = this.railCol;
        gl.uniform4f(L.u.uCol, r[0], r[1], r[2], 0.9);
        gl.drawArrays(gl.LINES, 0, this.ground.nrails);
        gl.disableVertexAttribArray(L.a.aPos);
        gl.depthMask(true);
        gl.disable(gl.BLEND);
      }
      const m = this.mesh;
      if (!m) return;
      const P = this.prog;
      gl.useProgram(P.p);
      const attr = (name, b, size, type, norm) => {
        const loc = P.a[name];
        if (loc === undefined || loc < 0) return;
        gl.bindBuffer(gl.ARRAY_BUFFER, b);
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, size, type, norm, 0, 0);
      };
      attr("aPos", m.pos, 3, gl.UNSIGNED_SHORT, true);
      attr("aNrm", m.nrm, 3, gl.BYTE, true);
      attr("aCol", m.col, 4, gl.UNSIGNED_BYTE, true);
      attr("aEmi", m.emi, 4, gl.UNSIGNED_BYTE, true);
      attr("aDoor", m.door, 4, gl.FLOAT, false);
      attr("aGroup", m.grp, 1, gl.FLOAT, false);
      gl.uniformMatrix4fv(P.u.uVP, false, vp);
      gl.uniform3fv(P.u.uMin, m.min);
      gl.uniform3fv(P.u.uSpan, m.span);
      const open = Math.min(1, Math.max(0, this.open));
      gl.uniform1f(P.u.uOpenL, this.side === "right" ? 0 : open);
      gl.uniform1f(P.u.uOpenR, this.side === "left" ? 0 : open);
      gl.uniform3fv(P.u.uLight, v3norm([0.45, 0.8, 0.55]));
      gl.uniform3fv(P.u.uEye, eye);
      gl.uniform1f(P.u.uCut, this.cut ? 1 : 0);
      gl.uniform1f(P.u.uCutSide, eye[2] >= this.target[2] ? 1 : -1);
      gl.uniform1f(P.u.uWire, 0);
      gl.uniform1f(P.u.uAlpha, 1);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.idx);
      gl.enable(gl.CULL_FACE);
      gl.cullFace(gl.BACK);
      if (this.cut) gl.disable(gl.CULL_FACE);
      if (this.wire) { gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(1, 1); }
      gl.drawElements(gl.TRIANGLES, m.opaque, m.type, 0);
      gl.disable(gl.POLYGON_OFFSET_FILL);
      if (this.wire && m.nedges) {
        gl.uniform1f(P.u.uWire, 1);
        const wc = this.wireCol;
        gl.uniform4f(P.u.uWireCol, wc[0], wc[1], wc[2], 0.55);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.edges);
        gl.drawElements(gl.LINES, m.nedges, m.type, 0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.idx);
        gl.uniform1f(P.u.uWire, 0);
        gl.disable(gl.BLEND);
      }
      if (m.total > m.opaque) {
        // glass: blended over everything opaque, both sides, not writing depth
        gl.disable(gl.CULL_FACE);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.depthMask(false);
        gl.drawElements(gl.TRIANGLES, m.total - m.opaque, m.type, m.opaque * m.bytes);
        gl.depthMask(true);
        gl.disable(gl.BLEND);
      }
      for (const n of ["aPos", "aNrm", "aCol", "aEmi", "aDoor", "aGroup"]) if (P.a[n] !== undefined && P.a[n] >= 0) gl.disableVertexAttribArray(P.a[n]);
    }
    destroy() {
      this.disposed = true;
      cancelAnimationFrame(this.raf);
      const c = this.canvas;
      c.removeEventListener("pointerdown", this._h.down);
      c.removeEventListener("pointermove", this._h.move);
      c.removeEventListener("pointerup", this._h.up);
      c.removeEventListener("pointercancel", this._h.up);
      c.removeEventListener("wheel", this._h.wheel);
      c.removeEventListener("dblclick", this._h.dbl);
      c.removeEventListener("contextmenu", this._h.ctx);
      c.removeEventListener("webglcontextlost", this._h.lost);
      c.removeEventListener("webglcontextrestored", this._h.restored);
      if (this._ro) this._ro.disconnect();
      try {
        this._freeMesh();
        const ext = this.gl && this.gl.getExtension("WEBGL_lose_context");
        if (ext) ext.loseContext();
      } catch (e) { /* the context may already be gone */ }
    }
  }

  // ------------------------------------------------------------------ the form's fields
  const KIND_OPTS = [["locomotive", "机车", "Locomotive"], ["coach", "客车（无司机室）", "Coach (no cab)"], ["cab_car", "控制车（带司机室的客车）", "Cab car (a coach with a cab)"], ["emu", "动车组车厢", "Multiple-unit car"]];
  const STYLE_OPTS = [["carbody", "车体型（客车、动车、箱形机车）", "Carbody (coach, multiple unit, box cab)"], ["hood", "罩式机车（北美内燃机车）", "Hood unit (North American diesel)"]];
  const MAT_LABELS = {
    primary: ["主涂装色", "Primary livery"], secondary: ["副涂装色", "Secondary livery"], glass: ["车窗玻璃", "Window glass"], gasket: ["窗框与密封条", "Window frames, seals"],
    underframe: ["车底与深色部件", "Underframe, dark parts"], steel: ["金属、扶手、车轮", "Steel, handrails, wheels"], roof: ["车顶", "Roof"], headlamp: ["前照灯", "Headlights"],
    tail_lamp: ["尾灯", "Tail lights"], safety_yellow: ["警示黄（门槛）", "Safety yellow (thresholds)"], logo: ["标志", "Logo"], interior_wall: ["车内墙面", "Interior walls"],
    interior_floor: ["车内地板", "Interior floors"], seat: ["座椅", "Seats"], interior_light: ["车顶灯带", "Ceiling lights"], display: ["司机台屏幕", "Driver's displays"],
  };
  const LEVEL_OPTS = [["none", "无（玻璃不透明）", "None (opaque glass)"], ["simple", "简单", "Simple"], ["detailed", "精细", "Detailed"]];
  const LAYOUT_OPTS = [["single", "单层", "Single deck"], ["bilevel", "双层（GO BiLevel 布局）", "Bi-level (the GO BiLevel layout)"], ["none", "无客室（只有司机室）", "None (cabs only)"]];
  const CAB_OPTS = [["none", "无", "None"], ["front", "前端（+X）", "Front (+X)"], ["both", "两端", "Both ends"]];
  const GANG_OPTS = [["none", "无", "None"], ["front", "前端（+X）", "Front (+X)"], ["rear", "后端（−X）", "Rear (−X)"], ["both", "两端", "Both ends"]];
  const LEAF_OPTS = [[2, "双扇对开", "Two leaves, bi-parting"], [1, "单扇", "One leaf"]];
  const DIR_OPTS = [[1, "向 +X（前）", "Towards +X (front)"], [-1, "向 −X（后）", "Towards −X (rear)"]];
  const LOGO_OPTS = [["none", "无", "None"], ["go", "GO 标志", "GO mark"]];
  const FACING_OPTS = [[1, "关节朝 +X", "Knee to +X"], [-1, "关节朝 −X", "Knee to −X"]];

  const isCar = (s) => !s.body || s.body.style !== "hood";
  const hasDoors = (s) => isCar(s) && s.doors && Array.isArray(s.doors.centers) && s.doors.centers.length > 0;
  const hasCab = (s) => isCar(s) && s.cab && s.cab.ends && s.cab.ends !== "none";
  const hasGang = (s) => isCar(s) && s.gangway && s.gangway.ends && s.gangway.ends !== "none";
  const ilevel = (s) => (s.interior || {}).level || "simple";

  function floorOf(s) {
    return (s.interior && typeof s.interior.floor_y === "number" && s.interior.floor_y) || (s.doors && typeof s.doors.y0 === "number" && s.doors.y0) || 1.2;
  }
  function cabDefaults(s) {
    const hw = s.width / 2, half = s.length / 2 - ((s.body || {}).end_inset !== undefined ? s.body.end_inset : 0.35), f = floorOf(s);
    return {
      windscreen: { z0: 0.1, z1: r4(hw - 0.32), y0: r4(f + 1.0), y1: r4(f + 1.8), split: true, frame: 0.06, frame_offset: 0.04, glass_offset: 0.045 },
      side_lights: [{ y: r4(f + 0.1), z: r4(hw - 0.4), radius: 0.1, depth: 0.07, offset: 0.07, paint: "headlamp" },
        { y: r4(f + 0.1), z: r4(hw - 0.7), radius: 0.07, depth: 0.07, offset: 0.07, paint: "tail_lamp" }],
      center_lights: [{ y: r4(f + 2.15), z: 0, radius: 0.09, depth: 0.07, offset: 0.07, paint: "headlamp" }],
      chevrons: null, horns: null,
      interior: { x: r4(half - 1.1), floor: f, length: 1.6 },
    };
  }
  function doorDefaults(s) {
    const f = floorOf(s);
    return { width: 1.3, y0: f, y1: r4(f + 1.9), leaves: 2, travel: 0.68, open_seconds: 1.6, close_seconds: 0.7, pocket_inset: 0.035, thickness: 0.036,
      window: { margin: 0.12, y0: 0.95, y1: 1.6 }, paint: "secondary", inner_paint: "interior_wall", threshold: true, grab_handles: true };
  }
  function gangDefaults(s) {
    const f = floorOf(s);
    return { offset: 0.015, center_y: r4(f + 1.09), height: 2.12, width: 0.97, depth: 0.12, paint: "gasket",
      door: { center_y: r4(f + 1.08), height: 1.91, width: 0.72, thickness: 0.028, offset: 0.071, paint: "secondary" },
      window: { y0: r4(f + 1.29), y1: r4(f + 1.86), half_width: 0.25, offset: 0.09 } };
  }

  const F = (p, t, zh, en, extra) => Object.assign({ p, t, l: [zh, en] }, extra || {});
  const isImport = (s) => !!(s && s.body && s.body.style === "import");

  // the form of a model imported from GLB files
  function importSchema(s) {
    return [
      { id: "unit", l: ["车辆", "Unit"], f: [
        F("unit_id", "text", "车辆 id（unit_id）", "Unit id (unit_id)", { w: 1, h: ["必须与模组 mod.txt 中某个 [TrainUnit] 的 id= 完全一致。", "Must be exactly the id= of a [TrainUnit] in the mod's mod.txt."] }),
        F("label", "text", "名称", "Name", { w: 1 }),
        F("kind", "sel", "类型", "Kind", { opts: KIND_OPTS }),
        F("length", "num", "长度（写进清单）", "Length (in the manifest)", { u: "m", h: ["与 mod.txt 的 length= 相同；附加组件按它摆放模型", "As length= in mod.txt; the add-on places the model by it"] }),
        F("width", "num", "宽度（写进清单）", "Width (in the manifest)", { u: "m" }),
      ] },
      { id: "import", l: ["导入的模型（GLB）", "Imported model (GLB)"], f: [
        { t: "note", l: ["模型来自你在 Blender 等软件里做的 GLB 文件。LOD1、LOD2 可以各给一个文件；不给就由 LOD0 自动生成（去掉小零件和车内、合并顶点）。改了 GLB 文件后预览会自动更新。", "The model comes from GLB files you made in Blender or another program. LOD1 and LOD2 may have files of their own; without, they are made from LOD0 (small parts and the interior left out, vertices merged). The preview follows when you export the GLB again."] },
        { t: "lodfiles", w: 1 },
        F("import.scale", "num", "缩放", "Scale", { h: ["厘米建模填 0.01", "0.01 for a model made in centimetres"] }),
        F("import.turn", "chk", "掉头（模型的前端朝 −X）", "Turn around (the model's front faces −X)"),
        F("import.offset", "list", "平移 x, y, z", "Move by x, y, z", { u: "m", w: 1 }),
        { t: "tool", id: "place", w: 1 },
        F("import.lod2_drop_interior", "chk", "LOD2 去掉车内（interior_*）", "LOD2 without the interior (interior_*)"),
        F("import.lod1_drop_below", "num", "LOD1 去掉小于此尺寸的零件", "LOD1 leaves out parts smaller than", { u: "m" }),
        F("import.lod2_drop_below", "num", "LOD2 去掉小于此尺寸的零件", "LOD2 leaves out parts smaller than", { u: "m" }),
        F("import.lod1_cell", "num", "LOD1 顶点合并间距", "LOD1 merges vertices closer than", { u: "m" }),
        F("import.lod2_cell", "num", "LOD2 顶点合并间距", "LOD2 merges vertices closer than", { u: "m" }),
        { t: "report", w: 1 },
      ] },
      { id: "livery", l: ["材质颜色", "Material colours"], f: [
        { t: "note", l: ["材质来自 GLB；可以在这里改颜色（也可以用旁边模组图片的吸管）。贴图不会被使用。", "The materials come from the GLB; change their colours here (or with the eyedropper on the mod's picture). Textures are not used."] },
        { t: "mats", w: 1 },
      ] },
      { id: "meta", l: ["文件信息", "File information"], f: [
        F("meta.generator", "text", "生成器名称（写进 GLB）", "Generator name (in the GLB)", { w: 1 }),
        F("meta.asset_version", "text", "模型版本", "Model version"),
        F("meta.dimension_source", "text", "尺寸来源说明", "Where the dimensions come from", { w: 1 }),
      ] },
      { id: "advanced", l: ["高级：整个规格的 JSON", "Advanced: the whole spec as JSON"], f: [{ p: "", t: "json", w: 1, l: ["规格", "Spec"], big: 1 }] },
    ];
  }

  function schema(s) {
    if (isImport(s)) return importSchema(s);
    const car = isCar(s);
    const groups = [];
    groups.push({ id: "unit", l: ["车辆", "Unit"], f: [
      F("unit_id", "text", "车辆 id（unit_id）", "Unit id (unit_id)", { w: 1, h: ["必须与模组 mod.txt 中某个 [TrainUnit] 的 id= 完全一致（大小写也一样）。导出时可以从模组的车辆列表里选。", "Must be exactly the id= of a [TrainUnit] in the mod's mod.txt (same case). You can pick it from the mod's units when exporting."] }),
      F("label", "text", "名称", "Name", { w: 1 }),
      F("kind", "sel", "类型", "Kind", { opts: KIND_OPTS }),
      F("body.style", "style", "车体样式", "Body style", { opts: STYLE_OPTS }),
      F("length", "num", "长度", "Length", { u: "m", h: ["与 mod.txt 的 length= 相同（含车钩）", "As length= in mod.txt (couplers included)"] }),
      F("width", "num", "宽度", "Width", { u: "m", h: ["与 mod.txt 的 width= 相同", "As width= in mod.txt"] }),
      F("height", "num", "高度", "Height", { u: "m", h: [car ? "参考值；车体高度以断面最上一层为准" : "参考值；高度由截面决定", car ? "For reference: the profile's top level is what is built" : "For reference: the sections set the height"] }),
      { t: "tool", id: "stretch", w: 1 },
    ] });
    const paints = [
      car ? F("body.end_paint", "paint", "车端", "Ends") : F("hood.end_paint", "paint", "车端", "Ends"),
      car && F("body.underside_paint", "paint", "车底", "Underside"),
      hasDoors(s) && F("doors.paint", "paint", "车门外侧", "Doors (outside)"),
      hasDoors(s) && F("doors.inner_paint", "paint", "车门内侧", "Doors (inside)"),
    ].filter(Boolean);
    groups.push({ id: "livery", l: ["涂装与材质", "Livery and materials"], f: [
      { t: "note", l: ["颜色是材质的颜色；车身各条色带用哪个材质在“车体断面”里设，罩式机车在“罩式车体”里设。线性颜色与屏幕颜色之间的换算与附加组件相同。", "Colours belong to materials; which material each band of the body uses is set under Body shape (Hood body for a hood unit). The editor converts to and from linear colour as the add-on does."] },
      { t: "mats", w: 1 },
      ...paints,
    ] });
    if (car) {
      groups.push({ id: "shape", l: ["车体断面", "Body shape"], f: [
        { t: "note", l: ["断面从侧墙底部一层层往上，到车顶中线结束（最后一层 w = 0）。y 是高度（米），w 是这一层的半宽占车宽一半的比例，颜色是这一层到下一层之间色带的材质。", "The cross-section, level by level from the bottom of the side up to the middle of the roof (the last level has w = 0). y is the height (m), w the half width as a share of half the car's width, paint the material of the band from this level up to the next."] },
        { p: "body.profile", t: "table", w: 1, cols: [{ k: "y", t: "num", l: ["高度 y", "y"] }, { k: "w", t: "num", l: ["半宽比 w", "w"] }, { k: "paint", t: "paint", l: ["色带材质", "Band paint"] }],
          def: (rows) => { const last = rows[rows.length - 1] || { y: 1, w: 1, paint: "secondary" }; return { y: r4(last.y + 0.2), w: last.w, paint: last.paint }; } },
        F("body.stations", "list", "截面位置 x", "Stations x", { w: 1, u: "m", h: ["沿车长放截面的 x（车中心为 0），两端自动加上。端部收顶在这些截面之间过渡。", "Where loft sections stand along the car (0 is the middle); the two ends are added. The end taper blends between them."] }),
        F("body.end_inset", "num", "车体端部内缩", "Body end inset", { u: "m", h: ["车体端面距车辆总长两端的距离（留给车钩和风挡）", "From each end of the length to the body (room for couplers and gangways)"] }),
        F("body.aperture_min_z", "num", "开洞的最小半宽", "Holes cut where wider than", { u: "m", h: ["只有半宽大于此值的色带才开窗洞门洞", "Window and door holes are cut only in bands whose half width is more than this"] }),
        F("body.end_taper.start", "num", "端部收顶：从 |x|", "End taper: from |x|", { u: "m" }),
        F("body.end_taper.roof_drop", "num", "车顶在端部降低", "Roof drop at the ends", { u: "m", h: ["0 = 不收顶", "0 = no taper"] }),
        F("body.end_taper.roof_from", "num", "从此高度往上收", "Taper above height", { u: "m" }),
        F("body.end_taper.roof_span", "num", "收顶高度范围", "Taper height span", { u: "m" }),
        F("body.end_skirt.rise", "num", "端部裙板抬高", "End skirt rise", { u: "m", h: ["0 = 不抬高", "0 = none"] }),
        F("body.end_skirt.below", "num", "裙板：低于此高度的层", "Skirt: levels below", { u: "m" }),
        F("body.end_skirt.base", "num", "裙板起始高度", "Skirt base height", { u: "m" }),
        F("body.end_skirt.from", "num", "裙板从 |x| 开始抬", "Skirt rises from |x|", { u: "m" }),
        F("body.end_skirt.length", "num", "裙板抬升长度", "Skirt rise length", { u: "m" }),
        F("body.center_y", "num", "车体中心高度", "Body centre height", { u: "m", h: ["只用来判断面的朝向", "Only used to tell which way faces point"] }),
        F("body.lining.inset", "num", "内衬厚度", "Lining inset", { u: "m", h: ["车内墙板离外壳的距离（门扇在两者之间滑动）", "Inner wall panels' distance from the shell (door leaves slide between)"] }),
        F("body.lining.roof_from", "num", "内衬车顶：高于", "Roof lining above", { u: "m" }),
      ] });
      groups.push({ id: "windows", l: ["车窗", "Windows"], f: [
        { t: "note", l: ["每一排窗：下沿 y0、上沿 y1、窗宽和各窗中心的 x（米，用逗号分隔）。窗洞是真的开在车身上的。", "Each row: bottom y0, top y1, window width, and each window's centre x (metres, comma separated). The holes are cut through the body."] },
        { p: "windows", t: "table", w: 1, cols: [{ k: "y0", t: "num", l: ["下沿 y0", "y0"] }, { k: "y1", t: "num", l: ["上沿 y1", "y1"] }, { k: "width", t: "num", l: ["窗宽", "Width"] }, { k: "centers", t: "list", l: ["中心 x 列表", "Centres x"], wide: 1 }],
          def: (rows) => (rows.length ? clone(rows[rows.length - 1]) : { y0: r4(floorOf(s) + 0.82), y1: r4(floorOf(s) + 1.72), width: 1.2, centers: [] }) },
        F("window_frame.border", "num", "窗框宽", "Frame width", { u: "m" }),
        F("window_frame.glass_inset", "num", "玻璃内缩", "Glass inset", { u: "m" }),
        F("window_frame.reveal", "num", "窗洞侧面深", "Reveal depth", { u: "m" }),
        { t: "tool", id: "arrange", w: 1 },
      ] });
      const d = hasDoors(s);
      const leaves = (s.doors || {}).leaves || 2;
      groups.push({ id: "doors", l: ["客室车门", "Passenger doors"], f: [
        F("doors.centers", "list", "门中心 x 列表", "Door centres x", { w: 1, u: "m", rr: 1, h: ["每侧的门（两侧对称）。门扇在开站台门时滑开；附加组件按车厢左右分别开门。", "The doors of each side (both sides alike). Their leaves slide open when the add-on opens that side's doors at a platform."] }),
        d && F("doors.width", "num", "门洞宽", "Doorway width", { u: "m" }),
        d && F("doors.leaves", "sel", "门扇", "Leaves", { opts: LEAF_OPTS, rr: 1 }),
        d && F("doors.y0", "num", "门底 y0", "Door bottom y0", { u: "m" }),
        d && F("doors.y1", "num", "门顶 y1", "Door top y1", { u: "m" }),
        d && leaves === 1 && F("doors.single_direction", "sel", "滑向", "Slides", { opts: DIR_OPTS }),
        d && F("doors.travel", "num", "滑动距离", "Slide travel", { u: "m", h: ["每扇门打开时滑动多远（GOV2 上限 2 米）", "How far each leaf slides open (GOV2 allows up to 2 m)"] }),
        d && F("doors.open_seconds", "num", "开门时间", "Opening time", { u: "s" }),
        d && F("doors.close_seconds", "num", "关门时间", "Closing time", { u: "s" }),
        d && F("doors.window", "opt", "门上有窗", "Window in the leaf", { def: () => ({ margin: 0.11, y0: 0.96, y1: 1.55 }) }),
        d && s.doors && s.doors.window && F("doors.window.margin", "num", "门窗边距", "Window margin", { u: "m" }),
        d && s.doors && s.doors.window && F("doors.window.y0", "num", "门窗下沿（距门底）", "Window bottom (above door bottom)", { u: "m" }),
        d && s.doors && s.doors.window && F("doors.window.y1", "num", "门窗上沿（距门底）", "Window top (above door bottom)", { u: "m" }),
        d && F("doors.threshold", "chk", "黄色门槛", "Yellow threshold"),
        d && F("doors.grab_handles", "chk", "门边扶手", "Grab handles"),
        d && F("doors.thickness", "num", "门扇厚", "Leaf thickness", { u: "m" }),
        d && F("doors.pocket_inset", "num", "门袋深（离外壳）", "Pocket inset", { u: "m" }),
      ].filter(Boolean) });
      const c = hasCab(s);
      const cf = [F("cab.ends", "cab", "司机室", "Cabs", { opts: CAB_OPTS, h: ["+X 是车辆前端。控制车的司机室在 +X；编组里车辆可以翻转（mod.txt 的 flip）。", "+X is the vehicle's front. A cab car has its cab at +X; consists can flip a vehicle (flip in mod.txt)."] })];
      if (c) {
        cf.push(
          F("cab.windscreen.split", "chk", "两块前窗（中间有立柱）", "Two windscreen panes (a centre post)", { rr: 1 }),
          F("cab.windscreen.z0", "num", "前窗内缘 z0", "Windscreen inner edge z0", { u: "m" }),
          F("cab.windscreen.z1", "num", "前窗外缘 z1", "Windscreen outer edge z1", { u: "m" }),
          F("cab.windscreen.y0", "num", "前窗下沿", "Windscreen bottom", { u: "m" }),
          F("cab.windscreen.y1", "num", "前窗上沿", "Windscreen top", { u: "m" }),
          { t: "note", l: ["车灯：每侧灯（左右对称，z 为到中线的距离）和中间的灯（z 照写）。", "Lamps: side lamps (mirrored, z from the middle) and middle lamps (z as given)."] },
          { p: "cab.side_lights", t: "table", w: 1, cols: [{ k: "y", t: "num", l: ["高 y", "y"] }, { k: "z", t: "num", l: ["z", "z"] }, { k: "radius", t: "num", l: ["半径", "Radius"] }, { k: "offset", t: "num", l: ["凸出", "Offset"] }, { k: "paint", t: "paint", l: ["材质", "Paint"] }],
            def: (rows) => (rows.length ? clone(rows[rows.length - 1]) : { y: r4(floorOf(s) + 0.1), z: r4(s.width / 2 - 0.4), radius: 0.1, depth: 0.07, offset: 0.07, paint: "headlamp" }) },
          { p: "cab.center_lights", t: "table", w: 1, cols: [{ k: "y", t: "num", l: ["高 y", "y"] }, { k: "z", t: "num", l: ["z", "z"] }, { k: "radius", t: "num", l: ["半径", "Radius"] }, { k: "offset", t: "num", l: ["凸出", "Offset"] }, { k: "paint", t: "paint", l: ["材质", "Paint"] }],
            def: (rows) => (rows.length ? clone(rows[rows.length - 1]) : { y: r4(floorOf(s) + 2.1), z: 0, radius: 0.09, depth: 0.07, offset: 0.07, paint: "headlamp" }) },
          F("cab.chevrons", "opt", "车头 V 形条纹", "Nose chevrons", { def: () => ({ rows: [r4(floorOf(s) - 0.2), r4(floorOf(s) + 0.13), r4(floorOf(s) + 0.46)], half_width: 0.34, rise: 0.16, height: 0.1, offset: 0.095, paint: "primary" }) }),
          s.cab && s.cab.chevrons && F("cab.chevrons.rows", "list", "条纹高度", "Stripe heights", { u: "m" }),
          s.cab && s.cab.chevrons && F("cab.chevrons.paint", "paint", "条纹材质", "Stripe paint"),
          F("cab.horns", "opt", "车顶风笛", "Roof horns", { def: () => ({ offset: 0.5, y: r4(((s.body || {}).profile || []).slice(-1)[0] ? s.body.profile.slice(-1)[0].y - 0.55 : 3.5), z: [-0.2, 0.2], radius: 0.07, length: 0.36, paint: "underframe" }) }),
          s.cab && s.cab.horns && F("cab.horns.y", "num", "风笛高度", "Horn height", { u: "m" }),
          s.cab && s.cab.horns && F("cab.horns.offset", "num", "风笛离车端", "Horns from the end", { u: "m" }),
        );
        if (ilevel(s) !== "none") {
          cf.push(
            F("cab.interior.x", "num", "司机室中心 |x|", "Cab centre |x|", { u: "m" }),
            F("cab.interior.floor", "num", "司机室地板高", "Cab floor height", { u: "m" }),
            F("cab.interior.length", "num", "司机室长", "Cab length", { u: "m" }),
          );
        }
      }
      groups.push({ id: "cab", l: ["司机室与车灯", "Cabs and lamps"], f: cf.filter(Boolean) });
      const gf = [F("gangway.ends", "gang", "贯通道（风挡）", "Gangways", { opts: GANG_OPTS })];
      if (hasGang(s)) {
        gf.push(
          F("gangway.center_y", "num", "风挡中心高", "Bellows centre height", { u: "m" }),
          F("gangway.height", "num", "风挡高", "Bellows height", { u: "m" }),
          F("gangway.width", "num", "风挡宽", "Bellows width", { u: "m" }),
          F("gangway.depth", "num", "风挡厚", "Bellows depth", { u: "m" }),
          F("gangway.door", "opt", "端门", "End door", { def: () => gangDefaults(s).door }),
          F("gangway.window", "opt", "端门窗", "End door window", { def: () => gangDefaults(s).window }),
        );
      }
      groups.push({ id: "gangway", l: ["贯通道", "Gangways"], f: gf });
      groups.push({ id: "roof", l: ["车顶设备", "Roof equipment"], f: [
        { t: "note", l: ["受电弓（降下状态，不会升起）和空调机组。高度自动贴在车顶上。", "Pantographs (lowered; they do not rise) and air-conditioning units. They sit on the roof by themselves."] },
        { p: "roof.pantographs", t: "table", w: 1, cols: [{ k: "x", t: "num", l: ["位置 x", "x"] }, { k: "head_width", t: "num", l: ["弓头宽", "Head width"] }, { k: "facing", t: "sel", opts: FACING_OPTS, l: ["朝向", "Facing"] }],
          def: () => ({ x: 0, head_width: 1.0, facing: 1 }) },
        { p: "roof.ac_units", t: "table", w: 1, cols: [{ k: "x", t: "num", l: ["位置 x", "x"] }, { k: "length", t: "num", l: ["长", "Length"] }, { k: "width", t: "num", l: ["宽", "Width"] }, { k: "height", t: "num", l: ["高", "Height"] }, { k: "paint", t: "paint", l: ["材质", "Paint"] }],
          def: () => ({ x: 0, length: 2.8, width: 1.6, height: 0.3, paint: "roof" }) },
      ] });
    }
    groups.push({ id: "running", l: ["走行部", "Running gear"], f: [
      F("bogies.pivot_fraction", "num", "转向架中心（车长比例）", "Bogie centres (share of length)", { h: ["两台转向架中心在 ±(长度 × 此值) 处", "The two bogies stand at ±(length × this)"] }),
      F("bogies.wheel_radius", "num", "车轮半径", "Wheel radius", { u: "m" }),
      F("bogies.axles", "list", "各轴位置（相对转向架中心）", "Axles (from the bogie centre)", { u: "m", w: 1 }),
      F("bogies.frame_length", "num", "构架长", "Frame length", { u: "m" }),
      F("bogies.side_frame_length", "num", "侧架长", "Side frame length", { u: "m" }),
      F("couplers.inset", "num", "车钩内缩", "Coupler inset", { u: "m" }),
      F("couplers.height", "num", "车钩高", "Coupler height", { u: "m" }),
      car && { p: "underfloor", t: "table", w: 1, cols: [{ k: "x", t: "num", l: ["x", "x"] }, { k: "y", t: "num", l: ["高 y", "y"] }, { k: "length", t: "num", l: ["长", "Length"] }, { k: "height", t: "num", l: ["高", "Height"] }, { k: "width", t: "num", l: ["宽", "Width"] }],
        def: () => ({ x: 0, y: 0.75, length: 2.4, height: 0.4, width: 1.9, paint: "underframe" }), title: ["车底设备箱", "Underfloor boxes"] },
    ].filter(Boolean) });
    const lay = (s.interior || {}).layout;
    groups.push({ id: "interior", l: ["车内", "Interior"], f: [
      F("interior.level", "sel", "车内细节", "Interior detail", { opts: LEVEL_OPTS, rr: 1, h: ["精细：LOD0 有座椅腿、扶手、操纵杆；LOD1 简化；LOD2 没有车内、玻璃不透明。", "Detailed: LOD0 has seat legs, armrests and levers; LOD1 simpler; LOD2 has no interior and opaque glass."] }),
      car && F("interior.layout", "sel", "布局", "Layout", { opts: LAYOUT_OPTS, rr: 1 }),
      car && lay === "single" && F("interior.floor_y", "num", "地板高", "Floor height", { u: "m" }),
      car && lay === "single" && F("interior.seat_pitch", "num", "座椅排距", "Seat pitch", { u: "m" }),
      car && lay === "single" && F("interior.aisle", "num", "过道宽", "Aisle width", { u: "m" }),
      car && lay === "bilevel" && { t: "note", l: ["双层布局用 GO BiLevel 的楼层、楼梯和座椅位置；要改数字，在“高级”里给 interior.bilevel 写覆盖值（键名见 trainmodel/interior.py）。", "The bi-level layout uses the GO BiLevel's floors, stairs and seats; to change its numbers, give overrides in interior.bilevel under Advanced (keys in trainmodel/interior.py)."] },
    ].filter(Boolean) });
    if (car) {
      groups.push({ id: "deco", l: ["标志与装饰", "Logo and trim"], f: [
        F("logo.type", "sel", "车身标志", "Side logo", { opts: LOGO_OPTS, rr: 1 }),
        s.logo && s.logo.type === "go" && F("logo.x", "num", "标志中心 x", "Logo centre x", { u: "m" }),
        s.logo && s.logo.type === "go" && F("logo.y", "num", "标志高度 y", "Logo height y", { u: "m" }),
        s.logo && s.logo.type === "go" && F("logo.scale", "num", "标志大小", "Logo size", { h: ["标志高约为此值的 2 倍（米）", "The mark is about twice this tall (m)"] }),
        F("side_ribs.heights", "list", "侧面压条高度（LOD0）", "Side trim heights (LOD0)", { u: "m", w: 1 }),
      ].filter(Boolean) });
    } else {
      groups.push({ id: "hood", l: ["罩式车体", "Hood body"], f: [
        { t: "note", l: ["车体由若干横截面放样而成：x、半宽、底、肩、顶（米）。每个截面一圈 10 段，各段材质在下面依次设定（0 = 左下……9 = 底）。门、窗、格栅、灯和台阶都在“细节部件”里。", "The body is lofted through sections: x, half width, floor, shoulder, roof (m). Each section has a ring of 10 segments whose materials are set below (0 = lower left ... 9 = bottom). Doors, windows, grilles, lamps and steps are in Details."] },
        { p: "hood.sections", t: "table", w: 1, arr: 1, cols: [{ k: 0, t: "num", l: ["x", "x"] }, { k: 1, t: "num", l: ["半宽", "Half width"] }, { k: 2, t: "num", l: ["底", "Floor"] }, { k: 3, t: "num", l: ["肩", "Shoulder"] }, { k: 4, t: "num", l: ["顶", "Roof"] }],
          def: (rows) => (rows.length ? clone(rows[rows.length - 1]).map((v, i) => (i === 0 ? r4(v + 1) : v)) : [0, 1.5, 1.4, 4, 4.5]) },
        { p: "hood.ring_paint", t: "paints", w: 1, n: 10, l: ["每圈 10 段的材质", "Materials of the 10 ring segments"] },
        F("hood.center_y", "num", "车体中心高度", "Body centre height", { u: "m" }),
        F("hood.cab_interior.x", "num", "司机室中心 x", "Cab centre x", { u: "m" }),
        F("hood.cab_interior.floor", "num", "司机室地板高", "Cab floor height", { u: "m" }),
        F("hood.cab_interior.length", "num", "司机室长", "Cab length", { u: "m" }),
        { p: "hood.apertures", t: "json", w: 1, l: ["开洞规则（前窗、侧窗）", "Aperture rules (windscreen, side windows)"] },
      ] });
    }
    groups.push({ id: "details", l: ["细节部件", "Details"], f: [
      { t: "note", l: ["附加的几何体，按顺序生成：box 方盒、cylinder 圆柱、bar 杆、face 面、aperture 开洞面、panel 侧板、grille 格栅、steps 台阶、spokes 辐条、logo 标志、slope_aperture / slope_face 斜前窗。放进 {\"type\": \"side\", \"items\": [...]} 的会在左右两侧各生成一次（z 取镜像）。\"lods\": [0, 1] 表示只在这些细节层级出现。", "Extra geometry, made in order: box, cylinder, bar, face, aperture, panel, grille, steps, spokes, logo, slope_aperture / slope_face (a sloping windscreen). Items inside {\"type\": \"side\", \"items\": [...]} are made on both sides (z mirrored). \"lods\": [0, 1] keeps an item to those levels of detail."] },
      { p: "details", t: "json", w: 1, l: ["details 列表", "The details list"] },
    ] });
    groups.push({ id: "meta", l: ["文件信息", "File information"], f: [
      F("meta.generator", "text", "生成器名称（写进 GLB）", "Generator name (in the GLB)", { w: 1 }),
      F("meta.asset_version", "text", "模型版本", "Model version"),
      F("meta.dimension_source", "text", "尺寸来源说明", "Where the dimensions come from", { w: 1 }),
    ] });
    groups.push({ id: "advanced", l: ["高级：整个规格的 JSON", "Advanced: the whole spec as JSON"], f: [
      { t: "note", l: ["这里可以改任何一项（包括表单里没有的）。改完点“应用”。", "Change anything here, including what the form does not show, then press Apply."] },
      { p: "", t: "json", w: 1, l: ["规格", "Spec"], big: 1 },
    ] });
    return groups;
  }

  // ------------------------------------------------------------------ state (kept while the app runs)
  const state = {
    specs: [], cur: 0, dirty: [], source: null, examples: null, exampleName: null, open: new Set(["unit", "livery"]), tutOpen: true,
    lod: 0, wire: false, cut: false, side: "both", open01: 0, problems: { errors: [], warnings: [] }, stats: null, built: false,
    mods: null, modSel: null, modInfo: null, include: {}, source_id: "", glb: false, includeSpec: true, result: null, busy: 0,
    stretch: null, arrangeN: null, buildError: null, addonScansLocal: false, first: true,
    // the unit picked in the mod (the target card), its sprite, the guide, an import's report
    unitSel: null, sprite: null, spriteKey: null, spriteOpts: { on: {}, tint: {}, overlay: true, target: "primary", zoom: 1 },
    guide: { on: false, step: 0 }, report: null, includeSources: false,
  };
  let viewer = null;
  let timer = 0;
  let seq = 0;
  let offLang = null;
  let themeObs = null;
  let mediaQ = null;

  const cur = () => state.specs[state.cur];

  // ------------------------------------------------------------------ rendering
  function render() {
    if (!root) return;
    const keepCanvas = root.querySelector(".te-canvas-wrap canvas");
    root.innerHTML = `<div class="te">${headHTML()}${tutorialHTML()}${targetHTML()}<div class="te-main"><div class="te-left">${tabsHTML()}<div class="te-form"></div></div>
      <div class="te-right">${guideHTML()}${viewHTML()}${spriteHTML()}</div></div>${exportHTML()}</div>`;
    const wrap = root.querySelector(".te-canvas-wrap");
    if (keepCanvas && viewer) {
      wrap.insertBefore(keepCanvas, wrap.firstChild);
    } else {
      const c = document.createElement("canvas");
      c.tabIndex = 0;
      c.setAttribute("aria-label", T("列车三维预览：拖动旋转，滚轮缩放，右键或 Shift 拖动平移，双击复位", "Train preview: drag to turn, wheel to zoom, right-drag or Shift-drag to pan, double-click to reset"));
      wrap.insertBefore(c, wrap.firstChild);
      if (viewer) viewer.destroy();
      viewer = new Viewer(c, (st) => {
        if (st === "u32") toast(T("这块显卡的 WebGL 画不了这么多顶点", "This graphics card's WebGL cannot draw this many vertices"), "warn");
      });
      viewer.onDoor = (v) => { const r = root && root.querySelector("#te-door"); if (r) r.value = Math.round(v * 100); };
      if (!viewer.ok) wrap.insertAdjacentHTML("beforeend", `<div class="te-nogl">${esc(T("这里无法使用 WebGL，看不到预览；仍可编辑和导出。", "WebGL is not available here, so there is no preview; editing and exporting still work."))}</div>`);
    }
    if (viewer) { viewer.wire = state.wire; viewer.cut = state.cut; viewer.setDoors(state.open01, state.side); }
    renderForm();
    renderStats();
    renderProblems();
    bindSprite();
    drawSprite();
    highlightGuide(false);
  }

  function headHTML() {
    const ex = (state.examples && state.examples.examples) || [];
    return `<section class="card te-head" style="--i:0">
      <div class="card-icon"><svg class="i" viewBox="0 0 24 24" aria-hidden="true">${TRAIN_ICON_PATHS}</svg></div>
      <div class="te-head-text"><h1>${esc(T("列车编辑器", "Train editor"))}</h1>
        <p>${esc(T("为模组里的车辆做三维模型：改参数、看预览、导出到模组的 nimby3d 文件夹。附加组件在游戏里用这些模型画车。", "Make 3D models for a mod's vehicles: set the parameters, look at the preview, export into the mod's nimby3d folder. The add-on draws the trains in game with them."))}</p></div>
      <div class="te-head-actions">
        <select class="te-sel" id="te-example" style="width:auto;max-width:260px" aria-label="${esc(T("示例", "Examples"))}">
          <option value="">${esc(T("打开示例……", "Open an example…"))}</option>
          ${ex.map((e) => `<option value="${esc(e.name)}">${esc(TT([e.title.zh, e.title.en]))}</option>`).join("")}
        </select>
        <select class="te-sel" id="te-new" style="width:auto" aria-label="${esc(T("新建", "New"))}">
          <option value="">${esc(T("新建车辆……", "New vehicle…"))}</option>
          <option value="emu">${esc(T("动车组车厢（带司机室）", "Multiple-unit car (with a cab)"))}</option>
          <option value="coach">${esc(T("客车", "Coach"))}</option>
          <option value="cab_car">${esc(T("控制车", "Cab car"))}</option>
          <option value="locomotive:hood">${esc(T("罩式内燃机车", "Hood diesel locomotive"))}</option>
          <option value="locomotive:carbody">${esc(T("箱形电力机车（两端司机室）", "Box-cab electric (two cabs)"))}</option>
        </select>
        <button type="button" class="btn btn-sm btn-ghost" data-act="import-glb" title="${esc(T("导入你在 Blender 等软件里做的模型（.glb）", "Import a model you made in Blender or another program (.glb)"))}">${icon("i-cube")}<span>${esc(T("导入 GLB", "Import GLB"))}</span></button>
        <button type="button" class="btn btn-sm btn-ghost" data-act="load-spec">${icon("i-folder-open")}<span>${esc(T("打开规格", "Open spec"))}</span></button>
        <button type="button" class="btn btn-sm btn-ghost" data-act="save-spec">${icon("i-download")}<span>${esc(T("保存规格", "Save spec"))}</span></button>
        <button type="button" class="btn btn-sm te-guide-btn" data-act="guide-open" aria-pressed="${state.guide.on}">${icon("i-help")}<span>${esc(T("一步步教我做", "Guide me step by step"))}</span></button>
      </div></section>`;
  }

  function tabsHTML() {
    if (!state.specs.length) return `<div class="card te-tabs">${esc(T("没有打开的车辆", "No vehicle open"))}</div>`;
    return `<div class="card te-tabs" role="tablist">${state.specs.map((s, i) => `<span class="te-tab" role="tab" data-act="tab" data-i="${i}" aria-selected="${i === state.cur}" tabindex="0">
        ${state.dirty[i] ? '<span class="te-dot" title="' + esc(T("有未保存的修改", "Unsaved changes")) + '"></span>' : ""}${esc(s.unit_id || "?")}
        <button type="button" class="te-x" data-act="close-tab" data-i="${i}" aria-label="${esc(T("关闭", "Close"))}">${icon("i-x")}</button></span>`).join("")}
      <button type="button" class="te-tab te-tab-add" data-act="dup-tab" title="${esc(T("复制当前车辆为新的一页", "Copy this vehicle into a new tab"))}">+ ${esc(T("复制", "Copy"))}</button></div>`;
  }

  function viewHTML() {
    const lods = [0, 1, 2].map((l) => `<button type="button" data-act="lod" data-lod="${l}" aria-pressed="${state.lod === l}">LOD${l}</button>`).join("");
    return `<section class="card te-view" style="--i:2">
      <div class="te-view-bar">
        <div class="seg" role="group" aria-label="LOD">${lods}</div>
        <label class="te-slider">${esc(T("车门", "Doors"))}<input type="range" id="te-door" min="0" max="100" value="${Math.round(state.open01 * 100)}"></label>
        <select class="te-sel" id="te-side" aria-label="${esc(T("哪一侧", "Which side"))}">
          ${[["both", "两侧", "Both sides"], ["left", "左侧（−Z）", "Left (−Z)"], ["right", "右侧（+Z）", "Right (+Z)"]].map((o) => `<option value="${o[0]}"${state.side === o[0] ? " selected" : ""}>${esc(T(o[1], o[2]))}</option>`).join("")}
        </select>
        <button type="button" class="te-toggle" data-act="play" aria-pressed="${!!(viewer && viewer.anim)}">${icon("i-play")}${esc(T("开关门", "Cycle"))}</button>
        <span class="te-spacer"></span>
        <button type="button" class="te-toggle" data-act="wire" aria-pressed="${state.wire}">${esc(T("线框", "Wireframe"))}</button>
        <button type="button" class="te-toggle" data-act="cut" aria-pressed="${state.cut}" title="${esc(T("切掉靠近你的一半，看车内", "Cut away the half nearest you to see inside"))}">${esc(T("剖视", "Section"))}</button>
        <div class="seg" role="group" aria-label="${esc(T("视角", "View"))}">
          <button type="button" data-act="view" data-v="three">3/4</button><button type="button" data-act="view" data-v="side">${esc(T("侧", "Side"))}</button><button type="button" data-act="view" data-v="front">${esc(T("前", "Front"))}</button><button type="button" data-act="view" data-v="top">${esc(T("顶", "Top"))}</button>
        </div>
      </div>
      <div class="te-canvas-wrap"><div class="te-overlay"><span class="te-busy" id="te-busy"></span><span>${esc(T("拖动旋转 · 滚轮缩放 · 右键平移 · 双击复位", "Drag to turn · wheel to zoom · right-drag to pan · double-click to reset"))}</span></div><div id="te-stale-slot"></div></div>
      <div class="te-stats" id="te-stats"></div>
      <div class="te-problems" id="te-problems"></div>
    </section>`;
  }

  function renderStats() {
    const el = root && root.querySelector("#te-stats");
    if (!el) return;
    const st = state.stats;
    el.innerHTML = [0, 1, 2].map((l) => {
      const s = st && st[l];
      return `<button type="button" class="te-stat" data-act="lod" data-lod="${l}" aria-current="${state.lod === l}">
        <div class="te-lod">LOD${l} · ${esc(T(["近处", "中距离", "远处"][l], ["near", "middle", "far"][l]))}</div>
        <div class="te-tri">${s ? num(s.triangles) : "—"} <span class="te-sub" style="font:500 11px var(--font)">${esc(T("三角形", "triangles"))}</span></div>
        <div class="te-sub">${s ? `${num(s.vertices)} ${esc(T("顶点", "vertices"))} · ${s.parts} ${esc(T("部件", "parts"))}${s.bytes ? " · " + kb(s.bytes) : ""}` : "&nbsp;"}</div></button>`;
    }).join("");
  }

  function renderProblems() {
    const el = root && root.querySelector("#te-problems");
    if (!el) return;
    const p = state.problems || { errors: [], warnings: [] };
    const rows = [];
    if (state.buildError) rows.push(`<div class="te-prob te-err">${icon("i-x-circle")}<span>${esc(state.buildError)}</span></div>`);
    for (const e of p.errors.slice(0, 12)) rows.push(`<div class="te-prob te-err" data-path="${esc(dotPath(e.path))}">${icon("i-x-circle")}<span><span class="te-path">${esc(e.path)}</span>${esc(T(e.zh, e.en))}</span></div>`);
    for (const w of p.warnings.slice(0, 12)) rows.push(`<div class="te-prob te-warn" data-path="${esc(dotPath(w.path))}">${icon("i-alert")}<span><span class="te-path">${esc(w.path)}</span>${esc(T(w.zh, w.en))}</span></div>`);
    for (const l of state.limits || []) rows.push(`<div class="te-prob te-err">${icon("i-x-circle")}<span>${esc(l)}</span></div>`);
    if (p.errors.length > 12 || p.warnings.length > 12) rows.push(`<div class="te-prob">${icon("i-info")}<span>${esc(T("还有更多，修好上面的再看。", "There are more; fix these first."))}</span></div>`);
    el.innerHTML = rows.join("");
    const slot = root.querySelector("#te-stale-slot");
    if (slot) {
      const first = p.errors[0];
      slot.innerHTML = first || state.buildError ? `<div class="te-stale">${icon("i-alert")}<span>${esc(T("规格有错误，预览停在上一次能生成的样子：", "The spec has errors; the preview shows the last model that could be built: "))}${esc(first ? first.path + " — " + T(first.zh, first.en) : state.buildError)}</span></div>` : "";
    }
    // mark fields
    root.querySelectorAll(".te-bad, .te-warned").forEach((x) => x.classList.remove("te-bad", "te-warned"));
    const mark = (list, cls) => {
      for (const e of list) {
        const path = dotPath(e.path);
        let el2 = root.querySelector(`[data-path="${CSS.escape(path)}"]`);
        if (!el2) {
          const parts = path.split(".");
          while (parts.length > 1 && !el2) { parts.pop(); el2 = root.querySelector(`[data-path="${CSS.escape(parts.join("."))}"]`); }
        }
        if (el2) el2.classList.add(cls);
      }
    };
    mark(p.warnings, "te-warned");
    mark(p.errors, "te-bad");
    // counts on group heads
    root.querySelectorAll(".te-group").forEach((g) => {
      const cnt = g.querySelector(".te-count");
      if (!cnt) return;
      const nb = g.querySelectorAll(".te-bad").length, nw = g.querySelectorAll(".te-warned").length;
      cnt.className = "te-count" + (nb ? " te-has-err" : nw ? " te-has-warn" : "");
      cnt.textContent = nb ? T(`${nb} 处错误`, `${nb} error${nb > 1 ? "s" : ""}`) : nw ? T(`${nw} 处提醒`, `${nw} warning${nw > 1 ? "s" : ""}`) : "";
    });
  }

  function paintOptions(sel, s) {
    const keys = Object.keys((s && s.materials) || {});
    if (sel !== undefined && sel !== null && !keys.includes(sel)) keys.push(sel);
    return keys.map((k) => `<option value="${esc(k)}"${k === sel ? " selected" : ""}>${esc(MAT_LABELS[k] ? TT(MAT_LABELS[k]) + " · " + k : k)}</option>`).join("");
  }

  function fieldHTML(f, s) {
    const wide = f.w ? " te-wide" : "";
    const lab = (extra) => `<span class="te-lab">${esc(TT(f.l))}${f.u ? `<i class="te-unit">${esc(f.u)}</i>` : ""}${extra || ""}</span>`;
    const hint = f.h ? `<span class="te-hint">${esc(TT(f.h))}</span>` : "";
    const v = f.p !== undefined ? getPath(s, f.p) : undefined;
    switch (f.t) {
      case "note": return `<div class="te-gnote">${esc(TT(f.l))}</div>`;
      case "text": return `<label class="te-field${wide}">${lab()}<input class="te-in" data-path="${esc(f.p)}" data-t="text" value="${esc(v)}" spellcheck="false" autocomplete="off">${hint}</label>`;
      case "num": return `<label class="te-field${wide}">${lab()}<input class="te-in te-num" data-path="${esc(f.p)}" data-t="num" inputmode="decimal" value="${esc(fmtNum(v))}" autocomplete="off">${hint}</label>`;
      case "list": return `<label class="te-field${wide}">${lab()}<input class="te-in te-num" data-path="${esc(f.p)}" data-t="list" ${f.rr ? 'data-rr="1"' : ""} value="${esc(Array.isArray(v) ? v.join(", ") : "")}" autocomplete="off">${hint}</label>`;
      case "sel": case "style": case "cab": case "gang": {
        const opts = f.opts.map((o, i) => `<option value="${i}"${o[0] === v ? " selected" : ""}>${esc(T(o[1], o[2]))}</option>`).join("");
        return `<label class="te-field${wide}">${lab()}<select class="te-sel" data-path="${esc(f.p)}" data-t="${f.t}" data-fid="${esc(f.p)}" ${f.rr ? 'data-rr="1"' : ""}>${opts}</select>${hint}</label>`;
      }
      case "paint": return `<label class="te-field${wide}">${lab()}<select class="te-sel" data-path="${esc(f.p)}" data-t="paint">${paintOptions(v, s)}</select>${hint}</label>`;
      case "chk": return `<label class="te-check${wide}"><input type="checkbox" data-path="${esc(f.p)}" data-t="chk" ${f.rr ? 'data-rr="1"' : ""}${v !== false && v !== undefined && v !== null ? " checked" : ""}>${esc(TT(f.l))}</label>`;
      case "opt": return `<label class="te-check${wide}"><input type="checkbox" data-path="${esc(f.p)}" data-t="opt" data-fid="${esc(f.p)}"${v ? " checked" : ""}>${esc(TT(f.l))}</label>`;
      case "table": return tableHTML(f, s, v);
      case "paints": {
        const arr = Array.isArray(v) ? v : [];
        return `<div class="te-field te-wide">${lab()}<div class="te-trow" style="grid-template-columns:repeat(5,minmax(0,1fr))">${Array.from({ length: f.n }, (_, i) => `<select class="te-sel" data-path="${esc(f.p + "." + i)}" data-t="paint" title="${i}">${paintOptions(arr[i], s)}</select>`).join("")}</div></div>`;
      }
      case "json": {
        const text = JSON.stringify(f.p ? (v === undefined ? null : v) : s, null, 1);
        return `<div class="te-field te-wide">${lab()}<textarea class="te-area" data-json="${esc(f.p)}" spellcheck="false" style="min-height:${f.big ? 320 : 170}px">${esc(text)}</textarea>
          <div class="te-table-foot"><button type="button" class="btn btn-sm btn-ghost" data-act="json-apply" data-p="${esc(f.p)}">${icon("i-check")}${esc(T("应用", "Apply"))}</button>
          ${f.big ? `<button type="button" class="btn btn-sm btn-ghost" data-act="json-copy">${esc(T("复制", "Copy"))}</button>` : ""}</div></div>`;
      }
      case "mats": return matsHTML(s);
      case "tool": return toolHTML(f.id, s);
      case "lodfiles": return lodFilesHTML(s);
      case "report": return importReportHTML();
      default: return "";
    }
  }

  function tableHTML(f, s, v) {
    const rows = Array.isArray(v) ? v : [];
    const cols = f.cols;
    const tpl = cols.map((c) => (c.wide ? "minmax(0,2.4fr)" : c.t === "paint" || c.t === "sel" ? "minmax(0,1.3fr)" : "minmax(0,1fr)")).join(" ") + " 28px";
    const head = `<div class="te-table-head" style="grid-template-columns:${tpl}">${cols.map((c) => `<span>${esc(TT(c.l))}</span>`).join("")}<span></span></div>`;
    const body = rows.map((r, i) => `<div class="te-trow" style="grid-template-columns:${tpl}">${cols.map((c) => {
      const p = `${f.p}.${i}.${c.k}`;
      const cv = r === null || r === undefined ? undefined : r[c.k];
      if (c.t === "paint") return `<select class="te-sel" data-path="${esc(p)}" data-t="paint">${paintOptions(cv, s)}</select>`;
      if (c.t === "sel") return `<select class="te-sel" data-path="${esc(p)}" data-t="selv" data-opts='${esc(JSON.stringify(c.opts.map((o) => o[0])))}'>${c.opts.map((o) => `<option${o[0] === cv ? " selected" : ""}>${esc(T(o[1], o[2]))}</option>`).join("")}</select>`;
      if (c.t === "list") return `<input class="te-in te-num" data-path="${esc(p)}" data-t="list" value="${esc(Array.isArray(cv) ? cv.join(", ") : "")}" autocomplete="off">`;
      return `<input class="te-in te-num" data-path="${esc(p)}" data-t="num" inputmode="decimal" value="${esc(fmtNum(cv))}" autocomplete="off">`;
    }).join("")}<button type="button" class="te-icon-btn te-del" data-act="row-del" data-p="${esc(f.p)}" data-i="${i}" aria-label="${esc(T("删除这一行", "Remove this row"))}">${icon("i-x")}</button></div>`).join("");
    return `<div class="te-table" data-path="${esc(f.p)}">${f.title ? `<span class="te-lab">${esc(TT(f.title))}</span>` : ""}${head}${body}
      <div class="te-table-foot"><button type="button" class="btn btn-sm btn-ghost" data-act="row-add" data-p="${esc(f.p)}" data-fid="${esc(f.p)}">+ ${esc(T("添加一行", "Add a row"))}</button>
      ${rows.length ? "" : `<span class="te-hint">${esc(T("（空）", "(none)"))}</span>`}</div></div>`;
  }

  function matsHTML(s) {
    const m = s.materials || {};
    const rows = Object.keys(m).map((k) => {
      const mt = m[k] || {};
      const std = !!MAT_LABELS[k];
      const em = mt.emissive !== undefined && mt.emissive !== null;
      return `<div class="te-mat" data-path="materials.${esc(k)}">
        <input type="color" class="te-color" data-path="materials.${esc(k)}.color" data-t="color" value="${hexOf(mt.color)}" title="${esc(T("颜色", "Colour"))}">
        <div class="te-mat-name"><b>${esc(std ? TT(MAT_LABELS[k]) : k)}</b><input class="te-in" data-path="materials.${esc(k)}.name" data-t="text" value="${esc(mt.name || k)}" title="${esc(T("写进模型文件的材质名", "The material's name in the model file"))}" spellcheck="false"></div>
        <input class="te-in te-num" data-path="materials.${esc(k)}.metallic" data-t="num" value="${esc(fmtNum(mt.metallic !== undefined ? mt.metallic : 0))}" title="${esc(T("金属度 0..1", "Metallic 0..1"))}">
        <input class="te-in te-num" data-path="materials.${esc(k)}.roughness" data-t="num" value="${esc(fmtNum(mt.roughness !== undefined ? mt.roughness : 0.5))}" title="${esc(T("粗糙度 0..1", "Roughness 0..1"))}">
        <input class="te-in te-num" data-path="materials.${esc(k)}.alpha" data-t="num" value="${esc(fmtNum(mt.alpha !== undefined ? mt.alpha : 1))}" title="${esc(T("不透明度 0..1（玻璃用）", "Opacity 0..1 (for glass)"))}">
        ${std ? "<span></span>" : `<button type="button" class="te-icon-btn te-del" data-act="mat-del" data-k="${esc(k)}" aria-label="${esc(T("删除材质", "Remove material"))}">${icon("i-x")}</button>`}
        <div class="te-mat-emi"><label class="te-check" style="min-height:0"><input type="checkbox" data-act="emi" data-k="${esc(k)}"${em ? " checked" : ""}>${esc(T("自发光", "Glows"))}</label>
          ${em ? `<input type="color" class="te-color" data-path="materials.${esc(k)}.emissive" data-t="color" value="${hexOf(mt.emissive)}">` : ""}</div>
      </div>`;
    }).join("");
    return `<div class="te-mats"><div class="te-mat-head"><span></span><span>${esc(T("材质（名称）", "Material (name)"))}</span><span>${esc(T("金属", "Metal"))}</span><span>${esc(T("粗糙", "Rough"))}</span><span>${esc(T("不透明", "Opacity"))}</span><span></span></div>${rows}
      <div class="te-table-foot"><input class="te-in" id="te-newmat" placeholder="${esc(T("新材质名，如 stripe_red", "new key, e.g. stripe_red"))}" style="max-width:220px" spellcheck="false">
      <button type="button" class="btn btn-sm btn-ghost" data-act="mat-add">+ ${esc(T("添加材质", "Add material"))}</button></div></div>`;
  }

  function lodFilesHTML(s) {
    const lods = ((s.import || {}).lods || []).concat([null, null, null]).slice(0, 3);
    const base = (p) => String(p || "").split(/[\\/]/).pop();
    return `<div class="te-field te-wide" data-path="import.lods"><span class="te-lab">${esc(T("GLB 文件（每个细节层级）", "GLB files (one per level of detail)"))}</span>
      ${lods.map((p, i) => `<div class="te-lodrow"><b>LOD${i}</b>
        <span class="te-path" title="${esc(p || "")}">${p ? esc(base(p)) : `<i>${esc(T("由 LOD0 自动生成", "made from LOD0"))}</i>`}</span>
        <button type="button" class="btn btn-sm btn-ghost" data-act="pick-glb" data-lod="${i}">${icon("i-folder-open")}${esc(T("选择……", "Choose…"))}</button>
        ${i > 0 && p ? `<button type="button" class="te-icon-btn te-del" data-act="clear-glb" data-lod="${i}" aria-label="${esc(T("改为自动生成", "Make it from LOD0"))}">${icon("i-x")}</button>` : "<span></span>"}
      </div>`).join("")}</div>`;
  }

  function importReportHTML() {
    const r = state.report;
    if (!r || !r.box) return `<div class="te-gnote" id="te-imp-report">${esc(T("预览生成后，这里显示模型的尺寸和部件。", "The model's size and parts show here once the preview is built."))}</div>`;
    const b = r.box;
    const f2 = (v) => (Math.round(v * 100) / 100).toFixed(2);
    const roleNames = { vehicle_root: ["根", "root"], static: ["车体", "body"], interior: ["车内", "interior"], door_leaf: ["门扇", "door leaves"], bogie: ["转向架", "bogies"], wheelset: ["轮对", "wheelsets"], coupler: ["车钩", "couplers"] };
    const roles = Object.entries(r.roles || {}).filter(([k]) => k !== "vehicle_root").map(([k, n]) => `${n} ${esc(roleNames[k] ? T(roleNames[k][0], roleNames[k][1]) : k)}`).join(" · ");
    return `<div class="te-modinfo te-wide" id="te-imp-report">
      <div class="te-lab">${esc(T("导入的模型", "The imported model"))}</div>
      <div>${esc(T("尺寸", "Size"))}: <b>${f2(b.max[0] - b.min[0])} × ${f2(b.max[2] - b.min[2])} × ${f2(b.max[1] - b.min[1])}</b> m <span class="te-hint">(${esc(T("长 × 宽 × 高", "length × width × height"))})</span></div>
      <div class="te-hint">x ${f2(b.min[0])} … ${f2(b.max[0])} · y ${f2(b.min[1])} … ${f2(b.max[1])} · z ${f2(b.min[2])} … ${f2(b.max[2])}</div>
      <div class="te-hint">${r.parts} ${esc(T("个部件", "parts"))}: ${roles} · ${r.materials} ${esc(T("种材质", "materials"))}</div>
    </div>`;
  }

  function toolHTML(id, s) {
    if (id === "place") {
      return `<div class="te-field te-wide"><div class="te-row"><button type="button" class="btn btn-sm btn-ghost" data-act="place">${esc(T("居中并放到轨面上", "Centre it and put it on the rails"))}</button></div>
        <span class="te-hint">${esc(T("把模型的中心移到 x = 0、z = 0，最低点移到 y = 0（轨面）。", "Moves the model's middle to x = 0, z = 0 and its lowest point to y = 0 (the rail head)."))}</span></div>`;
    }
    if (id === "stretch") {
      const st = state.stretch || { length: s.length, width: s.width, height: s.height };
      return `<div class="te-field te-wide"><span class="te-lab">${esc(T("按新尺寸拉伸整个布局", "Stretch the whole layout to new dimensions"))}</span>
        <div class="te-row"><input class="te-in te-num" id="te-st-l" value="${esc(fmtNum(st.length))}" title="${esc(T("长", "Length"))}"><input class="te-in te-num" id="te-st-w" value="${esc(fmtNum(st.width))}" title="${esc(T("宽", "Width"))}"><input class="te-in te-num" id="te-st-h" value="${esc(fmtNum(st.height))}" title="${esc(T("高", "Height"))}">
        <button type="button" class="btn btn-sm btn-ghost" data-act="stretch">${esc(T("拉伸", "Stretch"))}</button></div>
        <span class="te-hint">${esc(T("直接改上面的长宽高不会移动门窗；这里会把门窗、截面、车顶设备等按比例挪到新尺寸上（门、灯、座椅本身大小不变）。", "Changing length/width/height above moves nothing; this moves windows, doors, sections and roof equipment to the new size (doors, lamps and seats keep their own size)."))}</span></div>`;
    }
    if (id === "arrange") {
      const n = state.arrangeN !== null ? state.arrangeN : ((s.doors || {}).centers || []).length;
      const row = (s.windows || [])[0] || {};
      return `<div class="te-field te-wide"><span class="te-lab">${esc(T("自动排布：每侧门数、窗宽、窗间距", "Arrange: doors per side, window width, pillar"))}</span>
        <div class="te-row"><input class="te-in te-num" id="te-ar-n" value="${n}" title="${esc(T("每侧门数", "Doors per side"))}"><input class="te-in te-num" id="te-ar-w" value="${esc(fmtNum(row.width || 1.2))}" title="${esc(T("窗宽", "Window width"))}"><input class="te-in te-num" id="te-ar-p" value="0.5" title="${esc(T("窗间距", "Pillar"))}">
        <button type="button" class="btn btn-sm btn-ghost" data-act="arrange">${esc(T("排布", "Arrange"))}</button></div>
        <span class="te-hint">${esc(T("把门均匀排开（给司机室留空），再在门与门之间排满第一排窗。其它窗排不动。", "Spaces the doors evenly (leaving room for cabs), then fills the bays between them with the first window row. Other rows stay."))}</span></div>`;
    }
    return "";
  }

  function renderForm() {
    const host = root && root.querySelector(".te-form");
    if (!host) return;
    const s = cur();
    if (!s) { host.innerHTML = ""; return; }
    const scroll = host.closest(".te-left") ? window.scrollY : 0;
    host.innerHTML = schema(s).map((g, gi) => `<details class="card te-group" data-g="${g.id}" style="--i:${Math.min(gi, 6)}"${state.open.has(g.id) ? " open" : ""}>
      <summary>${icon("i-chevron", "te-chev")}<span>${esc(TT(g.l))}</span><span class="te-count"></span></summary>
      <div class="te-gbody">${g.f.filter(Boolean).map((f) => fieldHTML(f, s)).join("")}</div></details>`).join("");
    host.querySelectorAll("details.te-group").forEach((d) => d.addEventListener("toggle", () => { if (d.open) state.open.add(d.dataset.g); else state.open.delete(d.dataset.g); }));
    window.scrollTo(window.scrollX, scroll);
    renderProblems();
  }

  // ------------------------------------------------------------------ tutorial
  function tutorialHTML() {
    const zh = lang() === "zh";
    const sec = (n, title, body, wide) => `<div class="te-tut-sec${wide ? " te-wide" : ""}"><h3><span class="te-num">${n}</span>${title}</h3>${body}</div>`;
    const scans = state.addonScansLocal;
    const tree = `<b>steamapps\\workshop\\content\\1134710\\2388066983\\</b>     ${zh ? "← 模组文件夹，名字就是创意工坊物品编号" : "← the mod folder; its name is the Workshop item id"}
  mod.txt                       ${zh ? "← [TrainUnit] id=mp40_bl / bilevel1 / bicab1" : "← [TrainUnit] id=mp40_bl / bilevel1 / bicab1"}
  mp40bl\\…                      ${zh ? "← 模组自己的贴图，不用动" : "← the mod's own textures, untouched"}
  <b>nimby3d\\</b>                      ${zh ? "← 新建这个文件夹" : "← add this folder"}
    <b>manifest.json</b>               ${zh ? "← 清单：哪个车辆用哪些模型文件" : "← which unit uses which model files"}
    mp40_bl_lod0.gov  …_lod1.gov  …_lod2.gov
    bilevel1_lod0.gov …_lod1.gov  …_lod2.gov
    bicab1_lod0.gov   …_lod1.gov  …_lod2.gov
    *.rig.json  *.train.json    ${zh ? "← 可选：部件说明、编辑器规格" : "← optional: part bindings, the editor's spec"}`;
    const manifest = `{
  "schema": 2,
  "native_format": "GOV2",
  "source_workshop_id": "2388066983",
  "models": [
    { "unit_id": "bilevel1", "length_m": 25.91, "width_m": 3.0,
      "variants": [
        { "lod": 0, "native_mesh": "bilevel1_lod0.gov", "native_sha256": "352cec69…" },
        { "lod": 1, "native_mesh": "bilevel1_lod1.gov", "native_sha256": "3810610e…" },
        { "lod": 2, "native_mesh": "bilevel1_lod2.gov", "native_sha256": "b1bb1a49…" } ] } ] }`;
    const s1 = zh
      ? `<p>附加组件读每个模组的 <code>mod.txt</code> 找车辆；如果模组文件夹里还有 <code>nimby3d\\manifest.json</code>，清单里列出的车辆就用自带的三维模型画，其余车辆仍是通用车厢。</p><div class="te-tree">${tree}</div>`
      : `<p>The add-on reads each mod's <code>mod.txt</code> for its vehicles; when the mod folder also has <code>nimby3d\\manifest.json</code>, the units listed there are drawn with their own 3D models, the rest stay generic cars.</p><div class="te-tree">${tree}</div>`;
    const s2 = zh
      ? `<p>清单里每个模型的 <code>"unit_id"</code> 必须和 mod.txt 中 <code>[TrainUnit]</code> 的 <code>id=</code> <b>一字不差</b>（大小写也算）。<code>length_m</code>、<code>width_m</code> 照抄 mod.txt 的 <code>length=</code>、<code>width=</code>，模型也按这个长宽做（长度含车钩）。</p>
         <p>编辑器导出时会列出模组的全部车辆让你选，并在长度对不上时提醒你、帮你拉伸。</p>`
      : `<p>Each model's <code>"unit_id"</code> must be <b>exactly</b> the <code>id=</code> of a <code>[TrainUnit]</code> in mod.txt (case too). <code>length_m</code> and <code>width_m</code> copy mod.txt's <code>length=</code> and <code>width=</code>, and the model is built to them (the length includes the couplers).</p>
         <p>When exporting, the editor lists the mod's units for you to pick from, and warns (and offers to stretch) when the lengths differ.</p>`;
    const s3 = zh
      ? `<p><code>source_workshop_id</code> 是这个模组的创意工坊物品编号，也就是 <code>workshop\\content\\1134710\\</code> 下面那个文件夹的名字。附加组件只接受和自己所在文件夹同名的清单——这样把别人的清单复制到另一个模组里不会套错车。游戏自带列车（<code>resources\\trains\\nimby3d</code>）写 <code>"builtin"</code>。</p>
         <p>每个文件还要写 <code>native_sha256</code>：文件的 SHA-256。改了文件哪怕一个字节，附加组件就不用它（日志会写“its hash differs”）。所以<b>不要手改 .gov 文件</b>，改规格后重新导出，编辑器会重算。文件名只能是同一文件夹里的普通文件名。</p>
         <div class="te-tree">${esc(manifest)}</div>`
      : `<p><code>source_workshop_id</code> is the mod's Workshop item id: the name of its folder under <code>workshop\\content\\1134710\\</code>. The add-on only accepts a manifest naming the folder it is in, so a manifest copied into another mod never dresses the wrong trains. The game's own trains (<code>resources\\trains\\nimby3d</code>) use <code>"builtin"</code>.</p>
         <p>Each file also carries <code>native_sha256</code>, its SHA-256: change one byte and the add-on refuses it (the log says "its hash differs"). So <b>never edit a .gov by hand</b>: change the spec and export again, and the editor recomputes everything. File names must be plain names in the same folder.</p>
         <div class="te-tree">${esc(manifest)}</div>`;
    const s4 = zh
      ? `<div class="te-callout te-warnbox">${icon("i-alert")}<span>直接往订阅的创意工坊物品文件夹里加文件<b>不牢靠</b>：模组作者一更新，Steam 重新下载时可能把你加的 nimby3d 文件夹删掉或冲掉；取消订阅会删掉整个文件夹。</span></div>
         <ul><li><b>最好的办法</b>：做成你自己的模组并发布到创意工坊（在原作者允许的前提下，把 nimby3d 文件夹一起上传），这样它就有自己的编号和文件夹。</li>
         <li>或者放进你自己的本地模组：<code>%USERPROFILE%\\Saved Games\\Weird and Wry\\NIMBY Rails\\mods\\</code> 里的一个文件夹（和存档在一起；<code>%APPDATA%</code> 里那个同名文件夹只放设置）。${scans ? "附加组件会读本地模组，source_workshop_id 写本地模组文件夹的名字。" : "<b>注意：当前版本的附加组件只从创意工坊物品和游戏自带列车读模型，还不读本地模组</b>；编辑器照样能导出、检查，等附加组件支持后就能用（source_workshop_id 写文件夹名）。"}</li>
         <li>只是自己试一试，写进创意工坊文件夹也可以：编辑器会先把要覆盖的文件备份到管理器的状态文件夹，Steam 更新后重新导出一次即可。</li></ul>`
      : `<div class="te-callout te-warnbox">${icon("i-alert")}<span>Adding files to a subscribed Workshop item's folder is <b>fragile</b>: when the author updates the mod, Steam may delete or overwrite your nimby3d folder while re-downloading it, and unsubscribing deletes the whole folder.</span></div>
         <ul><li><b>Best</b>: make it a mod of your own and publish it on the Workshop (with the original author's permission, upload the nimby3d folder with it), so it has its own id and folder.</li>
         <li>Or put it in a local mod of yours: a folder in <code>%USERPROFILE%\\Saved Games\\Weird and Wry\\NIMBY Rails\\mods\\</code> (beside the saves; the folder of that name in <code>%APPDATA%</code> only holds settings). ${scans ? "The add-on reads local mods; source_workshop_id is the local mod's folder name." : "<b>Note: the current add-on reads models only from Workshop items and the game's own trains, not yet from local mods</b>; the editor still exports and checks them, ready for when it does (source_workshop_id is the folder's name)."}</li>
         <li>Just trying it yourself, writing into the Workshop folder is fine: the editor first backs up any file it replaces into the manager's state folder; export again after Steam updates the item.</li></ul>`;
    const s5 = zh
      ? `<p>LOD 是细节层级：<b>LOD0</b> 近处看（完整车内），<b>LOD1</b> 中距离（简化座椅和司机台），<b>LOD2</b> 远处（没有车内、玻璃不透明）。附加组件按距离选；三级都要有（至少从 LOD0 起连续）。</p>
         <ul><li>每节车 LOD0 最好在 15,000 三角形以内，LOD1 约一半，LOD2 约十分之一到五分之一；同屏几百节车时 LOD2 最重要。</li>
         <li>附加组件的上限：每个文件最多 100 万顶点、300 万索引、4096 个部件、256 种材质、64 MB。</li>
         <li>车门、门的绑定和真正的门洞在三级里都保留，远处也能看到开门。</li></ul>`
      : `<p>LODs are levels of detail: <b>LOD0</b> for near (the full interior), <b>LOD1</b> for middle distance (simpler seats and desks), <b>LOD2</b> for far (no interior, opaque glass). The add-on picks by distance; ship all three (at least a run starting from LOD0).</p>
         <ul><li>Keep LOD0 under about 15,000 triangles per car, LOD1 about half, LOD2 a tenth to a fifth: with hundreds of cars on screen LOD2 matters most.</li>
         <li>The add-on's limits per file: 1,000,000 vertices, 3,000,000 indices, 4096 parts, 256 materials, 64 MB.</li>
         <li>Doors, their bindings and real door holes are kept at every level, so doors open even far away.</li></ul>`;
    const s6 = zh
      ? `<ol><li>在游戏里按 <b>F10</b> 打开 Nimby3D 面板 → “铁路”页 → 确认 <b>“车辆自带模型”</b> 是开着的。</li>
         <li>附加组件在游戏启动后第一次画列车时读模组。看日志（游戏文件夹里的 <code>nimby3d_probe.log</code>，或管理器底部活动面板的“附加组件”页）中以 <code>vehicle models:</code> 开头的行：<br><code>vehicle models: 2388066983/bilevel1: 3 levels, 12518 / 7038 / 1888 triangles</code> 表示用上了；<br><code>…: not used (…)</code> 写着原因，和编辑器“检查模组”给出的一样。</li>
         <li>本地模组另有一行 <code>trains: N local mods read (M with models of their own)</code>：M 应包括你的模组。</li>
         <li>周期性的 <code>trains:</code> 日志行里有 <code>vehicle models: N models for M units</code>。</li>
         <li>改了模型要<b>重启游戏</b>，附加组件只在启动时读一次。</li>
         <li>别的模组的车辆想借用你的模型：在 <code>nimby3d.ini</code> 旁边的 <code>nimby3d_vehicles.txt</code> 里写一行 <code>&lt;模组&gt;/&lt;车辆&gt; = &lt;模组&gt;/&lt;车辆&gt;</code>。</li></ol>`
      : `<ol><li>In game press <b>F10</b> for the Nimby3D panel → Railway page → make sure <b>Vehicles' own models</b> is on.</li>
         <li>The add-on reads the mods when it first draws trains after the game starts. In its log (<code>nimby3d_probe.log</code> in the game folder, or the Add-on tab of the manager's activity panel) look for lines starting <code>vehicle models:</code><br><code>vehicle models: 2388066983/bilevel1: 3 levels, 12518 / 7038 / 1888 triangles</code> means it is used;<br><code>…: not used (…)</code> gives the reason, the same as the editor's Check mod.</li>
         <li>For local mods there is also <code>trains: N local mods read (M with models of their own)</code>: M should count your mod.</li>
         <li>The periodic <code>trains:</code> log line includes <code>vehicle models: N models for M units</code>.</li>
         <li><b>Restart the game</b> after changing models: the add-on reads them once.</li>
         <li>To let another mod's unit use your model, add a line <code>&lt;mod&gt;/&lt;unit&gt; = &lt;mod&gt;/&lt;unit&gt;</code> to <code>nimby3d_vehicles.txt</code> beside <code>nimby3d.ini</code>.</li></ol>`;
    const s7 = zh
      ? `<ol><li>在上面“打开示例”里选 <b>GO Transit</b>：三页分别是 MP40 机车、BiLevel 客车和控制车。它们生成的文件与已部署的 GO 参考模型包逐字节相同。</li>
         <li>看预览：切 LOD、拖“车门”滑块、开“剖视”看双层车内和楼梯。</li>
         <li>改点东西试试，比如“涂装与材质”里的主涂装色，或“车门”里的滑动距离。</li>
         <li>在下面“导出到模组”里选模组 <b>2388066983</b>（或你自己的模组），每个规格对上一个车辆 id，导出。</li>
         <li>导出后编辑器会像附加组件那样检查模组，给出它会写进日志的行。然后重启游戏看效果。</li></ol>
         <p style="margin-top:8px"><button type="button" class="btn btn-sm btn-ghost" data-act="load-go">${icon("i-play")}打开 GO 示例</button></p>`
      : `<ol><li>Under Open an example above choose <b>GO Transit</b>: three tabs, the MP40 locomotive, the BiLevel coach and the cab car. The files they make are byte for byte the deployed GO reference pack's.</li>
         <li>Look at the preview: switch LODs, drag the Doors slider, turn on Section to see the two decks and the stairs.</li>
         <li>Change something, e.g. the primary livery colour under Livery and materials, or the slide travel under Passenger doors.</li>
         <li>Under Export to a mod below, pick the mod <b>2388066983</b> (or a mod of your own), give each spec a unit id, export.</li>
         <li>After exporting the editor checks the mod as the add-on would, with the lines it will write to its log. Then restart the game and look.</li></ol>
         <p style="margin-top:8px"><button type="button" class="btn btn-sm btn-ghost" data-act="load-go">${icon("i-play")}Open the GO example</button></p>`;
    return `<details class="card te-tut" id="te-tut" style="--i:1"${state.tutOpen ? " open" : ""}>
      <summary><div class="card-icon">${icon("i-book")}</div><h2>${esc(T("怎样把模型放进模组", "How to put models into a mod"))}</h2>${icon("i-chevron", "te-chev")}</summary>
      <div class="te-tut-body">
        ${sec(1, esc(T("文件放在哪里", "What goes where")), s1, true)}
        ${sec(2, esc(T("车辆 id 必须对上 mod.txt", "Unit ids must match mod.txt")), s2)}
        ${sec(3, esc(T("source_workshop_id 与文件哈希", "source_workshop_id and file hashes")), s3)}
        ${sec(4, esc(T("放进哪个模组", "Which mod to put it in")), s4)}
        ${sec(5, esc(T("三级 LOD", "The three LODs")), s5)}
        ${sec(6, esc(T("在游戏里测试", "Testing in game")), s6)}
        ${sec(7, esc(T("示例：GO Transit 列车", "Walk-through: the GO Transit train")), s7)}
        ${sec(8, esc(T("在 Blender 里自己建模", "Model it in Blender")), blenderHTML(), true)}
      </div></details>`;
  }

  function blenderHTML() {
    const rows = [
      ["door_left_*  /  door_right_*", "左侧（−Z）/ 右侧（+Z）的门扇；滑动方向：自定义属性 slide_axis = (1, 0, 0)，或名字结尾 _fwd / _back；否则离开旁边那扇门。滑动距离 travel_m（默认门扇长度），开关时间 open_seconds / close_seconds（1.6 / 0.7）",
        "a door leaf on the left (−Z) / right (+Z) side; slides along custom property slide_axis = (1, 0, 0), or the name ending _fwd / _back, else away from the leaf beside it; travel_m (default: the leaf's length), open_seconds / close_seconds (1.6 / 0.7)"],
      ["bogie_*", "转向架：原点放在转心（绕竖轴转）", "a bogie: its origin at the pivot (it turns about the vertical)"],
      ["wheelset_*  /  wheels_*  /  axle_*", "轮对：原点放在车轴中心；半径 radius_m（默认取高度的一半）", "a wheelset: its origin at the axle's centre; radius_m (default: half its height)"],
      ["interior_*", "车内（座椅、地板、隔墙）：LOD2 自动去掉", "the interior (seats, floors, partitions): left out at LOD2"],
      ["detail_*", "小零件：自动生成 LOD1 / LOD2 时去掉", "small details: left out of the LOD1 / LOD2 made from LOD0"],
      ["coupler_*", "车钩", "a coupler"],
      [T("其它名字", "any other name"), "车体的固定部分", "a fixed part of the body"],
    ];
    const table = `<table class="te-ntable"><tbody>${rows.map((r) => `<tr><td><code>${esc(r[0])}</code></td><td>${esc(T(r[1], r[2]))}</td></tr>`).join("")}</tbody></table>`;
    const checks = T(
      ["单位是米（场景属性 → 单位：公制，单位缩放 1.0）", "列车朝 +X（前端），车顶朝 +Z，右侧朝 −Y", "原点 (0, 0, 0) 在车辆中间，Z = 0 是轨面，车轮站在 Z = 0 上",
        "长、宽和 mod.txt 的 length、width 一样（长度从车钩到车钩）", "会动的部件是单独的物体，按上表命名；转向架、轮对的原点在转轴上",
        "玻璃：Alpha 小于 1，混合模式 Alpha Blend（或材质名里有 glass）", "三角形在预算内（LOD0 约 15,000）；贴图不用，颜色用基础色",
        "导出 glTF 2.0：格式 glTF 二进制（.glb），包含 → 自定义属性 ✓，变换 → +Y 向上 ✓，网格 → 应用修改器 ✓、法线 ✓",
        "在编辑器里“导入 GLB”，看提醒、拖“车门”滑块试门，再导出到模组"],
      ["Units are metres (Scene Properties → Units: Metric, Unit Scale 1.0)", "The train points along +X (its front), its roof along +Z, its right side towards −Y",
        "The origin (0, 0, 0) is the middle of the vehicle, Z = 0 the rail head: the wheels stand on Z = 0",
        "Length and width as mod.txt's length and width (the length from coupler to coupler)", "Parts that move are objects of their own, named as in the table; bogies' and wheelsets' origins on their axes",
        "Glass: Alpha below 1 with Blend Mode Alpha Blend (or glass in the material's name)", "Triangles within budget (LOD0 about 15,000); no textures: the base colour is used",
        "Export glTF 2.0: Format glTF Binary (.glb), Include → Custom Properties ✓, Transform → +Y Up ✓, Mesh → Apply Modifiers ✓, Normals ✓",
        "In the editor: Import GLB, read the warnings, drag Doors to try the doors, then export to the mod"]);
    return T(
      `<p>形状不在模板里，就在 Blender（或别的建模软件）里自己做，导出 GLB，用上面的<b>导入 GLB</b>。编辑器把它转成 GOV2：节点的旋转和缩放烘焙进顶点，部件只保留原点（门从这里滑，轮对和转向架绕这里转）。</p>
       <p><b>坐标</b>：附加组件用米，+X 车头、+Y 向上、+Z 右侧，原点在车辆中间的轨面上。Blender 是 Z 向上：列车朝 +X 放，车顶朝 +Z，右侧就朝 −Y；导出时选 <b>+Y Up</b>，导出器会换成 glTF 的 Y 向上。模型朝反了就在编辑器里勾“掉头”，用厘米做的填缩放 0.01，原点不对点“居中并放到轨面上”。</p>
       <p><b>部件名</b>（Blender 的 .001 后缀没关系；也可以用自定义属性 role 指定）：</p>${table}
       <p><b>三级细节</b>：最好自己导出 LOD1、LOD2 各一个 GLB（减面修改器 Decimate、删掉车内），在“导入的模型”里分别选。不选就由 LOD0 自动生成：去掉小零件和 interior_*、合并相近顶点，效果一般。</p>
       <p><b>检查清单</b></p><ul class="te-checklist">${checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`,
      `<p>When no template fits, model it in Blender (or another program), export a GLB and use <b>Import GLB</b> above. The editor turns it into GOV2: each node's rotation and scale are baked into its vertices, and a part keeps only its origin (doors slide from it, wheelsets and bogies turn about it).</p>
       <p><b>Axes</b>: the add-on uses metres, +X the front, +Y up, +Z right, the origin at the middle of the vehicle on the rail head. Blender is Z-up: point the train along +X with its roof along +Z, so its right side faces −Y; export with <b>+Y Up</b> and the exporter turns it into glTF's Y-up. If it comes out backwards tick Turn around in the editor; a model made in centimetres takes scale 0.01; a misplaced origin is fixed by Centre it and put it on the rails.</p>
       <p><b>Part names</b> (Blender's .001 suffixes do no harm; a custom property role works too):</p>${table}
       <p><b>Levels of detail</b>: best export a GLB of your own for LOD1 and LOD2 (a Decimate modifier, the interior deleted) and choose them under Imported model. Without, they are made from LOD0: small parts and interior_* left out, close vertices merged; it works, but plainly.</p>
       <p><b>Checklist</b></p><ul class="te-checklist">${checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`);
  }

  // ------------------------------------------------------------------ export panel
  function exportHTML() {
    const mods = (state.mods && state.mods.mods) || [];
    const groupsOf = [["local", T("本地模组", "Local mods")], ["other", T("其它文件夹", "Other folders")], ["workshop", T("创意工坊", "Workshop")], ["game", T("游戏自带", "The game's own")]];
    const opts = groupsOf.map(([src, label]) => {
      const list = mods.filter((m) => m.source === src);
      if (!list.length) return "";
      return `<optgroup label="${esc(label)}">${list.map((m) => `<option value="${esc(m.folder)}"${state.modSel === m.folder ? " selected" : ""}>${esc(m.name)}${m.source === "workshop" ? " · " + esc(m.id) : ""} (${m.units.length})</option>`).join("")}</optgroup>`;
    }).join("");
    const info = state.modInfo;
    let infoHTML = `<div class="te-modinfo"><span class="te-hint">${esc(T("先选一个模组，或选择文件夹。", "Pick a mod first, or choose a folder."))}</span></div>`;
    if (info) {
      const badge = (tone, text) => `<span class="badge" data-tone="${tone}"><span class="dot"></span>${esc(text)}</span>`;
      const srcLabel = { local: T("本地模组", "Local mod"), workshop: T("创意工坊物品", "Workshop item"), game: T("游戏自带", "The game's own"), other: T("其它文件夹", "Other folder"), game_other: T("游戏文件夹", "Game folder") }[info.source] || info.source;
      infoHTML = `<div class="te-modinfo">
        <div style="font-weight:650">${esc(info.name)}${info.author ? ` <span class="te-hint">· ${esc(info.author)}</span>` : ""}</div>
        <div class="te-path">${esc(info.folder)}</div>
        <div class="te-badges">${badge(info.source === "workshop" ? "info" : "accent", srcLabel)}
          ${info.scanned_by_addon ? badge("ok", T("附加组件会读", "The add-on reads it")) : badge("warn", T("附加组件目前不读这里", "The add-on does not read this yet"))}
          ${info.protected ? badge("warn", T("Steam/游戏管理的文件夹", "Managed by Steam / the game")) : ""}
          ${info.nimby3d ? badge("accent", T(`已有 ${info.models.length} 个模型`, `${info.models.length} model${info.models.length === 1 ? "" : "s"} already`)) : ""}</div>
        <div class="te-hint">${esc(T("车辆：", "Units: "))}${info.units.map((u) => esc(u.id) + (u.has_model ? " ✓" : "")).join(", ") || esc(T("（mod.txt 里没有 [TrainUnit]）", "(no [TrainUnit] in mod.txt)"))}</div>
        <div class="te-row"><button type="button" class="btn btn-sm btn-ghost" data-act="check-mod">${icon("i-search")}${esc(T("检查模组", "Check mod"))}</button>
          ${info.nimby3d ? `<button type="button" class="btn btn-sm btn-ghost" data-act="mod-specs">${icon("i-file")}${esc(T("载入模组里的规格", "Load specs from the mod"))}</button>` : ""}</div>
      </div>`;
    }
    const mapRows = state.specs.map((s, i) => {
      const inc = state.include[i] !== false;
      const units = info ? info.units : [];
      const u = units.find((x) => x.id === s.unit_id);
      const sel = `<select class="te-sel" data-act="map" data-i="${i}">${units.map((x) => `<option value="${esc(x.id)}"${x.id === s.unit_id ? " selected" : ""}>${esc(x.id)}${x.name && x.name !== x.id ? " — " + esc(x.name) : ""}</option>`).join("")}
        ${u || !info ? "" : `<option value="${esc(s.unit_id)}" selected>${esc(s.unit_id)} ${esc(T("（不在 mod.txt 里）", "(not in mod.txt)"))}</option>`}</select>`;
      let note = "";
      if (info && !u) note = `<div class="te-mapnote">${icon("i-alert")}${esc(T("这个 id 不在模组的 mod.txt 里：没有车辆会用它。从列表里选一个。", "This id is not in the mod's mod.txt: no vehicle would use it. Pick one from the list."))}</div>`;
      else if (u && (Math.abs(u.length - s.length) > 0.05 || (u.width && Math.abs(u.width - s.width) > 0.05))) {
        note = `<div class="te-mapnote">${icon("i-alert")}${esc(T(`mod.txt 里 ${u.id} 是 ${u.length} × ${u.width} 米，规格是 ${s.length} × ${s.width} 米`, `mod.txt has ${u.id} at ${u.length} × ${u.width} m, the spec is ${s.length} × ${s.width} m`))}
          <button type="button" class="btn btn-sm btn-ghost" data-act="fit-unit" data-i="${i}">${esc(T("拉伸到这个尺寸", "Stretch to fit"))}</button></div>`;
      }
      return `<div class="te-maprow"><input type="checkbox" data-act="include" data-i="${i}"${inc ? " checked" : ""} aria-label="${esc(T("导出这个", "Export this one"))}">
        <div class="te-spec">${esc(s.label || s.unit_id)}<small>${esc(s.unit_id)} · ${esc(s.length)} m</small></div><span class="te-arrow">→</span>${info ? sel : `<span class="te-hint">—</span>`}${note}</div>`;
    }).join("");
    const expected = info ? info.expected_source : "";
    return `<section class="card te-export" style="--i:3" id="te-export">
      <h2>${esc(T("导出到模组", "Export to a mod"))}</h2>
      <div class="te-export-grid">
        <div style="display:flex;flex-direction:column;gap:10px;min-width:0">
          <label class="te-field"><span class="te-lab">${esc(T("目标模组", "Target mod"))}</span>
            <div class="te-row"><select class="te-sel" id="te-mod"><option value="">${esc(state.mods ? T("选择一个模组……", "Choose a mod…") : T("正在查找模组……", "Looking for mods…"))}</option>${opts}</select>
            <button type="button" class="btn btn-sm btn-ghost" data-act="pick-folder">${icon("i-folder")}${esc(T("文件夹……", "Folder…"))}</button>
            <button type="button" class="te-icon-btn" data-act="reload-mods" title="${esc(T("重新查找", "Look again"))}">${icon("i-refresh")}</button></div></label>
          ${infoHTML}
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;min-width:0">
          <span class="te-lab">${esc(T("每个规格对应模组里的哪个车辆", "Which unit of the mod each spec is for"))}</span>
          <div class="te-map">${mapRows || `<span class="te-hint">${esc(T("没有规格", "No specs"))}</span>`}</div>
          <label class="te-field"><span class="te-lab">source_workshop_id</span><input class="te-in te-num" id="te-source" value="${esc(state.source_id || expected)}" placeholder="${esc(expected)}">
            <span class="te-hint">${esc(T(`这个文件夹应为 “${expected}”（${info && info.source === "game" ? "游戏自带列车" : "模组文件夹名"}）`, `This folder needs "${expected}" (${info && info.source === "game" ? "the game's own trains" : "the mod folder's name"})`))}</span></label>
          <label class="te-check"><input type="checkbox" id="te-glb"${state.glb ? " checked" : ""}>${esc(T("同时写 GLB（给 Blender 等软件看；附加组件不用）", "Also write GLB (for Blender and other viewers; the add-on does not use it)"))}</label>
          <label class="te-check"><input type="checkbox" id="te-incspec"${state.includeSpec ? " checked" : ""}>${esc(T("把规格文件一起放进去（别人可以接着改）", "Include the spec files (so others can keep editing)"))}</label>
          ${state.specs.some(isImport) ? `<label class="te-check"><input type="checkbox" id="te-incsrc"${state.includeSources ? " checked" : ""}>${esc(T("导入的模型：把源 GLB 文件也放进去（模组会变大）", "Imported models: include the source GLB files too (the mod gets bigger)"))}</label>` : ""}
        </div>
      </div>
      <div class="te-export-actions">
        <button type="button" class="btn btn-primary" data-act="export"${info ? "" : " disabled"}>${icon("i-download")}<span class="label">${esc(T("导出", "Export"))}</span></button>
        <span class="te-hint">${esc(T("只写进模组的 nimby3d 文件夹；被替换的文件先备份到管理器的状态文件夹。", "Writes only inside the mod's nimby3d folder; files it replaces are backed up into the manager's state folder first."))}</span>
      </div>
      <div id="te-result">${resultHTML()}</div>
    </section>`;
  }

  function checkHTML(chk) {
    if (!chk) return "";
    const good = chk.valid;
    const lines = (chk.log_lines || []).map((l) => "vehicle models: " + l).join("\n");
    const probs = (chk.problems || []).map((p) => `<div class="te-prob te-err">${icon("i-x-circle")}<span>${esc(T(p.zh, p.en))}</span></div>`).join("");
    const warns = (chk.warnings || []).map((p) => `<div class="te-prob te-warn">${icon("i-alert")}<span>${esc(T(p.zh, p.en))}</span></div>`).join("");
    const head = !good ? T("附加组件不会全部用上", "The add-on will not use all of these")
      : chk.scanned_by_addon ? T("附加组件会用这些模型", "The add-on will use these models")
        : T("清单和模型都合格，但附加组件目前不读这个文件夹", "Manifest and models are valid, but the add-on does not read this folder yet");
    return `<div class="te-res ${good ? "te-good" : "te-badres"}"><h3>${icon(good ? (chk.scanned_by_addon ? "i-check-circle" : "i-info") : "i-x-circle")}${esc(head)}</h3>
      <span class="te-hint">${esc(T("附加组件读到这个模组时会在日志里写：", "When the add-on reads this mod it will log:"))}</span>
      <pre class="te-loglines">${esc(lines || T("（没有 nimby3d\\manifest.json，不写这一行）", "(no nimby3d\\manifest.json: no such line)"))}</pre>${probs}${warns}</div>`;
  }

  function resultHTML() {
    const r = state.result;
    if (!r) return "";
    if (r.kind === "check") return checkHTML(r.check);
    const files = (r.written || []).map((f) => `<li title="${esc(f.sha256)}">${esc(f.name)} <span>${kb(f.bytes)}</span></li>`).join("");
    const warns = (r.warnings || []).map((w) => `<div class="te-prob te-warn">${icon("i-alert")}<span>${esc(w)}</span></div>`).join("");
    return `<div class="te-res te-good"><h3>${icon("i-check-circle")}${esc(T(`已写入 ${r.written.length} 个文件`, `${r.written.length} files written`))}</h3>
      <div class="te-path" style="font:11.5px var(--mono);color:var(--text-2);overflow-wrap:anywhere">${esc(r.nimby3d)}</div>
      <ul class="te-files">${files}</ul>
      ${r.removed && r.removed.length ? `<span class="te-hint">${esc(T("删掉了不再使用的旧文件：", "Removed old files no longer used: "))}${esc(r.removed.join(", "))}</span>` : ""}
      ${r.backup ? `<span class="te-hint">${esc(T("原来的文件备份在：", "The files it replaced are backed up in: "))}<code>${esc(r.backup)}</code></span>` : ""}
      ${warns}</div>${checkHTML(r.check)}`;
  }

  function renderExport() {
    const el = root && root.querySelector("#te-export");
    if (!el) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = exportHTML();
    el.replaceWith(tmp.firstElementChild);
  }

  // ------------------------------------------------------------------ preview
  function setBusy(on) {
    state.busy = Math.max(0, state.busy + (on ? 1 : -1));
    const el = root && root.querySelector("#te-busy");
    if (el) el.innerHTML = state.busy ? `<span class="spin"></span>${esc(T("正在生成……", "Building…"))}` : "";
  }

  function schedule(delay) {
    clearTimeout(timer);
    timer = setTimeout(refresh, delay === undefined ? 380 : delay);
  }

  async function refresh() {
    const s = cur();
    if (!s) return;
    const my = ++seq;
    const spec = clone(s);
    const lod = state.lod;
    setBusy(true);
    try {
      const v = await api("validate", { spec });
      if (my !== seq) return;
      state.problems = { errors: v.errors || [], warnings: v.warnings || [] };
      state.buildError = null;
      if (v.valid) {
        const p = await api("preview", { spec, lod });
        if (my !== seq) return;
        state.stats = p.stats;
        state.report = p.report || null;
        state.problems.warnings = p.warnings || state.problems.warnings;
        if (p.report) {
          const rep = root && root.querySelector("#te-imp-report");
          if (rep) rep.outerHTML = importReportHTML();
        }
        drawSprite();
        state.limits = p.limits || [];
        if (viewer) viewer.setMesh(p.mesh);
        state.built = true;
      }
    } catch (e) {
      if (my !== seq) return;
      state.buildError = errMsg(e);
    } finally {
      setBusy(false);
    }
    renderStats();
    renderProblems();
  }

  // ------------------------------------------------------------------ changing the spec
  function markDirty() {
    state.dirty[state.cur] = true;
    const tab = root && root.querySelector(`.te-tab[data-i="${state.cur}"]`);
    if (tab && !tab.querySelector(".te-dot")) tab.insertAdjacentHTML("afterbegin", `<span class="te-dot"></span>`);
  }

  function setSpec(spec, i) {
    if (i === undefined) i = state.cur;
    state.specs[i] = spec;
    markDirty();
    renderForm();
    schedule(120);
  }

  function onInput(e) {
    const el = e.target;
    if (!el || !el.dataset) return;
    if (el.id === "te-door") {
      state.open01 = Number(el.value) / 100;
      if (viewer) { viewer.stopDoors(); viewer.setDoors(state.open01, state.side); }
      const pb = root.querySelector('[data-act="play"]');
      if (pb) pb.setAttribute("aria-pressed", "false");
      return;
    }
    if (el.id === "te-source") { state.source_id = el.value.trim(); return; }
    if (el.dataset.spriteTint !== undefined) { state.spriteOpts.tint[Number(el.dataset.spriteTint)] = el.value; drawSprite(); return; }
    const path = el.dataset.path;
    const t = el.dataset.t;
    if (path === undefined || !t) return;
    const s = cur();
    if (!s) return;
    if (t === "text") { setPath(s, path, el.value); if (path === "unit_id") { const tab = root.querySelector(`.te-tab[data-i="${state.cur}"]`); if (tab) tab.childNodes.forEach((n) => { if (n.nodeType === 3 && n.textContent.trim()) n.textContent = el.value || "?"; }); } }
    else if (t === "num") {
      const v = parseNum(el.value);
      if (v === null) { el.classList.add("te-bad"); return; }
      el.classList.remove("te-bad");
      setPath(s, path, v);
    } else if (t === "list") {
      const v = parseList(el.value);
      if (v === null) { el.classList.add("te-bad"); return; }
      el.classList.remove("te-bad");
      setPath(s, path, v);
    } else if (t === "color") {
      setPath(s, path, linOf(el.value));
    } else return;
    markDirty();
    schedule();
  }

  function onChange(e) {
    const el = e.target;
    if (!el) return;
    if (el.id === "te-example") { const v = el.value; el.value = ""; if (v) loadExample(v); return; }
    if (el.id === "te-new") { const v = el.value; el.value = ""; if (v) newSpec(v); return; }
    if (el.id === "te-side") { state.side = el.value; if (viewer) viewer.setDoors(state.open01, state.side); return; }
    if (el.id === "te-mod" || el.id === "te-tmod") { selectMod(el.value); return; }
    if (el.id === "te-tunit") { selectUnit(el.value); return; }
    if (el.id === "te-sprite-overlay") { state.spriteOpts.overlay = el.checked; drawSprite(); return; }
    if (el.id === "te-sprite-target") { state.spriteOpts.target = el.value; return; }
    if (el.dataset && el.dataset.spriteOn !== undefined) { state.spriteOpts.on[Number(el.dataset.spriteOn)] = el.checked; drawSprite(); return; }
    if (el.dataset && el.dataset.spriteTint !== undefined) return;
    if (el.id === "te-incsrc") { state.includeSources = el.checked; return; }
    if (el.id === "te-glb") { state.glb = el.checked; return; }
    if (el.id === "te-incspec") { state.includeSpec = el.checked; return; }
    const act = el.dataset && el.dataset.act;
    if (act === "include") { state.include[Number(el.dataset.i)] = el.checked; return; }
    if (act === "map") {
      const i = Number(el.dataset.i);
      state.specs[i].unit_id = el.value;
      state.include[i] = true;
      state.dirty[i] = true;
      render();
      if (i === state.cur) schedule(50);
      return;
    }
    if (act === "emi") {
      const s = cur();
      const k = el.dataset.k;
      if (el.checked) s.materials[k].emissive = s.materials[k].color ? clone(s.materials[k].color) : [0.5, 0.5, 0.5];
      else delete s.materials[k].emissive;
      setSpec(s);
      return;
    }
    const path = el.dataset && el.dataset.path;
    const t = el.dataset && el.dataset.t;
    if (path === undefined || !t) return;
    const s = cur();
    if (!s) return;
    if (t === "num" || t === "list" || t === "text" || t === "color") {
      if (path === "doors.centers" && (s.doors.centers || []).length && typeof s.doors.width !== "number") {
        s.doors = Object.assign(doorDefaults(s), s.doors);
      }
      if (el.dataset.rr) { renderForm(); schedule(60); }
      return;
    }
    if (t === "paint") { setPath(s, path, el.value); markDirty(); schedule(); return; }
    if (t === "selv") { const vals = JSON.parse(el.dataset.opts); setPath(s, path, vals[el.selectedIndex]); markDirty(); schedule(); return; }
    if (t === "chk") { setPath(s, path, el.checked); markDirty(); if (el.dataset.rr) renderForm(); schedule(); return; }
    if (t === "opt") {
      const f = findField(path);
      setPath(s, path, el.checked ? (f && f.def ? f.def() : {}) : null);
      setSpec(s);
      return;
    }
    if (t === "sel" || t === "style" || t === "cab" || t === "gang") {
      const f = findField(path);
      const v = f.opts[Number(el.value)][0];
      if (t === "style") { changeStyle(v); return; }
      if (t === "cab") {
        if (v !== "none" && !(s.cab && s.cab.windscreen)) s.cab = Object.assign(cabDefaults(s), s.cab || {});
        setPath(s, "cab.ends", v);
        setSpec(s);
        return;
      }
      if (t === "gang") {
        if (v !== "none" && !(s.gangway && typeof s.gangway.center_y === "number")) s.gangway = Object.assign(gangDefaults(s), s.gangway || {});
        setPath(s, "gangway.ends", v);
        setSpec(s);
        return;
      }
      setPath(s, path, v);
      if (path === "interior.layout" && v === "single" && typeof (s.interior || {}).floor_y !== "number") setPath(s, "interior.floor_y", floorOf(s));
      markDirty();
      if (f.rr) renderForm();
      schedule();
    }
  }

  function findField(path) {
    const s = cur();
    for (const g of schema(s)) for (const f of g.f) if (f && f.p === path) return f;
    return null;
  }

  async function changeStyle(style) {
    const s = cur();
    const ok = await ctx.confirm({ title: T("换车体样式？", "Change the body style?"), body: T("车体会换成这种样式的默认车体（车辆 id、名称和材质保留）。", "The body is replaced by this style's default (the unit id, name and materials are kept)."), ok: T("更换", "Change") });
    if (!ok) { renderForm(); return; }
    try {
      const kind = style === "hood" ? "locomotive" : (s.kind === "locomotive" ? "locomotive" : s.kind);
      const fresh = await api("new_spec", { kind, style });
      fresh.unit_id = s.unit_id; fresh.label = s.label; fresh.materials = s.materials;
      setSpec(fresh);
    } catch (e) { toast(errMsg(e), "danger"); renderForm(); }
  }

  async function onClick(e) {
    const btn = e.target.closest("[data-act]");
    if (!btn || !root.contains(btn)) {
      const prob = e.target.closest(".te-prob[data-path]");
      if (prob) focusPath(prob.dataset.path);
      return;
    }
    const act = btn.dataset.act;
    const s = cur();
    if (["include", "map", "emi"].includes(act)) return;
    switch (act) {
      case "tab": state.cur = Number(btn.dataset.i); state.stats = null; render(); schedule(10); break;
      case "close-tab": {
        e.stopPropagation();
        const i = Number(btn.dataset.i);
        if (state.dirty[i] && !(await ctx.confirm({ title: T("关闭这一页？", "Close this tab?"), body: T("这个规格有未保存的修改。", "This spec has unsaved changes."), ok: T("关闭", "Close"), danger: true }))) return;
        state.specs.splice(i, 1); state.dirty.splice(i, 1);
        defaultIncludes();
        state.cur = Math.max(0, Math.min(state.cur, state.specs.length - 1));
        render(); schedule(10);
        break;
      }
      case "dup-tab": if (s) { const c = clone(s); c.unit_id = s.unit_id + "_copy"; state.specs.push(c); state.dirty.push(true); state.cur = state.specs.length - 1; defaultIncludes(); render(); schedule(10); } break;
      case "lod": state.lod = Number(btn.dataset.lod); root.querySelectorAll('[data-act="lod"]').forEach((b) => { b.setAttribute(b.classList.contains("te-stat") ? "aria-current" : "aria-pressed", String(Number(b.dataset.lod) === state.lod)); }); schedule(0); break;
      case "wire": state.wire = !state.wire; btn.setAttribute("aria-pressed", String(state.wire)); if (viewer) { viewer.wire = state.wire; viewer.dirty = true; } break;
      case "cut": state.cut = !state.cut; btn.setAttribute("aria-pressed", String(state.cut)); if (viewer) { viewer.cut = state.cut; viewer.dirty = true; } break;
      case "view": if (viewer) viewer.view(btn.dataset.v); break;
      case "play": {
        if (!viewer) break;
        if (viewer.anim) { viewer.stopDoors(); btn.setAttribute("aria-pressed", "false"); state.open01 = viewer.open; }
        else { const d = (s && s.doors) || {}; viewer.side = state.side; viewer.playDoors([d.open_seconds || 1.6, d.close_seconds || 0.7]); btn.setAttribute("aria-pressed", "true"); }
        break;
      }
      case "row-add": {
        const p = btn.dataset.p;
        const f = findField(p);
        const rows = getPath(s, p) || [];
        if (!Array.isArray(getPath(s, p))) setPath(s, p, rows);
        rows.push(f && f.def ? f.def(rows) : {});
        setSpec(s);
        break;
      }
      case "row-del": { const rows = getPath(s, btn.dataset.p); rows.splice(Number(btn.dataset.i), 1); setSpec(s); break; }
      case "json-apply": applyJSON(btn.dataset.p, btn.closest(".te-field").querySelector("textarea").value); break;
      case "json-copy": try { await navigator.clipboard.writeText(JSON.stringify(s, null, 1)); toast(T("已复制", "Copied"), "ok"); } catch (err) { toast(errMsg(err), "warn"); } break;
      case "mat-add": {
        const inp = root.querySelector("#te-newmat");
        const k = (inp.value || "").trim();
        if (!/^[a-z][a-z0-9_]{0,40}$/.test(k)) { toast(T("材质名只能用小写字母、数字和下划线，以字母开头", "A material key is lower-case letters, digits and _, starting with a letter"), "warn"); break; }
        if (s.materials[k]) { toast(T("已有这个材质", "That material exists"), "warn"); break; }
        s.materials[k] = { name: k, color: clone((s.materials.primary || {}).color || [0.5, 0.5, 0.5]), alpha: 1, metallic: 0.12, roughness: 0.4 };
        setSpec(s);
        break;
      }
      case "mat-del": delete s.materials[btn.dataset.k]; setSpec(s); break;
      case "stretch": {
        const L = parseNum(root.querySelector("#te-st-l").value), W = parseNum(root.querySelector("#te-st-w").value), H = parseNum(root.querySelector("#te-st-h").value);
        if (L === null || W === null || H === null) { toast(T("长宽高须为数字", "Length, width and height must be numbers"), "warn"); break; }
        try { setSpec(await api("fit", { spec: clone(s), length: L, width: W, height: H })); toast(T("已按新尺寸拉伸", "Stretched to the new size"), "ok"); } catch (err) { toast(errMsg(err), "danger"); }
        break;
      }
      case "arrange": {
        const n = parseNum(root.querySelector("#te-ar-n").value), w = parseNum(root.querySelector("#te-ar-w").value), p = parseNum(root.querySelector("#te-ar-p").value);
        if (n === null || w === null || p === null) { toast(T("请填数字", "Numbers, please"), "warn"); break; }
        try { setSpec(await api("arrange", { spec: clone(s), doors_per_side: Math.round(n), window_width: w, pillar: p })); } catch (err) { toast(errMsg(err), "danger"); }
        break;
      }
      case "load-spec": await loadSpecFile(); break;
      case "save-spec": await saveSpecFile(); break;
      case "load-go": await loadExample("go_train"); break;
      case "pick-folder": await pickModFolder(); break;
      case "reload-mods": await loadMods(true); break;
      case "check-mod": await checkMod(); break;
      case "mod-specs": await loadModSpecs(); break;
      case "fit-unit": {
        const i = Number(btn.dataset.i);
        const u = state.modInfo.units.find((x) => x.id === state.specs[i].unit_id);
        if (!u) break;
        try {
          state.specs[i] = await api("fit", { spec: clone(state.specs[i]), length: u.length, width: u.width || null });
          state.dirty[i] = true;
          render(); schedule(20);
        } catch (err) { toast(errMsg(err), "danger"); }
        break;
      }
      case "export": await doExport(); break;
      case "guide-open": state.guide.on = !state.guide.on; if (state.guide.on) goStep(state.guide.step); else { render(); } break;
      case "guide-close": state.guide.on = false; render(); break;
      case "guide-next": goStep(state.guide.step + 1); break;
      case "guide-prev": goStep(state.guide.step - 1); break;
      case "guide-step": goStep(Number(btn.dataset.n)); break;
      case "guide-act": await guideAction(btn.dataset.k); break;
      case "use-unit": await useUnit(); break;
      case "import-glb": await importGlb(); break;
      case "pick-glb": await pickGlb(Number(btn.dataset.lod)); break;
      case "clear-glb": { const lods = (s.import.lods || []).concat([null, null, null]).slice(0, 3); lods[Number(btn.dataset.lod)] = null; s.import.lods = lods; setSpec(s); break; }
      case "place": placeOnRails(); break;
      default: break;
    }
  }

  function applyJSON(path, text) {
    let v;
    try { v = JSON.parse(text); } catch (err) { toast(T("不是有效的 JSON：", "Not valid JSON: ") + errMsg(err), "danger"); return; }
    const s = cur();
    if (!path) {
      if (!v || typeof v !== "object" || Array.isArray(v)) { toast(T("规格须为 JSON 对象", "A spec must be a JSON object"), "danger"); return; }
      setSpec(v);
    } else {
      setPath(s, path, v);
      setSpec(s);
    }
    toast(T("已应用", "Applied"), "ok");
  }

  function focusPath(path) {
    if (!root) return;
    let el = root.querySelector(`[data-path="${CSS.escape(path)}"]`);
    const parts = path.split(".");
    while (!el && parts.length > 1) { parts.pop(); el = root.querySelector(`[data-path="${CSS.escape(parts.join("."))}"]`); }
    if (!el) {
      // a group that is closed, or a path only the JSON shows: open the group that has it
      for (const g of schema(cur())) {
        if (g.f.some((f) => f && f.p && path.startsWith(String(f.p)))) { state.open.add(g.id); renderForm(); return focusPath(path); }
      }
      state.open.add("advanced");
      renderForm();
      const adv = root.querySelector('details[data-g="advanced"]');
      if (adv) adv.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const det = el.closest("details");
    if (det && !det.open) { det.open = true; state.open.add(det.dataset.g); }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const inp = el.matches("input,select,textarea") ? el : el.querySelector("input,select,textarea");
    if (inp) setTimeout(() => inp.focus(), 250);
  }

  // ------------------------------------------------------------------ loading and saving
  async function guardDirty() {
    if (!state.dirty.some(Boolean)) return true;
    return ctx.confirm({ title: T("放弃未保存的修改？", "Discard unsaved changes?"), body: T("打开的规格有未保存的修改，会被替换。", "The open specs have unsaved changes; they will be replaced."), ok: T("放弃并继续", "Discard and continue"), danger: true });
  }

  async function loadExample(name) {
    if (!(await guardDirty())) return;
    try {
      const ex = await api("load_example", { name });
      state.specs = ex.specs;
      state.dirty = ex.specs.map(() => false);
      state.cur = 0;
      state.exampleName = name;
      defaultIncludes();
      state.stats = null;
      state.result = null;
      if (ex.info && ex.info.mod && ex.info.mod.workshop_id && state.mods) {
        const m = state.mods.mods.find((x) => x.id === ex.info.mod.workshop_id);
        if (m) { state.modSel = m.folder; state.modInfo = m; defaultIncludes(); }
      }
      if (viewer) viewer.payload = null;
      render();
      schedule(10);
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function newSpec(v) {
    const [kind, style] = v.split(":");
    try {
      const spec = await api("new_spec", { kind, style: style || null });
      state.specs.push(spec);
      state.dirty.push(true);
      state.cur = state.specs.length - 1;
      defaultIncludes();
      state.stats = null;
      if (viewer) viewer.payload = null;
      render();
      schedule(10);
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  const SPEC_FILTERS = [["Train spec", "*.train.json"], ["JSON", "*.json"]];
  async function loadSpecFile() {
    const path = await ctx.pickFile({ title: T("打开列车规格", "Open a train spec"), filters: SPEC_FILTERS });
    if (!path) return;
    try {
      const r = await api("load_spec", { path });
      state.specs.push(r.spec);
      state.dirty.push(false);
      state.cur = state.specs.length - 1;
      defaultIncludes();
      if (viewer) viewer.payload = null;
      render();
      schedule(10);
      toast(T("已打开 ", "Opened ") + r.path, "ok");
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function saveSpecFile() {
    const s = cur();
    if (!s) return;
    const path = await ctx.pickFile({ title: T("保存列车规格", "Save the train spec"), filters: SPEC_FILTERS, save: true, name: (s.unit_id || "train") + ".train.json" });
    if (!path) return;
    try {
      const r = await api("save_spec", { spec: s, path });
      state.dirty[state.cur] = false;
      render();
      toast(T("已保存到 ", "Saved to ") + r.path, "ok");
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  // ------------------------------------------------------------------ mods and export
  async function loadMods(force) {
    if (state.mods && !force) return;
    try {
      state.mods = await api("list_mods", {});
      state.modsAt = Date.now();
      state.addonScansLocal = !!state.mods.addon_scans_local_mods;
      if (state.modSel) {
        const m = state.mods.mods.find((x) => x.folder === state.modSel);
        if (m) state.modInfo = m;
      } else if (state.exampleName === "go_train") {
        const m = state.mods.mods.find((x) => x.id === "2388066983");
        if (m) { state.modSel = m.folder; state.modInfo = m; defaultIncludes(); }
      }
    } catch (e) {
      state.mods = { mods: [] };
      toast(T("找不到模组：", "Could not list the mods: ") + errMsg(e), "warn");
    }
    pickDefaultUnit();
    renderTarget();
    renderExport();
    loadSprite();
  }

  // tick, by default, the specs whose unit id the mod has
  // (the first spec of each unit id only: two models for one unit cannot go into one manifest)
  function defaultIncludes() {
    const ids = new Set(((state.modInfo && state.modInfo.units) || []).map((u) => u.id));
    const seen = new Set();
    state.include = {};
    state.specs.forEach((s, i) => {
      state.include[i] = !seen.has(s.unit_id) && (!ids.size || ids.has(s.unit_id));
      seen.add(s.unit_id);
    });
  }

  async function selectMod(folder) {
    state.result = null;
    state.source_id = "";
    if (!folder) { state.modSel = null; state.modInfo = null; state.unitSel = null; renderTarget(); renderExport(); loadSprite(); return; }
    state.modSel = folder;
    state.modInfo = ((state.mods && state.mods.mods) || []).find((m) => m.folder === folder) || null;
    if (!state.modInfo) {
      try { state.modInfo = await api("mod_info", { folder }); } catch (e) { toast(errMsg(e), "danger"); }
    }
    defaultIncludes();
    pickDefaultUnit();
    renderTarget();
    renderExport();
    await loadSprite();
  }

  async function pickModFolder() {
    const folder = await ctx.pickFolder({ title: T("选择模组文件夹（里面有 mod.txt）", "Choose a mod folder (with mod.txt in it)") });
    if (!folder) return;
    try {
      state.modInfo = await api("mod_info", { folder });
      state.modSel = state.modInfo.folder;
      defaultIncludes();
      if (state.mods && !state.mods.mods.some((m) => m.folder === state.modInfo.folder)) state.mods.mods.push(state.modInfo);
      state.result = null;
      state.source_id = "";
      pickDefaultUnit();
      renderTarget();
      renderExport();
      await loadSprite();
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function checkMod() {
    if (!state.modInfo) return;
    try {
      const chk = await api("validate_mod", { folder: state.modInfo.folder });
      state.result = { kind: "check", check: chk };
      renderExport();
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function loadModSpecs() {
    try {
      const r = await api("read_mod_models", { folder: state.modInfo.folder });
      if (!r.specs.length) { toast(T("这个模组里没有编辑器规格（*.train.json）", "This mod has no editor specs (*.train.json)"), "info"); return; }
      for (const x of r.specs) { state.specs.push(x.spec); state.dirty.push(false); }
      state.cur = state.specs.length - r.specs.length;
      defaultIncludes();
      if (viewer) viewer.payload = null;
      render();
      schedule(10);
      toast(T(`载入了 ${r.specs.length} 个规格`, `Loaded ${r.specs.length} spec${r.specs.length > 1 ? "s" : ""}`), "ok");
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function doExport() {
    const info = state.modInfo;
    if (!info) return;
    const chosen = state.specs.filter((_, i) => state.include[i] !== false);
    if (!chosen.length) { toast(T("没有选中要导出的规格", "No spec is ticked for export"), "warn"); return; }
    const srcEl = root.querySelector("#te-source");
    const source = (srcEl && srcEl.value.trim()) || info.expected_source;
    const names = chosen.map((s) => s.unit_id).join(", ");
    let allowProtected = false;
    if (info.protected) {
      const ok = await ctx.confirm({
        title: info.source === "workshop" ? T("写进创意工坊物品的文件夹？", "Write into a Workshop item's folder?") : T("写进游戏自己的文件夹？", "Write into the game's own folder?"),
        body: T(`Steam 更新${info.source === "workshop" ? "这个模组" : "游戏"}时可能删掉或覆盖这些文件；取消订阅会删掉整个文件夹。被替换的文件会先备份。更稳妥的做法是放进你自己的模组。\n\n要写入：${names}`,
          `When Steam updates ${info.source === "workshop" ? "this mod" : "the game"} it may delete or overwrite these files; unsubscribing deletes the whole folder. Files replaced are backed up first. Your own mod is the safer place.\n\nTo write: ${names}`),
        ok: T("仍然写入", "Write anyway"), danger: true,
      });
      if (!ok) return;
      allowProtected = true;
    } else {
      const ok = await ctx.confirm({ title: T("导出模型？", "Export the models?"), body: T(`写入 ${info.folder}\\nimby3d：${names}`, `Into ${info.folder}\\nimby3d: ${names}`), ok: T("导出", "Export") });
      if (!ok) return;
    }
    const btn = root.querySelector('[data-act="export"]');
    if (btn) { btn.disabled = true; btn.querySelector(".label").textContent = T("正在导出……", "Exporting…"); }
    try {
      const r = await api("export", { spec_or_specs: chosen, mod_folder: info.folder, source_workshop_id: source, glb: state.glb, allow_protected: allowProtected, include_spec: state.includeSpec, include_sources: state.includeSources });
      state.result = Object.assign({ kind: "export" }, r);
      state.specs.forEach((s, i) => { if (state.include[i] !== false) state.dirty[i] = false; });
      try { await loadMods(true); } catch (e) { /* the list is only a convenience */ }
      render();
      const ck = r.check || {};
      toast(ck.loads ? T("导出完成，附加组件会用这些模型", "Exported: the add-on will use these models")
        : ck.valid ? T("导出完成；附加组件目前不读这个文件夹", "Exported; the add-on does not read this folder yet")
          : T("导出完成，但检查发现问题", "Exported, but the check found problems"), ck.loads ? "ok" : "warn");
      const res = root.querySelector("#te-result");
      if (res) res.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      toast(errMsg(e), "danger");
      if (btn) { btn.disabled = false; btn.querySelector(".label").textContent = T("导出", "Export"); }
    }
  }

  // ------------------------------------------------------------------ your mod and unit (the target card)
  function modOptionsHTML(sel) {
    const mods = (state.mods && state.mods.mods) || [];
    const groupsOf = [["local", T("本地模组", "Local mods")], ["other", T("其它文件夹", "Other folders")], ["workshop", T("创意工坊", "Workshop")], ["game", T("游戏自带", "The game's own")]];
    return groupsOf.map(([src, label]) => {
      const list = mods.filter((m) => m.source === src);
      if (!list.length) return "";
      return `<optgroup label="${esc(label)}">${list.map((m) => `<option value="${esc(m.folder)}"${sel === m.folder ? " selected" : ""}>${esc(m.name)}${m.source === "workshop" ? " · " + esc(m.id) : ""} (${m.units.length})</option>`).join("")}</optgroup>`;
    }).join("");
  }

  const selUnit = () => ((state.modInfo && state.modInfo.units) || []).find((u) => u.id === state.unitSel) || null;

  function targetHTML() {
    const info = state.modInfo;
    const units = info ? info.units : [];
    const u = selUnit();
    const s = cur();
    let facts = `<span class="te-hint">${esc(T("选一个模组和其中的车辆：编辑器读它的 mod.txt（id、长、宽和精灵图片）。", "Choose a mod and one of its units: the editor reads its mod.txt (id, length, width and sprite pictures)."))}</span>`;
    if (u) {
      const same = s && s.unit_id === u.id;
      const dimsOk = s && Math.abs(s.length - u.length) <= 0.05 && (!u.width || Math.abs(s.width - u.width) <= 0.05);
      facts = `<span class="te-fact"><code>id=${esc(u.id)}</code></span><span class="te-fact">${esc(T("长", "length"))} <b>${u.length}</b> m</span><span class="te-fact">${esc(T("宽", "width"))} <b>${u.width || "?"}</b> m</span>
        <span class="te-fact">${u.sprite ? esc(T("有精灵图片", "has sprite pictures")) : esc(T("没有精灵图片", "no sprite pictures"))}</span>
        <span class="te-fact">${u.has_model ? esc(T("已有三维模型", "already has a 3D model")) : esc(T("还没有三维模型", "no 3D model yet"))}</span>
        ${s ? (same && dimsOk ? `<span class="badge" data-tone="ok"><span class="dot"></span>${esc(T("当前这一页就是给它做的", "This tab is for it"))}</span>`
          : `<button type="button" class="btn btn-sm btn-ghost" data-act="use-unit">${icon("i-check")}${esc(T("让当前这一页做这个车辆", "Make this tab this unit"))}</button>`) : ""}`;
    }
    return `<section class="card te-target" id="te-target" style="--i:1">
      <div class="te-target-row">
        <div class="te-target-title">${icon("i-gamepad")}<b>${esc(T("你的模组和车辆", "Your mod and unit"))}</b></div>
        <select class="te-sel" id="te-tmod" aria-label="${esc(T("模组", "Mod"))}"><option value="">${esc(state.mods ? T("选择一个模组……", "Choose a mod…") : T("正在查找模组……", "Looking for mods…"))}</option>${modOptionsHTML(state.modSel)}</select>
        <button type="button" class="btn btn-sm btn-ghost" data-act="pick-folder">${icon("i-folder")}${esc(T("文件夹……", "Folder…"))}</button>
        <select class="te-sel" id="te-tunit" aria-label="${esc(T("车辆", "Unit"))}"${info ? "" : " disabled"}>${units.length ? units.map((x) => `<option value="${esc(x.id)}"${x.id === state.unitSel ? " selected" : ""}>${esc(x.id)}${x.name && x.name !== x.id ? " — " + esc(x.name) : ""}</option>`).join("") : `<option value="">${esc(T("（没有车辆）", "(no units)"))}</option>`}</select>
      </div>
      <div class="te-target-facts">${facts}</div>
    </section>`;
  }

  function renderTarget() {
    const el = root && root.querySelector("#te-target");
    if (!el) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = targetHTML();
    el.replaceWith(tmp.firstElementChild);
    highlightGuide(false);
  }

  function pickDefaultUnit() {
    const units = (state.modInfo && state.modInfo.units) || [];
    const s = cur();
    if (!units.some((u) => u.id === state.unitSel)) state.unitSel = (s && units.some((u) => u.id === s.unit_id)) ? s.unit_id : (units[0] ? units[0].id : null);
  }

  async function selectUnit(id) {
    state.unitSel = id || null;
    renderTarget();
    await loadSprite();
  }

  async function useUnit() {
    const u = selUnit();
    const s = cur();
    if (!u || !s) return;
    s.unit_id = u.id;
    if (!s.label || /^New /.test(s.label)) s.label = u.name || u.id;
    let msg = T(`这一页现在是 ${u.id}`, `This tab is now ${u.id}`);
    if (Math.abs(s.length - u.length) > 0.05 || (u.width && Math.abs(s.width - u.width) > 0.05)) {
      if (isImport(s)) {
        s.length = u.length;
        if (u.width) s.width = u.width;
        msg += T("（清单里的长宽已改成 mod.txt 的；模型本身不拉伸）", " (the manifest's length and width follow mod.txt; the model itself is not stretched)");
      } else {
        try {
          const fitted = await api("fit", { spec: clone(s), length: u.length, width: u.width || null });
          Object.keys(s).forEach((k) => delete s[k]);
          Object.assign(s, fitted);
          msg += T(`，并拉伸到 ${u.length} × ${u.width} 米`, `, stretched to ${u.length} × ${u.width} m`);
        } catch (e) { toast(errMsg(e), "danger"); }
      }
    }
    state.dirty[state.cur] = true;
    defaultIncludes();
    render();
    schedule(20);
    toast(msg, "ok");
  }

  // ------------------------------------------------------------------ the mod's sprite: eyedropper and overlay
  let spriteImgs = null;      // [{layer, img}]
  let spriteComp = null;      // the composited picture (full size), read by the eyedropper
  let spriteMap = null;       // picture <-> canvas <-> model metres

  async function loadSprite() {
    const u = selUnit();
    const info = state.modInfo;
    const key = info && u ? info.folder + "|" + u.id : null;
    if (key === state.spriteKey && state.sprite) return;
    state.spriteKey = key;
    state.sprite = null;
    spriteImgs = null;
    if (!key || !u.sprite) { renderSprite(); return; }
    try {
      const sp = await api("unit_sprite", { folder: info.folder, unit_id: u.id });
      if (state.spriteKey !== key) return;
      const imgs = await Promise.all(sp.layers.map((l) => new Promise((res) => {
        const img = new Image();
        img.onload = () => res({ layer: l, img });
        img.onerror = () => res(null);
        img.src = `data:${l.mime};base64,${l.data}`;
      })));
      if (state.spriteKey !== key) return;
      spriteImgs = imgs.filter(Boolean);
      sp.layers.forEach((l) => { delete l.data; });
      state.sprite = sp;
      const s = cur();
      let decor = 0;
      spriteImgs.forEach((x, i) => {
        if (state.spriteOpts.on[i] === undefined) state.spriteOpts.on[i] = true;
        if (state.spriteOpts.tint[i] === undefined) {
          const k = x.layer.kind === "decor" ? ["primary", "secondary", "roof"][decor++] : null;
          state.spriteOpts.tint[i] = k && s && s.materials && s.materials[k] ? hexOf(s.materials[k].color) : "#ffffff";
        }
      });
    } catch (e) {
      toast(T("读不了这个车辆的图片：", "The unit's pictures cannot be read: ") + errMsg(e), "warn");
    }
    renderSprite();
  }

  function spriteHTML() {
    const sp = state.sprite;
    const u = selUnit();
    if (!sp || !spriteImgs) {
      if (!u) return "";
      return `<section class="card te-sprite" id="te-sprite"><div class="te-sprite-head"><b>${esc(T("模组里的车辆图片", "The mod's picture of the unit"))}</b></div>
        <div class="te-hint" style="padding:0 12px 12px">${esc(u.sprite ? T("正在读取……", "Reading…") : T("这个车辆在 mod.txt 里没有 tex_base / tex_top 图片。", "This unit has no tex_base / tex_top pictures in mod.txt."))}</div></section>`;
    }
    const o = state.spriteOpts;
    const s = cur();
    const kindName = { base: ["底图", "base"], top: ["细节", "detail"], decor: ["涂装层", "decor"] };
    const layers = spriteImgs.map((x, i) => `<label class="te-layer" title="${esc(x.layer.name)}"><input type="checkbox" data-sprite-on="${i}"${o.on[i] ? " checked" : ""}>${esc(T(kindName[x.layer.kind][0], kindName[x.layer.kind][1]))}${x.layer.kind === "top" ? "" : `<input type="color" class="te-color te-tint" data-sprite-tint="${i}" value="${esc(o.tint[i] || "#ffffff")}" title="${esc(T("游戏里给这一层上的颜色（只用于这里的预览）", "The colour the game tints this layer with (for this preview only)"))}">`}</label>`).join("");
    const mats = Object.keys((s && s.materials) || {});
    return `<section class="card te-sprite" id="te-sprite">
      <div class="te-sprite-head"><b>${esc(T("模组里的车辆图片", "The mod's picture of the unit"))}</b> <code>${esc(sp.unit_id)}</code>
        <span class="te-hint">${esc(T("俯视图，前端（+X）在左；按车长截取", "top view, the front (+X) at the left, cut to the car's length"))}</span>
        <label class="te-check" style="min-height:0;margin-left:auto"><input type="checkbox" id="te-sprite-overlay"${o.overlay ? " checked" : ""}>${esc(T("叠加门窗位置", "Overlay doors and windows"))}</label></div>
      <div class="te-layers">${layers}</div>
      <div class="te-sprite-wrap"><canvas id="te-sprite-canvas" aria-label="${esc(T("车辆图片：点一下吸取颜色", "The unit's picture: click to take a colour"))}"></canvas></div>
      <div class="te-sprite-foot">
        <span class="te-lab">${icon("i-edit")}${esc(T("吸管：点图片，把颜色给", "Eyedropper: click the picture to give its colour to"))}</span>
        <select class="te-sel" id="te-sprite-target" style="width:auto">${mats.map((k) => `<option value="${esc(k)}"${k === o.target ? " selected" : ""}>${esc(MAT_LABELS[k] ? TT(MAT_LABELS[k]) + " · " + k : k)}</option>`).join("")}</select>
        <span class="te-read" id="te-sprite-read"></span>
      </div>
      ${sp.missing && sp.missing.length ? `<div class="te-hint" style="padding:0 12px 10px">${esc(T("找不到：", "Not found: "))}${esc(sp.missing.join(", "))}</div>` : ""}
    </section>`;
  }

  function renderSprite() {
    if (!root) return;
    const el = root.querySelector("#te-sprite");
    const html = spriteHTML();
    if (el) {
      if (!html) { el.remove(); return; }
      const tmp = document.createElement("div");
      tmp.innerHTML = html;
      el.replaceWith(tmp.firstElementChild);
    } else if (html) {
      const right = root.querySelector(".te-right");
      if (right) right.insertAdjacentHTML("beforeend", html);
    }
    bindSprite();
    drawSprite();
    highlightGuide(false);
  }

  function composite() {
    const sp = state.sprite;
    if (!sp || !spriteImgs || !spriteImgs.length) return null;
    const W = spriteImgs[0].img.naturalWidth, H = spriteImgs[0].img.naturalHeight;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const tmp = document.createElement("canvas");
    tmp.width = W; tmp.height = H;
    const t = tmp.getContext("2d");
    // the base picture, then the tinted livery layers, then the details on top
    const order = { base: 0, decor: 1, top: 2 };
    const layers = spriteImgs.map((x, i) => [x, i]).sort((a, b) => order[a[0].layer.kind] - order[b[0].layer.kind] || a[1] - b[1]);
    layers.forEach(([x, i]) => {
      if (!state.spriteOpts.on[i]) return;
      const tint = x.layer.kind === "top" ? null : (state.spriteOpts.tint[i] || "#ffffff");
      if (!tint || tint.toLowerCase() === "#ffffff") { g.drawImage(x.img, 0, 0, W, H); return; }
      // the game tints a layer: its grey times the colour, its own transparency kept
      t.globalCompositeOperation = "source-over";
      t.clearRect(0, 0, W, H);
      t.drawImage(x.img, 0, 0, W, H);
      t.globalCompositeOperation = "multiply";
      t.fillStyle = tint;
      t.fillRect(0, 0, W, H);
      t.globalCompositeOperation = "destination-in";
      t.drawImage(x.img, 0, 0, W, H);
      g.drawImage(tmp, 0, 0);
    });
    return c;
  }

  function drawSprite() {
    const cv = root && root.querySelector("#te-sprite-canvas");
    const sp = state.sprite;
    if (!cv || !sp || !spriteImgs || !spriteImgs.length) return;
    spriteComp = composite();
    const W = spriteComp.width, H = spriteComp.height;
    const crop = Math.max(8, Math.min(W, Math.round(sp.length / sp.tex_m_width * W)));
    const cssW = cv.parentElement.clientWidth || 600;
    const cssH = Math.max(40, Math.round(H * cssW / crop));
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.style.height = cssH + "px";
    cv.width = Math.round(cssW * dpr);
    cv.height = Math.round(cssH * dpr);
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, cssW, cssH);
    g.drawImage(spriteComp, 0, 0, crop, H, 0, 0, cssW, cssH);
    const pxPerM = W / sp.tex_m_width;          // picture pixels per metre along
    const pyPerM = H / sp.tex_m_height;         // and across
    const k = cssW / crop;
    spriteMap = {
      W, H, crop, cssW, cssH, k,
      toX: (u) => sp.length / 2 - (u / k) / pxPerM,
      toZ: (v) => sp.tex_m_height / 2 - (v / k) / pyPerM,
      u: (x) => (sp.length / 2 - x) * pxPerM * k,
      v: (z) => (sp.tex_m_height / 2 - z) * pyPerM * k,
    };
    if (state.spriteOpts.overlay && cur()) drawOverlay(g, cur(), spriteMap);
  }

  function drawOverlay(g, s, M) {
    const col = (name, a) => { const c = cssColor(name, "#888"); return `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${a})`; };
    const rect = (x0, x1, z0, z1, fill, stroke) => {
      const u0 = M.u(x1), u1 = M.u(x0), v0 = M.v(z1), v1 = M.v(z0);
      if (fill) { g.fillStyle = fill; g.fillRect(u0, v0, u1 - u0, v1 - v0); }
      if (stroke) { g.strokeStyle = stroke; g.lineWidth = 1.5; g.strokeRect(u0 + .5, v0 + .5, u1 - u0 - 1, v1 - v0 - 1); }
    };
    const vline = (x, color, dash) => { g.save(); g.setLineDash(dash || []); g.strokeStyle = color; g.lineWidth = 1.5; g.beginPath(); g.moveTo(M.u(x), 0); g.lineTo(M.u(x), M.cssH); g.stroke(); g.restore(); };
    const accent = col("--accent", 1), door = col("--danger", .5), doorLine = col("--danger", .95), win = col("--info", .45), roof = col("--warn", .35), roofLine = col("--warn", .9);
    const L = s.length, hw = s.width / 2;
    g.save();
    if (isImport(s)) {
      const b = state.report && state.report.box;
      if (b) rect(b.min[0], b.max[0], b.min[2], b.max[2], null, accent);
    } else if (isCar(s)) {
      const half = L / 2 - ((s.body || {}).end_inset !== undefined ? s.body.end_inset : 0.35);
      rect(-half, half, -hw, hw, null, accent);
      for (const row of s.windows || []) for (const x of row.centers || []) for (const z of [-1, 1]) rect(x - row.width / 2, x + row.width / 2, z > 0 ? hw - .22 : -hw, z > 0 ? hw : -hw + .22, win, null);
      const d = s.doors || {};
      for (const x of d.centers || []) for (const z of [-1, 1]) rect(x - d.width / 2, x + d.width / 2, z > 0 ? hw - .32 : -hw, z > 0 ? hw : -hw + .32, door, doorLine);
      const roofEq = s.roof || {};
      for (const pg of roofEq.pantographs || []) rect(pg.x - .62, pg.x + .62, -.5, .5, roof, roofLine);
      for (const ac of roofEq.ac_units || []) rect(ac.x - ac.length / 2, ac.x + ac.length / 2, -ac.width / 2, ac.width / 2, roof, roofLine);
    } else if (s.hood && Array.isArray(s.hood.sections)) {
      g.strokeStyle = accent; g.lineWidth = 1.5; g.beginPath();
      s.hood.sections.forEach((sec, i) => { const u = M.u(sec[0]), v = M.v(sec[1]); if (i) g.lineTo(u, v); else g.moveTo(u, v); });
      s.hood.sections.slice().reverse().forEach((sec) => g.lineTo(M.u(sec[0]), M.v(-sec[1])));
      g.closePath(); g.stroke();
      const roofItems = (items) => items.forEach((it) => {
        if (it.type === "side") return;
        if (it.type === "box" && it.center && it.center[1] > 3.3) rect(it.center[0] - it.size[0] / 2, it.center[0] + it.size[0] / 2, it.center[2] - it.size[2] / 2, it.center[2] + it.size[2] / 2, roof, roofLine);
        if (it.type === "cylinder" && it.axis === "y" && it.center && it.center[1] > 3.3) {
          g.fillStyle = roof; g.strokeStyle = roofLine; g.beginPath(); g.arc(M.u(it.center[0]), M.v(it.center[2]), it.radius * M.k * (M.W / state.sprite.tex_m_width), 0, Math.PI * 2); g.fill(); g.stroke();
        }
      });
      roofItems(s.details || []);
    }
    const bg = s.bogies || {};
    if (typeof bg.pivot_fraction === "number") for (const x of [-L * bg.pivot_fraction, L * bg.pivot_fraction]) vline(x, accent, [5, 4]);
    g.restore();
  }

  function bindSprite() {
    const cv = root && root.querySelector("#te-sprite-canvas");
    if (!cv || cv.dataset.bound) return;
    cv.dataset.bound = "1";
    const at = (e) => {
      if (!spriteMap || !spriteComp) return null;
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const pu = Math.floor(x / spriteMap.k), pv = Math.floor(y / spriteMap.k);
      if (pu < 0 || pv < 0 || pu >= spriteMap.crop || pv >= spriteMap.H) return null;
      const d = spriteComp.getContext("2d").getImageData(pu, pv, 1, 1).data;
      const hex = "#" + [d[0], d[1], d[2]].map((v) => v.toString(16).padStart(2, "0")).join("");
      return { hex, alpha: d[3], x: spriteMap.toX(x), z: spriteMap.toZ(y) };
    };
    cv.addEventListener("mousemove", (e) => {
      const p = at(e);
      const out = root && root.querySelector("#te-sprite-read");
      if (!out) return;
      out.innerHTML = p ? `<i class="te-swatch" style="background:${p.alpha > 8 ? p.hex : "transparent"}"></i>${p.alpha > 8 ? p.hex : esc(T("透明", "clear"))} · x = ${p.x.toFixed(2)} m · z = ${p.z.toFixed(2)} m` : "";
    });
    cv.addEventListener("click", (e) => {
      const p = at(e);
      const s = cur();
      if (!p || !s) return;
      if (p.alpha <= 8) { toast(T("这里是透明的，换个地方点", "That spot is transparent: click somewhere else"), "info"); return; }
      const k = state.spriteOpts.target;
      if (!s.materials || !s.materials[k]) return;
      s.materials[k].color = linOf(p.hex);
      markDirty();
      renderForm();
      drawSprite();
      schedule(60);
      toast(T(`${k} 的颜色改成 ${p.hex}`, `${k} is now ${p.hex}`), "ok");
    });
  }

  // ------------------------------------------------------------------ the guide: making a model for your mod's unit
  const goEx = (zh, en) => `<div class="te-guide-ex">${icon("i-info")}<span><b>${esc(T("GO 示例：", "GO example: "))}</b>${T(zh, en)}</span></div>`;
  const GUIDE = [
    {
      t: ["打开你的模组，选中车辆", "Open your mod and pick the unit"],
      body: () => T(
        `<p>三维模型是给模组里<b>某一个</b> <code>[TrainUnit]</code> 做的。在上面“你的模组和车辆”里选模组（本地模组和订阅的创意工坊物品都列出来了）和车辆。编辑器读它的 <code>mod.txt</code>：</p>
         <ul><li><code>id=</code>：模型的 unit_id 必须一字不差；</li><li><code>length=</code>、<code>width=</code>：模型按这个长宽做（长度含车钩）；</li><li><code>tex_base</code> / <code>tex_top</code> / <code>tex_decors</code>：游戏画这节车用的俯视图片，后面拿来取色和对位置。</li></ul>`,
        `<p>A 3D model is made for <b>one</b> <code>[TrainUnit]</code> of a mod. Under Your mod and unit above, choose the mod (your local mods and your Workshop subscriptions are listed) and the unit. The editor reads its <code>mod.txt</code>:</p>
         <ul><li><code>id=</code>: the model's unit_id must be exactly this;</li><li><code>length=</code>, <code>width=</code>: the model is built to them (the length includes the couplers);</li><li><code>tex_base</code> / <code>tex_top</code> / <code>tex_decors</code>: the top-view pictures the game draws the car with, used later for colours and positions.</li></ul>`) +
        goEx("创意工坊物品 2388066983 有三个车辆；机车是 <code>id=mp40_bl</code>、<code>length=20.73</code>、<code>width=3.2</code>、<code>tex_base=mp40bl/MP40_base.png</code>。",
          "the Workshop item 2388066983 has three units; its locomotive is <code>id=mp40_bl</code>, <code>length=20.73</code>, <code>width=3.2</code>, <code>tex_base=mp40bl/MP40_base.png</code>."),
      targets: ["#te-target"],
      actions: [["go", ["用 GO 示例跟着做", "Follow along with the GO example"]]],
    },
    {
      t: ["选最接近的模板", "Pick the closest template"],
      body: () => T(
        `<p>从最像的车开始，再改形状：</p><ul>
          <li><b>动车组车厢</b>：自带动力的客车，一端司机室、车顶有受电弓（地铁、城际动车）。</li>
          <li><b>客车</b>：被机车牵引的客车，两端贯通道，没有司机室。</li>
          <li><b>控制车</b>：客车在 +X 端加司机室（推拉列车的末端）。</li>
          <li><b>罩式内燃机车</b>：北美机车：窄机罩、一端司机室、外走道。</li>
          <li><b>箱形电力机车</b>：全宽车体、两端司机室、车顶受电弓（欧洲、亚洲常见）。</li></ul>
         <p>形状差得很远（蒸汽机车、有轨电车铰接车……）就在 Blender 里自己建模，用“导入 GLB”。</p>`,
        `<p>Start from the most alike, then change the shape:</p><ul>
          <li><b>Multiple-unit car</b>: a passenger car with its own power, a cab at one end, a pantograph on the roof (metro, regional EMU).</li>
          <li><b>Coach</b>: a hauled passenger car with gangways at both ends, no cab.</li>
          <li><b>Cab car</b>: a coach with a driving cab at +X (the far end of a push-pull train).</li>
          <li><b>Hood diesel locomotive</b>: North American: a narrow hood, a cab at one end, walkways.</li>
          <li><b>Box-cab electric</b>: a full-width body, cabs at both ends, pantographs (common in Europe and Asia).</li></ul>
         <p>For something quite different (a steam engine, an articulated tram...) model it in Blender and use Import GLB.</p>`) +
        goEx("MP40 用罩式机车模板，BiLevel 客车是客车（双层车内），控制车是控制车。示例里是做好的样子。", "the MP40 is a hood unit, the BiLevel coach a coach (with the bi-level interior), its cab car a cab car. The example shows them finished."),
      targets: ["#te-new", ".te-tabs"],
      actions: [["tpl:emu", ["动车组车厢", "Multiple-unit car"]], ["tpl:coach", ["客车", "Coach"]], ["tpl:cab_car", ["控制车", "Cab car"]], ["tpl:locomotive:hood", ["罩式机车", "Hood locomotive"]], ["tpl:locomotive:carbody", ["箱形电力机车", "Box-cab electric"]], ["import", ["导入 GLB……", "Import GLB…"]]],
    },
    {
      t: ["定尺寸", "Set the dimensions"],
      body: () => T(
        `<p>长、宽来自 mod.txt。点<b>拉伸到车辆尺寸</b>，门窗、截面、车顶设备会按比例挪到新长宽上。</p>
         <ul><li>车顶高度（离轨面）：动车组、客车 3.8–4.1 米；双层车 4.6–4.9 米；北美机车 4.5–4.8 米；欧洲电力机车 3.9–4.2 米。</li>
         <li>地板高：高站台车 1.1–1.3 米；低地板车、双层车下层 0.55–0.8 米。</li>
         <li>车体断面表格从侧墙底部一层层到车顶中线；w = 1 是全宽，越往上越小就是车顶的圆弧。</li></ul>`,
        `<p>Length and width come from mod.txt. Press <b>Stretch to the unit</b>: doors, windows, sections and roof equipment move to the new size.</p>
         <ul><li>Roof height above the rail head: multiple units and coaches 3.8–4.1 m; bi-level cars 4.6–4.9 m; North American locomotives 4.5–4.8 m; European electrics 3.9–4.2 m.</li>
         <li>Floor height: 1.1–1.3 m for high-platform cars; 0.55–0.8 m for low-floor cars and a bi-level's lower deck.</li>
         <li>The Body shape table goes level by level from the bottom of the side to the middle of the roof; w = 1 is the full width, smaller values above make the roof's curve.</li></ul>`) +
        goEx("BiLevel 高 4.65 米，侧墙到 3.34 米是竖直的，往上 w 收到 0.92、0.66，再到车顶中线。", "the BiLevel is 4.65 m tall; its side is vertical up to 3.34 m, then w narrows to 0.92 and 0.66 up to the roof's middle."),
      targets: ['[data-g="unit"]', '[data-g="shape"]'], open: ["unit", "shape"],
      actions: [["fit", ["拉伸到车辆尺寸", "Stretch to the unit"]], ["tab:bilevel1", ["在 BiLevel 上看", "Show me on the BiLevel"]]],
    },
    {
      t: ["涂装：从模组图片取色", "Livery: colours from the mod's picture"],
      body: () => T(
        `<p>预览下面是模组自己的车辆图片（俯视，前端在左），按车长截取。在<b>吸管</b>里选一个材质，再点图片上的颜色。</p>
         <p>很多模组的图片是灰色的，颜色由玩家在游戏里选的涂装决定（tex_decors 就是上色遮罩）：把每层的颜色设成你在游戏里用的颜色就能看到效果；或者直接用真车的颜色。然后在“车体断面”里决定每条色带用哪个材质。</p>`,
        `<p>Below the preview is the mod's own picture of the unit (top view, the front at the left), cut to the car's length. Under <b>Eyedropper</b> choose a material, then click a colour in the picture.</p>
         <p>Many mods paint grey pictures that the game tints with the livery chosen in game (tex_decors are such tint masks): set each layer's colour to the one you use in game to see it, or use the real train's colours. Then decide in Body shape which band of the body gets which material.</p>`) +
        goEx("GO 的图片是灰的；GO 绿是材质 go_green（线性颜色 0.035, 0.29, 0.17）。", "the GO pictures are grey; the GO green is the material go_green (linear 0.035, 0.29, 0.17)."),
      targets: ["#te-sprite", '[data-g="livery"]'], open: ["livery"],
      actions: [["sprite", ["显示车辆图片", "Show the picture"]]],
    },
    {
      t: ["车门和车窗", "Doors and windows"],
      body: () => T(
        `<ul><li>在“车窗”里用<b>自动排布</b>填每侧门数。通勤车每侧 2–4 个门，宽 1.3–1.4 米，双扇对开（每扇滑开门宽一半再多几厘米）；城际客车 1–2 个门，宽 0.8–1.0 米，单扇，在车端附近。</li>
         <li>窗宽 1.0–1.6 米，窗间立柱 0.4–0.6 米；窗下沿约在地板上 0.8 米。</li>
         <li>勾上图片的<b>叠加门窗位置</b>：门（红）和窗（蓝）画在图片上，可以对着图片里的车顶设备、通过台对齐。鼠标停在图片上能读出 x（米），填进门中心列表。</li></ul>`,
        `<ul><li>Under Windows use <b>Arrange</b> with the doors per side. Commuter cars: 2–4 doors per side, 1.3–1.4 m wide, bi-parting (each leaf slides half the width plus a few cm); intercity coaches: 1–2 doors of 0.8–1.0 m near the ends, one leaf.</li>
         <li>Windows 1.0–1.6 m wide with 0.4–0.6 m pillars; their bottom about 0.8 m above the floor.</li>
         <li>Tick <b>Overlay doors and windows</b> on the picture: doors (red) and windows (blue) are drawn on it, so you can line them up with roof equipment and vestibules in the picture. Hover the picture to read x in metres and type it into the door centres.</li></ul>`) +
        goEx("BiLevel 每侧两组门，x = ±6.10 米，宽 1.12 米，每扇滑开 0.60 米；拖预览上的“车门”滑块看开门。", "the BiLevel has two door pairs per side at x = ±6.10 m, 1.12 m wide, each leaf sliding 0.60 m; drag Doors on the preview to see them open."),
      targets: ['[data-g="doors"]', '[data-g="windows"]', "#te-sprite"], open: ["doors", "windows"],
      actions: [["tab:bilevel1", ["在 BiLevel 上看", "Show me on the BiLevel"]], ["arrange2", ["每侧 2 个门自动排布", "Arrange 2 doors per side"]], ["doors-open", ["打开车门看看", "Open the doors"]]],
    },
    {
      t: ["车端、车顶和走行部", "Ends, roof and running gear"],
      body: () => T(
        `<ul><li><b>司机室</b>：+X 是前端；控制车的司机室在 +X，编组里用 <code>flip</code> 翻转到列车尾部。设前窗、车灯，需要的话加 V 形条纹和风笛。</li>
         <li><b>贯通道</b>：客车两端都有；动车组只在没有司机室的一端。</li>
         <li><b>车顶</b>：电动车组、电力机车每节 1–2 个受电弓；空调机组。</li>
         <li><b>转向架</b>：客车中心约在 ±0.34–0.36 × 车长，轴距 2.3–2.6 米，车轮半径 0.43 米（直径 860 毫米）；机车约 ±0.31 × 车长，车轮半径 0.50–0.52 米，2 或 3 根轴。</li></ul>`,
        `<ul><li><b>Cabs</b>: +X is the front; a cab car has its cab at +X, and consists use <code>flip</code> to turn it round at the end of the train. Set the windscreen and lamps, chevrons and horns if it has them.</li>
         <li><b>Gangways</b>: at both ends of a coach; on a multiple-unit car only at the end without a cab.</li>
         <li><b>Roof</b>: 1–2 pantographs per electric car or locomotive; air-conditioning units.</li>
         <li><b>Bogies</b>: coaches have their centres at about ±0.34–0.36 × the length, axles 2.3–2.6 m apart, wheels of 0.43 m radius (860 mm); locomotives about ±0.31 × the length, wheels 0.50–0.52 m radius, 2 or 3 axles.</li></ul>`) +
        goEx("MP40 是 B-B：两台转向架在 ±6.43 米，轴在 ±1.4 米，车轮半径 0.51 米。", "the MP40 is a B-B: two bogies at ±6.43 m, axles at ±1.4 m, wheel radius 0.51 m."),
      targets: ['[data-g="cab"]', '[data-g="gangway"]', '[data-g="roof"]', '[data-g="running"]', '[data-g="hood"]'], open: ["cab", "running"],
      actions: [["view-front", ["看车头", "Look at the front"]]],
    },
    {
      t: ["三级细节（LOD）", "Levels of detail (LODs)"],
      body: () => T(
        `<ul><li><b>LOD0</b> 近处看：完整车内。</li><li><b>LOD1</b> 中距离：简化的座椅和司机台。</li><li><b>LOD2</b> 远处：没有车内，玻璃不透明。</li></ul>
         <p>附加组件按距离选，三级都要有。每节车的预算：LOD0 约 15,000 个三角形以内，LOD1 约一半，LOD2 约 2,500 以内；几百节车同屏时 LOD2 最要紧。点预览下面的 LOD 看每一级；“车内”里的细节等级决定 LOD0 有多细。</p>`,
        `<ul><li><b>LOD0</b> for close up: the full interior.</li><li><b>LOD1</b> for middle distance: simpler seats and desks.</li><li><b>LOD2</b> for far away: no interior, opaque glass.</li></ul>
         <p>The add-on picks by distance and needs all three. Per car: LOD0 within about 15,000 triangles, LOD1 about half, LOD2 within about 2,500; with hundreds of cars on screen LOD2 matters most. Click a LOD under the preview to look at each; Interior detail sets how fine LOD0 is.</p>`) +
        goEx("BiLevel 是 12,518 / 7,038 / 1,888 个三角形。", "the BiLevel has 12,518 / 7,038 / 1,888 triangles."),
      targets: ["#te-stats", '[data-g="interior"]'], open: ["interior"],
      actions: [["lod0", ["看 LOD0", "Show LOD0"]], ["lod2", ["看 LOD2", "Show LOD2"]]],
    },
    {
      t: ["导出到模组并检查", "Export to the mod and check"],
      body: () => T(
        `<p>在“导出到模组”里选模组，勾上要导出的规格，每个对上一个车辆 id，点<b>导出</b>。文件只写进 <code>&lt;模组&gt;\\nimby3d\\</code>（manifest.json、每个车辆三个 .gov、.rig.json 和你的规格），被替换的文件先备份。导出后的检查会列出附加组件会写进日志的那几行。</p>
         <p>你自己的本地模组（<code>%USERPROFILE%\\Saved Games\\Weird and Wry\\NIMBY Rails\\mods\\&lt;文件夹&gt;</code>）最稳妥；创意工坊物品的文件夹可能被 Steam 更新清掉。</p>`,
        `<p>Under Export to a mod choose the mod, tick the specs, give each its unit id, press <b>Export</b>. Files go into <code>&lt;mod&gt;\\nimby3d\\</code> only (manifest.json, three .gov per unit, .rig.json, your spec); anything replaced is backed up first. The check after exporting lists the very lines the add-on will write to its log.</p>
         <p>Your own local mod (<code>%USERPROFILE%\\Saved Games\\Weird and Wry\\NIMBY Rails\\mods\\&lt;folder&gt;</code>) is the safest place; a Workshop item's folder can be wiped by a Steam update.</p>`),
      targets: ["#te-export"],
      actions: [["export-go", ["到导出这里", "Go to Export"]]],
    },
    {
      t: ["在游戏里测试", "Test it in the game"],
      body: () => T(
        `<ol><li><b>重启 NIMBY Rails</b>：模型只在启动后读一次。</li>
         <li>按 <b>F10</b> → “铁路”页 → 确认 <b>“车辆自带模型”</b> 开着。</li>
         <li>把这个车辆编进列车，在三维里看它。</li>
         <li>看附加组件的日志（游戏文件夹里的 <code>nimby3d_probe.log</code>，或管理器活动面板的“附加组件”页）：<br><code>trains: N local mods read (M with models of their own)</code>（本地模组）<br><code>vehicle models: &lt;模组&gt;/&lt;车辆&gt;: 3 levels, a / b / c triangles</code> 表示用上了；<code>not used (…)</code> 写着原因。</li></ol>`,
        `<ol><li><b>Restart NIMBY Rails</b>: models are read once, after the game starts.</li>
         <li>Press <b>F10</b> → Railway page → make sure <b>Vehicles' own models</b> is on.</li>
         <li>Put the unit in a train and look at it in 3D.</li>
         <li>In the add-on's log (<code>nimby3d_probe.log</code> in the game folder, or the Add-on tab of the manager's activity panel):<br><code>trains: N local mods read (M with models of their own)</code> (local mods)<br><code>vehicle models: &lt;mod&gt;/&lt;unit&gt;: 3 levels, a / b / c triangles</code> means it is used; <code>not used (…)</code> says why not.</li></ol>`) +
        goEx("<code>vehicle models: 2388066983/mp40_bl: 3 levels, 5564 / 2668 / 668 triangles</code>", "<code>vehicle models: 2388066983/mp40_bl: 3 levels, 5564 / 2668 / 668 triangles</code>"),
      targets: [],
      actions: [],
    },
  ];

  function guideHTML() {
    if (!state.guide.on) return "";
    const n = state.guide.step;
    const st = GUIDE[n];
    const dots = GUIDE.map((g, i) => `<button type="button" class="te-gdot" data-act="guide-step" data-n="${i}" aria-current="${i === n}" title="${esc(TT(g.t))}">${i + 1}</button>`).join("");
    return `<section class="card te-guide" id="te-guide" aria-live="polite">
      <div class="te-guide-head"><span class="te-guide-n">${esc(T("第", "Step"))} ${n + 1} / ${GUIDE.length}</span><h3>${esc(TT(st.t))}</h3>
        <button type="button" class="te-icon-btn" data-act="guide-close" aria-label="${esc(T("关闭向导", "Close the guide"))}">${icon("i-x")}</button></div>
      <div class="te-guide-title">${esc(T("为模组车辆制作 3D 模型", "Make a 3D model for your mod's vehicle"))}</div>
      <div class="te-guide-body">${st.body()}</div>
      ${st.actions.length ? `<div class="te-guide-actions">${st.actions.map(([k, l]) => `<button type="button" class="btn btn-sm btn-ghost" data-act="guide-act" data-k="${esc(k)}">${esc(TT(l))}</button>`).join("")}</div>` : ""}
      <div class="te-guide-nav"><button type="button" class="btn btn-sm btn-ghost" data-act="guide-prev"${n === 0 ? " disabled" : ""}>← ${esc(T("上一步", "Back"))}</button>
        <div class="te-gdots">${dots}</div>
        ${n === GUIDE.length - 1 ? `<button type="button" class="btn btn-sm" data-act="guide-close">${esc(T("完成", "Done"))}</button>` : `<button type="button" class="btn btn-sm te-guide-next" data-act="guide-next">${esc(T("下一步", "Next"))} →</button>`}</div>
    </section>`;
  }

  function highlightGuide(scroll) {
    if (!root) return;
    root.querySelectorAll(".te-hl").forEach((x) => x.classList.remove("te-hl"));
    if (!state.guide.on) return;
    const st = GUIDE[state.guide.step];
    let first = null;
    for (const sel of st.targets) {
      root.querySelectorAll(sel).forEach((el) => {
        el.classList.add("te-hl");
        if (el.tagName === "DETAILS" && !el.open) { el.open = true; if (el.dataset.g) state.open.add(el.dataset.g); }
        if (!first) first = el;
      });
    }
    if (scroll && first) first.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function goStep(n) {
    state.guide.step = Math.max(0, Math.min(GUIDE.length - 1, n));
    const st = GUIDE[state.guide.step];
    for (const g of st.open || []) state.open.add(g);
    render();
    highlightGuide(true);
  }

  async function guideAction(k) {
    const s = cur();
    if (k === "go") {
      await loadExample("go_train");
      const m = state.mods && state.mods.mods.find((x) => x.id === "2388066983");
      if (m) {
        state.modSel = m.folder; state.modInfo = m; state.unitSel = "mp40_bl";
        defaultIncludes(); render(); await loadSprite();
        toast(T("已打开 GO 示例并选中模组 2388066983 的 mp40_bl", "Opened the GO example with mp40_bl of the mod 2388066983 selected"), "ok");
      } else {
        toast(T("已打开 GO 示例（这台电脑上没有订阅 GO 模组，所以没有它的图片）", "Opened the GO example (the GO mod is not installed here, so its pictures are not shown)"), "info");
      }
    } else if (k.startsWith("tpl:")) {
      const [, kind, style] = k.split(":");
      try {
        const spec = await api("new_spec", { kind, style: style || null });
        state.specs.push(spec); state.dirty.push(true); state.cur = state.specs.length - 1;
        if (viewer) viewer.payload = null;
        if (selUnit()) await useUnit(); else { defaultIncludes(); render(); schedule(10); }
      } catch (e) { toast(errMsg(e), "danger"); }
    } else if (k.startsWith("tab:")) {
      const id = k.slice(4);
      const i = state.specs.findIndex((x) => x.unit_id === id);
      if (i < 0) { toast(T("先用第 1 步打开 GO 示例", "Open the GO example first (step 1)"), "info"); return; }
      state.cur = i;
      if (state.modInfo && state.modInfo.units.some((u) => u.id === id)) state.unitSel = id;
      for (const g of GUIDE[state.guide.step].open || []) state.open.add(g);
      render();
      schedule(10);
      highlightGuide(true);
      await loadSprite();
    } else if (k === "import") {
      await importGlb();
    } else if (k === "fit") {
      if (!selUnit()) { toast(T("先在上面选模组和车辆", "Choose the mod and unit above first"), "warn"); return; }
      await useUnit();
    } else if (k === "sprite") {
      if (!selUnit()) { toast(T("先在上面选模组和车辆", "Choose the mod and unit above first"), "warn"); return; }
      await loadSprite();
      const el = root.querySelector("#te-sprite");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (k === "arrange2") {
      if (!s || isImport(s) || !isCar(s)) { toast(T("这个车体样式没有可排布的客室门", "This body style has no passenger doors to arrange"), "info"); return; }
      try { setSpec(await api("arrange", { spec: clone(s), doors_per_side: 2, window_width: ((s.windows || [])[0] || {}).width || 1.2, pillar: 0.5 })); } catch (e) { toast(errMsg(e), "danger"); }
    } else if (k === "doors-open") {
      state.open01 = 1;
      if (viewer) viewer.setDoors(1, state.side);
      const d = root.querySelector("#te-door");
      if (d) d.value = 100;
    } else if (k === "view-front") {
      if (viewer) viewer.view("front");
    } else if (k === "lod0" || k === "lod2") {
      state.lod = k === "lod0" ? 0 : 2;
      render(); schedule(0);
    } else if (k === "export-go") {
      const el = root.querySelector("#te-export");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // ------------------------------------------------------------------ importing a model (GLB)
  const GLB_FILTERS = [["glTF binary", "*.glb"]];
  async function importGlb() {
    const path = await ctx.pickFile({ title: T("导入模型（.glb）", "Import a model (.glb)"), filters: GLB_FILTERS });
    if (!path) return;
    const u = selUnit();
    try {
      const r = await api("import_glb", { path, unit_id: u ? u.id : null, label: u ? u.name : null, kind: null, length: u ? u.length : null, width: u ? u.width || null : null });
      state.specs.push(r.spec);
      state.dirty.push(true);
      state.cur = state.specs.length - 1;
      state.report = r.report;
      state.open.add("import");
      if (viewer) viewer.payload = null;
      defaultIncludes();
      render();
      schedule(10);
      const n = (r.warnings || []).length;
      toast(n ? T(`已导入；有 ${n} 条提醒，见预览下方`, `Imported; ${n} warning${n > 1 ? "s" : ""} under the preview`) : T("已导入", "Imported"), n ? "warn" : "ok");
    } catch (e) { toast(errMsg(e), "danger"); }
  }

  async function pickGlb(lod) {
    const s = cur();
    const path = await ctx.pickFile({ title: T(`LOD${lod} 的模型（.glb）`, `The model for LOD${lod} (.glb)`), filters: GLB_FILTERS });
    if (!path) return;
    const lods = ((s.import || {}).lods || []).concat([null, null, null]).slice(0, 3);
    lods[lod] = path;
    s.import.lods = lods;
    setSpec(s);
  }

  function placeOnRails() {
    const s = cur();
    const b = state.report && state.report.box;
    if (!s || !b) { toast(T("等预览生成后再试", "Wait for the preview, then try again"), "info"); return; }
    const off = (s.import.offset || [0, 0, 0]).slice();
    off[0] = r4(off[0] - (b.min[0] + b.max[0]) / 2);
    off[1] = r4(off[1] - b.min[1]);
    off[2] = r4(off[2] - (b.min[2] + b.max[2]) / 2);
    s.import.offset = off;
    setSpec(s);
    toast(T(`平移改为 ${off.join(", ")}`, `Moved by ${off.join(", ")}`), "ok");
  }

  // ------------------------------------------------------------------ the page
  const TRAIN_ICON_PATHS = '<rect x="5" y="3" width="14" height="13.5" rx="3.2"/><path d="M5 10.5h14M9.5 6.5h5M8.5 13.2h.01M15.5 13.2h.01M8 16.5 6 21M16 16.5l2 4.5M7.2 19h9.6"/>';
  const PAGE = {
    id: "trains",
    icon: `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${TRAIN_ICON_PATHS}</svg>`,
    title: { zh: "列车编辑器", en: "Train editor" },
    mount(el, c) {
      root = el;
      ctx = c;
      root.classList.add("te-root");
      root.addEventListener("input", onInput);
      root.addEventListener("change", onChange);
      root.addEventListener("click", onClick);
      root.addEventListener("toggle", onToggle, true);
      if (typeof ctx.onLang === "function") offLang = ctx.onLang(() => { if (root) render(); });
      // the theme (data-theme) and the skin (data-skin) change CSS variables the viewer reads
      themeObs = new MutationObserver(() => viewer && viewer.themeChanged());
      themeObs.observe(document.documentElement, { attributes: true });
      mediaQ = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
      if (mediaQ && mediaQ.addEventListener) mediaQ.addEventListener("change", onMedia);
      render();
      (async () => {
        try { state.examples = await api("examples", {}); state.addonScansLocal = !!state.examples.addon_scans_local_mods; } catch (e) { state.examples = { examples: [] }; }
        if (state.first && !state.specs.length) {
          state.first = false;
          try {
            const ex = await api("load_example", { name: "go_train" });
            state.specs = ex.specs;
            state.dirty = ex.specs.map(() => false);
            state.exampleName = "go_train";
          } catch (e) { /* no example: start empty */ }
        }
        render();
        schedule(10);
        loadMods(false);
      })();
    },
    // the app keeps the page in the document and only hides it when another tab is shown
    show() {
      if (!viewer) return;
      viewer.resume();
      viewer.themeChanged();
      if (state.mods && Date.now() - (state.modsAt || 0) > 60000) loadMods(true);
    },
    hide() {
      if (viewer) viewer.pause();
    },
    unmount() {
      clearTimeout(timer);
      seq++;
      if (viewer) { viewer.destroy(); viewer = null; }
      if (typeof offLang === "function") offLang();
      offLang = null;
      if (themeObs) themeObs.disconnect();
      themeObs = null;
      if (mediaQ && mediaQ.removeEventListener) mediaQ.removeEventListener("change", onMedia);
      if (root) {
        root.removeEventListener("input", onInput);
        root.removeEventListener("change", onChange);
        root.removeEventListener("click", onClick);
        root.removeEventListener("toggle", onToggle, true);
        root.innerHTML = "";
        root.classList.remove("te-root");
      }
      root = null;
    },
  };
  function onMedia() { if (viewer) setTimeout(() => viewer && viewer.themeChanged(), 50); }
  function onToggle(e) { if (e.target && e.target.id === "te-tut") state.tutOpen = e.target.open; }

  (window.N3D_PAGES = window.N3D_PAGES || []).push(PAGE);
})();
