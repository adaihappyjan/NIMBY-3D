/* The Shader packs page of Nimby3D: the Minecraft (Iris / OptiFine) shader packs in %APPDATA%\.minecraft\shaderpacks,
   which one the add-on draws the 3D view with (nimby3d.ini in the game folder: shaderpack=, shaderpack_file=), and
   each pack's own profile and options (shaderpack_profile=, shaderpack_options=). A page of app.js (mount(root, ctx));
   the backend is app.py's packs_* calls (manager/shaderpacks.py), a pack's options come from n3d_packinfo.exe. */
"use strict";
(() => {
  const B = (window.N3D_BUILTIN_PAGES = window.N3D_BUILTIN_PAGES || {});

  // ---------------------------------------------------------------- what the add-on sets itself
  // src/iris/pack.h adjust_for_nimby: over the pack's defaults and its profile, before shaderpack_options= (which wins)
  function strtod(s) {
    const m = /^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(String(s ?? ""));
    return m ? parseFloat(m[0]) : NaN;
  }
  function nimbyValue(o) {
    const name = o.name, def = String(o.default ?? ""), vals = (o.values || []).map(String);
    if (o.kind === "toggle" && name === "DOUBLE_REIM_CLOUDS") return "false";
    if (o.kind === "toggle" && name === "ADVANCED_MATERIALS" && def !== "true") return "true";
    if (name === "MATERIAL_FORMAT" && def === "0" && vals.includes("1")) return "1";
    if (o.kind === "toggle" || !vals.length) return null;
    const up = name.toUpperCase();
    if (up === "SHADOWDISTANCE" || up === "SHADOWMAPRESOLUTION") {
      const dist = up === "SHADOWDISTANCE", want = dist ? 1024 : 4096, d = strtod(def);
      let best = null, bestV = -1;
      for (const a of vals) {
        const v = strtod(a);
        if (isNaN(v)) continue;
        if (dist ? (v <= want && v > bestV) : (v >= want && (bestV < 0 || v < bestV))) { bestV = v; best = a; }
      }
      return best !== null && !isNaN(d) && bestV > d ? best : null;
    }
    if (!up.includes("CLOUD") || (!up.includes("ALT") && !up.includes("HEIGHT"))) return null;
    const d = strtod(def);
    if (isNaN(d) || d >= 400) return null;
    let best = null, most = d;
    for (const a of vals) {
      const v = strtod(a);
      if (!isNaN(v) && v > most) { most = v; best = a; }
    }
    return best;
  }
  const clean = (s) => String(s ?? "").replace(/§[0-9a-fk-or]/gi, "").replace(/\s*\[\*\]\s*/g, " ").trim();
  const pretty = (n) => { const s = String(n).replace(/_+/g, " ").trim().toLowerCase(); return s ? s[0].toUpperCase() + s.slice(1) : String(n); };

  B.packs = {
    mount(root, ctx) {
      const T = ctx.t, U = ctx.util, esc = U.esc, icon = U.icon;
      const $ = (sel) => root.querySelector(sel);
      let list = null, busy = false, ed = null, loadSeq = 0;

      root.innerHTML = `
        <section class="card page-head" style="--i:0">
          <div class="card-icon big"><svg class="i"><use href="#i-sparkles"/></svg></div>
          <div class="ph-text"><h1 id="pk-title"></h1><p class="sub" id="pk-lead"></p></div>
          <div class="ph-side">
            <button type="button" id="pk-master" class="switch" role="switch" aria-checked="false"><span class="track"><span class="thumb"></span></span><span class="label"></span></button>
          </div>
        </section>
        <div class="notes page-notes" id="pk-notes"></div>
        <section class="card pk-card" style="--i:1">
          <div class="pk-toolbar">
            <div class="pk-where" id="pk-where"></div>
            <div class="pk-actions">
              <button type="button" class="btn btn-sm btn-ghost" id="pk-add-zip"><svg class="i"><use href="#i-plus"/></svg><span></span></button>
              <button type="button" class="btn btn-sm btn-ghost" id="pk-add-dir"><svg class="i"><use href="#i-folder"/></svg><span></span></button>
              <button type="button" class="btn btn-sm btn-ghost" id="pk-open"><svg class="i"><use href="#i-folder-open"/></svg><span></span></button>
              <button type="button" class="icon-btn" id="pk-reload"><svg class="i"><use href="#i-refresh"/></svg></button>
            </div>
          </div>
          <div class="pk-list" id="pk-list"></div>
        </section>
        <section class="card pk-editor" id="pk-editor" style="--i:2" hidden></section>`;

      // ------------------------------------------------ the list
      async function load(quiet) {
        const seq = ++loadSeq;
        try {
          const r = await ctx.call("packs_list", {});
          if (seq !== loadSeq) return;
          list = r;
        } catch (e) {
          if (!quiet) ctx.toast(e.message, "error");
        }
        render();
      }
      const shortName = (n) => String(n).replace(/\.zip$/i, "");
      function render() {
        $("#pk-title").textContent = T("光影包", "Shader packs");
        $("#pk-lead").textContent = T("用为 Iris / OptiFine 制作的 Minecraft 光影包来画游戏里的三维视图。在这里添加、移除、选用光影包，并调整每个光影包自己的选项。",
          "Minecraft shader packs made for Iris or OptiFine can draw the 3D view in the game. Add, remove and choose packs here, and set each pack's own options.");
        $("#pk-add-zip span").textContent = T("添加 .zip…", "Add a .zip…");
        $("#pk-add-dir span").textContent = T("添加文件夹…", "Add a folder…");
        $("#pk-open span").textContent = T("打开文件夹", "Open folder");
        $("#pk-reload").title = T("刷新", "Refresh");
        $("#pk-reload").setAttribute("aria-label", T("刷新", "Refresh"));
        const sel = (list && list.selection) || null;
        const packs = (list && list.packs) || [];
        const master = $("#pk-master");
        master.setAttribute("aria-checked", String(!!(sel && sel.enabled)));
        master.querySelector(".label").textContent = T("用光影包画三维视图", "Draw the 3D view with a shader pack");
        master.disabled = busy || !list || !list.game || !packs.length;
        master.title = !list || !list.game ? T("没有找到游戏文件夹", "The game folder was not found") : !packs.length ? T("还没有光影包", "No shader packs yet") : "";

        const notes = [];
        const note = (tone, ic, text) => notes.push(`<div class="note" data-tone="${tone}">${icon(ic)}<span>${esc(text)}</span></div>`);
        if (list && !list.game) note("danger", "i-x-circle", T("没有找到游戏文件夹：选择光影包要写入游戏文件夹里的 nimby3d.ini（在主页选择游戏文件夹）。",
          "The game folder was not found: choosing a pack writes nimby3d.ini in the game folder (choose the game folder on the Home page)."));
        if (list && list.running) note("warn", "i-alert", T("NIMBY Rails 正在运行。游戏里的设置面板（F10）也会写 nimby3d.ini：之后在游戏里改的设置可能会覆盖这里的选择。",
          "NIMBY Rails is running. The settings panel in the game (F10) also writes nimby3d.ini: what you change there afterwards can replace what is set here."));
        if (sel && sel.enabled && sel.owner && !packs.some((p) => p.selected)) note("warn", "i-alert", T(`选中的光影包 ${sel.owner} 不在文件夹里。`, `The chosen pack ${sel.owner} is not in the folder.`));
        if (list && list.packinfo && !list.packinfo.exists) note("warn", "i-alert", T(`缺少读取光影包选项的工具 n3d_packinfo.exe，所以看不到光影包的选项：${list.packinfo.path || ""}`,
          `The pack reader n3d_packinfo.exe is missing, so packs' options cannot be shown: ${list.packinfo.path || ""}`));
        note("info", "i-clock", T("改动在下次启动游戏时生效（游戏运行时，也可以在游戏里按 F10 →“画面”重新选一次这个光影包）。",
          "Changes take effect the next time the game starts (while it runs, you can also pick the pack again in the game: F10 → Picture)."));
        note("info", "i-info", T("实验功能，目前只支持 NVIDIA 显卡。标着“已知可用”的光影包和 Nimby3D 一起试过。",
          "Experimental, NVIDIA graphics cards only for now. Packs marked “Known to work” have been tried with Nimby3D."));
        $("#pk-notes").innerHTML = notes.join("");

        $("#pk-where").innerHTML = list ? `${icon("i-folder")}<span class="mono" title="${esc(list.dir)}">${esc(list.dir)}</span>` +
          (list.exists ? "" : `<span class="faint">${esc(T("（还不存在，添加光影包时会创建）", "(not there yet: made when you add a pack)"))}</span>`) : "";
        ["#pk-add-zip", "#pk-add-dir", "#pk-open"].forEach((id) => { $(id).disabled = busy; });

        const box = $("#pk-list");
        if (!list) {
          box.innerHTML = `<div class="pk-loading"><span class="spin"></span><span>${esc(T("正在读取…", "Loading…"))}</span></div>`;
        } else if (!packs.length) {
          box.innerHTML = `<div class="empty big">${icon("i-sparkles")}<div><b>${esc(T("还没有光影包", "No shader packs yet"))}</b><span>${esc(T("点“添加 .zip…”或“添加文件夹…”，或者把光影包放进上面的文件夹。光影包里要有 shaders 文件夹。",
            "Click “Add a .zip…” or “Add a folder…”, or put packs into the folder above. A pack has a shaders folder inside."))}</span></div></div>`;
        } else {
          box.innerHTML = packs.map((p) => row(p, sel)).join("");
        }
        renderEditor();
      }
      function row(p, sel) {
        const on = p.selected && sel && sel.enabled;
        const meta = [p.kind === "zip" ? "ZIP" : T("文件夹", "Folder")];
        if (p.size !== null && p.size !== undefined) meta.push(U.bytes(p.size));
        if (p.kind === "folder" && p.files) meta.push(T(`${p.files} 个文件`, `${p.files} files`));
        if (p.mtime) meta.push(U.when(p.mtime));
        const badges = [];
        if (on) badges.push(`<span class="badge" data-tone="accent"><span class="dot"></span>${esc(T("正在使用", "In use"))}</span>`);
        else if (p.selected) badges.push(`<span class="badge" data-tone="muted">${esc(T("已选（光影包关闭中）", "Chosen · packs off"))}</span>`);
        if (p.known) badges.push(`<span class="badge" data-tone="ok" title="${esc(T("和 Nimby3D 一起试过", "Tried with Nimby3D"))}">${esc(T("已知可用", "Known to work"))}</span>`);
        const nset = p.selected && sel ? sel.option_count : 0;
        if (p.selected && nset) badges.push(`<span class="badge" data-tone="info">${esc(T(`${nset} 项选项`, `${nset} options set`))}</span>`);
        else if (!p.selected && p.saved) badges.push(`<span class="badge" data-tone="info" title="${esc(T("选用它时会放回 nimby3d.ini", "Put back into nimby3d.ini when you choose it"))}">${esc(T("记住了选项", "Options remembered"))}</span>`);
        const canUse = !busy && list.game && !on;
        return `<div class="pk-row${p.selected ? " sel" : ""}${on ? " on" : ""}" data-name="${esc(p.name)}">
          <div class="pk-ic">${icon(p.kind === "zip" ? "i-zip" : "i-folder")}</div>
          <div class="pk-main"><div class="pk-name" title="${esc(p.name)}">${esc(shortName(p.name))}</div><div class="pk-meta">${esc(meta.join(" · "))}</div></div>
          <div class="pk-badges">${badges.join("")}</div>
          <div class="pk-btns">
            <button type="button" class="btn btn-sm ${on ? "btn-ghost" : "btn-soft"}" data-act="use"${canUse ? "" : " disabled"}>${icon(on ? "i-check" : "i-play")}<span>${esc(on ? T("使用中", "In use") : T("使用", "Use"))}</span></button>
            <button type="button" class="btn btn-sm btn-ghost" data-act="options"${list.packinfo && list.packinfo.exists ? "" : ` title="${esc(T("缺少 n3d_packinfo.exe", "n3d_packinfo.exe is missing"))}"`}>${icon("i-sliders")}<span>${esc(T("选项", "Options"))}</span></button>
            <button type="button" class="icon-btn danger" data-act="remove" title="${esc(T("移到回收站", "Move to the Recycle Bin"))}" aria-label="${esc(T("移到回收站", "Move to the Recycle Bin"))}"${busy ? " disabled" : ""}>${icon("i-trash")}</button>
          </div>
        </div>`;
      }

      async function run(fn) {
        if (busy) return;
        busy = true;
        render();
        try { await fn(); } catch (e) { ctx.toast(e.message, "error"); }
        busy = false;
        await load(true);
      }
      const choose = (name) => run(async () => {
        await ctx.call("packs_select", { name });
        ctx.toast(T(`已选用 ${shortName(name)}\n下次启动游戏时生效。`, `${shortName(name)} chosen\nUsed the next time the game starts.`), "ok");
      });
      async function addPack(path, replace) {
        try {
          const r = await ctx.call("packs_import", { path, replace: !!replace });
          ctx.toast(T(`已添加 ${shortName(r.name)}`, `Added ${shortName(r.name)}`), "ok");
        } catch (e) {
          if (e.code === "pack_exists" && !replace) {
            const name = (e.params && e.params.name) || path;
            const yes = await ctx.confirm({ title: T(`替换 ${name}？`, `Replace ${name}?`),
              body: T("文件夹里已经有一个同名的光影包。原来那个会移到回收站。", "A pack of that name is already in the folder. The one there goes to the Recycle Bin."),
              ok: T("替换", "Replace"), danger: true });
            if (yes) await addPack(path, true);
            return;
          }
          throw e;
        }
      }
      $("#pk-add-zip").addEventListener("click", () => run(async () => {
        const path = await ctx.pickFile({ title: T("选择光影包（.zip）", "Choose a shader pack (.zip)"), filters: [[T("光影包", "Shader pack"), "*.zip"]] });
        if (path) await addPack(path, false);
      }));
      $("#pk-add-dir").addEventListener("click", () => run(async () => {
        const path = await ctx.pickFolder({ title: T("选择光影包文件夹（里面有 shaders 文件夹）", "Choose a shader pack folder (with a shaders folder inside)") });
        if (path) await addPack(path, false);
      }));
      $("#pk-open").addEventListener("click", () => ctx.call("packs_open_folder", {}).catch((e) => ctx.toast(e.message, "error")));
      $("#pk-reload").addEventListener("click", () => load(false));
      $("#pk-master").addEventListener("click", () => {
        const on = $("#pk-master").getAttribute("aria-checked") !== "true";
        run(async () => {
          await ctx.call("packs_enable", { on });
          ctx.toast(on ? T("光影包已打开\n下次启动游戏时生效。", "Shader packs on\nUsed the next time the game starts.") : T("光影包已关闭\n下次启动游戏时生效。", "Shader packs off\nTakes effect the next time the game starts."), "ok");
        });
      });
      $("#pk-list").addEventListener("click", async (ev) => {
        const b = ev.target.closest("[data-act]");
        const r = ev.target.closest(".pk-row");
        if (!b || !r || b.disabled) return;
        const name = r.dataset.name;
        if (b.dataset.act === "use") choose(name);
        else if (b.dataset.act === "options") openEditor(name);
        else if (b.dataset.act === "remove") {
          const yes = await ctx.confirm({ title: T(`把 ${shortName(name)} 移到回收站？`, `Move ${shortName(name)} to the Recycle Bin?`),
            body: T("需要时可以从回收站还原。", "You can restore it from the Recycle Bin."), ok: T("移到回收站", "Move to Recycle Bin"), danger: true });
          if (!yes) return;
          run(async () => {
            const res = await ctx.call("packs_remove", { name });
            ctx.toast(T(`${shortName(name)} 已移到回收站`, `${shortName(name)} moved to the Recycle Bin`), "ok");
            if (res.turned_off) ctx.toast(T("它是正在使用的光影包，所以光影包已关闭。", "It was the pack in use, so shader packs are now off."), "warn");
            if (ed && ed.name === name) { ed = null; }
          });
        }
      });

      // ------------------------------------------------ a pack's options
      const lbl = (x) => (x && typeof x === "object" ? clean(x[ctx.lang] || x.en || x.zh) : clean(x));
      const table = () => { const m = new Map(); ((ed.data && ed.data.info && ed.data.info.options) || []).forEach((o) => m.set(o.name, o)); return m; };
      const baseValue = (o) => (ed.profile && ed.profDefaults && ed.profDefaults[o.name] !== undefined ? String(ed.profDefaults[o.name]) : String(o.default ?? ""));
      const baseline = (o) => { const n = nimbyValue(o); return n !== null ? n : baseValue(o); };
      const current = (o) => (ed.chosen[o.name] !== undefined ? String(ed.chosen[o.name]) : baseline(o));
      const valid = (o, v) => (o.values || []).map(String).includes(String(v));
      function diff() {
        const t0 = table(), out = {};
        Object.keys(ed.chosen).sort().forEach((k) => {
          const o = t0.get(k);
          if (o && valid(o, ed.chosen[k]) && String(ed.chosen[k]) !== baseline(o)) out[k] = String(ed.chosen[k]);
        });
        return out;
      }
      const snapshot = () => JSON.stringify({ p: ed.profile, o: diff() });
      const dirty = () => !!(ed && ed.data && ed.data.info && ed.saved !== undefined && snapshot() !== ed.saved);
      function vlabel(o, v) {
        const vl = o.value_labels || {};
        let x = vl[v];
        if (!x) {
          const n = strtod(v);
          if (!isNaN(n)) for (const k of Object.keys(vl)) if (strtod(k) === n && /^\s*[+-]?[\d.]/.test(k)) { x = vl[k]; break; }
        }
        const s = lbl(x);
        return s || String(v);
      }

      async function openEditor(name) {
        if (ed && ed.name !== name && dirty()) {
          const yes = await ctx.confirm({ title: T("放弃没有保存的改动？", "Discard the changes not saved?"),
            body: T(`${shortName(ed.name)} 的选项还没有保存。`, `The options of ${shortName(ed.name)} are not saved yet.`), ok: T("放弃", "Discard"), danger: true });
          if (!yes) return;
        }
        ed = { name, data: null, loading: true, profile: "", chosen: {}, profDefaults: null, search: "", open: new Set(), saved: undefined };
        renderEditor();
        $("#pk-editor").scrollIntoView({ behavior: "smooth", block: "start" });
        try {
          const d = await ctx.call("packs_info", { name });
          if (!ed || ed.name !== name) return;
          ed.data = d;
          ed.profile = (d.current && d.current.profile) || "";
          ed.chosen = Object.assign({}, (d.current && d.current.options) || {});
          ed.profDefaults = d.profile_defaults || null;
          if (d.info) {
            ed.saved = snapshot();
            if (ed.profile && !(d.info.profiles || []).some((p) => p.name === ed.profile)) {
              ed.badProfile = ed.profile; // (a profile the pack does not have keeps it from opening: saving takes it out)
              ed.profile = "";
              ed.profDefaults = null;
            }
          }
        } catch (e) {
          if (!ed || ed.name !== name) return;
          ed.fail = e.message;
        }
        ed.loading = false;
        renderEditor();
      }
      async function setProfile(p) {
        ed.profile = p;
        ed.profDefaults = null;
        if (p) {
          ed.profLoading = true;
          renderEditor();
          try {
            const d = await ctx.call("packs_info", { name: ed.name, profile: p });
            if (ed && ed.profile === p) ed.profDefaults = d.profile_defaults || null;
          } catch (e) { ctx.toast(e.message, "error"); }
          ed.profLoading = false;
        }
        renderEditor();
      }
      async function save() {
        const options = diff();
        try {
          const r = await ctx.call("packs_save_options", { name: ed.name, profile: ed.profile, options });
          const n = Object.keys(options).length;
          ed.chosen = options;
          ed.saved = snapshot();
          ctx.toast(r.result && r.result.in_ini
            ? T(`已保存 ${shortName(ed.name)} 的选项（${n} 项）\n下次启动游戏时生效。`, `Options of ${shortName(ed.name)} saved (${n} set)\nUsed the next time the game starts.`)
            : T(`已记住 ${shortName(ed.name)} 的选项（${n} 项）\n选用这个光影包时生效。`, `Options of ${shortName(ed.name)} remembered (${n} set)\nUsed when you choose this pack.`), "ok");
          load(true);
        } catch (e) { ctx.toast(e.message, "error"); }
      }
      async function saveRaw() {
        const text = $("#po-raw").value;
        const options = {};
        text.split(/[\s,;]+/).forEach((w) => { const i = w.indexOf("="); if (i > 0 && i + 1 < w.length) options[w.slice(0, i)] = w.slice(i + 1); });
        try {
          await ctx.call("packs_save_options", { name: ed.name, profile: (ed.data && ed.data.current && ed.data.current.profile) || "", options });
          ctx.toast(T("已保存", "Saved"), "ok");
          load(true);
        } catch (e) { ctx.toast(e.message, "error"); }
      }

      function optionRow(o) {
        const cur = current(o), base = baseline(o), nv = nimbyValue(o);
        const changed = ed.chosen[o.name] !== undefined && String(ed.chosen[o.name]) !== base;
        const label = lbl(o.label) || o.name;
        const hint = lbl(o.comment);
        let ctl;
        const vals = (o.values || []).map(String);
        if (o.kind === "toggle") {
          ctl = `<button type="button" class="switch sm" role="switch" aria-checked="${cur === "true"}" data-set="toggle" aria-label="${esc(label)}"><span class="track"><span class="thumb"></span></span></button>`;
        } else {
          const choices = vals.slice();
          if (!choices.includes(cur)) choices.unshift(cur);
          const isSlider = (ed.data.info.sliders || []).includes(o.name) && choices.length >= 3;
          if (isSlider) {
            ctl = `<input type="range" min="0" max="${choices.length - 1}" step="1" value="${Math.max(0, choices.indexOf(cur))}" data-set="slider" aria-label="${esc(label)}" data-choices="${esc(JSON.stringify(choices))}"><span class="po-val">${esc(vlabel(o, cur))}</span>`;
          } else {
            ctl = `<select data-set="select" aria-label="${esc(label)}"${choices.length <= 1 ? " disabled" : ""}>${choices.map((v) =>
              `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(vlabel(o, v))}${v === base && !valid(o, v) ? esc(T("（默认）", " (default)")) : ""}</option>`).join("")}</select>`;
          }
        }
        const tag = nv !== null && cur === nv ? `<span class="badge po-nimby" data-tone="accent" title="${esc(T(`Nimby3D 为 NIMBY 的尺度设的值（光影包默认：${vlabel(o, baseValue(o))}）。在这里改就会用你选的值。`, `Set by Nimby3D for NIMBY's scale (the pack's default: ${vlabel(o, baseValue(o))}). Change it here to use your own.`))}">Nimby3D</span>` : "";
        return `<div class="po-row${changed ? " changed" : ""}" data-opt="${esc(o.name)}">
          <div class="po-text"><div class="po-label"><span>${esc(label)}</span>${label !== o.name ? `<span class="po-name">${esc(o.name)}</span>` : ""}${tag}</div>${hint ? `<div class="po-hint" title="${esc(hint)}">${esc(hint)}</div>` : ""}</div>
          <div class="po-ctl">${ctl}</div>
          <button type="button" class="icon-btn po-reset" data-reset title="${esc(T("恢复默认", "Back to the default"))}" aria-label="${esc(T("恢复默认", "Back to the default"))}"${changed ? "" : " hidden"}>${icon("i-undo")}</button>
        </div>`;
      }
      function screenHtml() {
        const info = ed.data.info, sc = info.screens || {}, t0 = table();
        const keys = Object.keys(sc);
        if (!keys.length) return `<div class="po-grid">${info.options.map(optionRow).join("")}</div>`;
        const onScreen = new Set();
        keys.forEach((k) => (sc[k] || []).forEach((e) => { if (t0.has(e)) onScreen.add(e); }));
        const linked = new Set();
        keys.forEach((k) => (sc[k] || []).forEach((e) => { const m = /^\[(.+)\]$/.exec(e); if (m) linked.add(m[1]); }));
        const rootName = ["main", "", "screen"].find((k) => k in sc) ?? keys.find((k) => !linked.has(k)) ?? keys[0];
        const stars = keys.some((k) => (sc[k] || []).includes("*"));
        const changedIn = (name, seen) => {
          let n = 0;
          (sc[name] || []).forEach((e) => {
            const m = /^\[(.+)\]$/.exec(e);
            if (m) { if (!seen.has(m[1]) && sc[m[1]]) { seen.add(m[1]); n += changedIn(m[1], seen); } }
            else if (e === "*") info.options.forEach((o) => { if (!onScreen.has(o.name) && isChanged(o)) n++; });
            else if (t0.has(e) && isChanged(t0.get(e))) n++;
          });
          return n;
        };
        const block = (name, seen) => {
          let cells = "";
          for (const e of sc[name] || []) {
            const m = /^\[(.+)\]$/.exec(e);
            if (m) {
              const sub = m[1];
              if (seen.has(sub) || !sc[sub]) continue;
              const next = new Set(seen).add(sub);
              const n = changedIn(sub, new Set([sub]));
              const title = lbl((info.screen_labels || {})[sub]) || pretty(sub);
              cells += `<details class="po-group" data-screen="${esc(sub)}"${ed.open.has(sub) ? " open" : ""}><summary>${icon("i-chevron", "i chev")}<span>${esc(title)}</span>${n ? `<span class="badge" data-tone="accent">${esc(T(`改了 ${n} 项`, `${n} changed`))}</span>` : ""}</summary><div class="po-grid">${block(sub, next)}</div></details>`;
            } else if (e === "*") {
              cells += info.options.filter((o) => !onScreen.has(o.name)).map(optionRow).join("");
            } else if (t0.has(e)) {
              cells += optionRow(t0.get(e));
            }
          }
          return cells;
        };
        let html = `<div class="po-grid">${block(rootName, new Set([rootName]))}</div>`;
        const left = info.options.filter((o) => !onScreen.has(o.name));
        if (left.length && !stars) {
          const n = left.filter(isChanged).length;
          html += `<details class="po-group po-hidden" data-screen="__other"${ed.open.has("__other") ? " open" : ""}><summary>${icon("i-chevron", "i chev")}<span>${esc(T(`不在光影包菜单里的选项（${left.length}）`, `Options not in the pack's menus (${left.length})`))}</span>${n ? `<span class="badge" data-tone="accent">${esc(T(`改了 ${n} 项`, `${n} changed`))}</span>` : ""}</summary><div class="po-grid">${left.map(optionRow).join("")}</div></details>`;
        }
        return html;
      }
      const isChanged = (o) => ed.chosen[o.name] !== undefined && String(ed.chosen[o.name]) !== baseline(o);
      function searchHtml(q) {
        const info = ed.data.info, words = q.toLowerCase().split(/\s+/).filter(Boolean);
        const hits = info.options.filter((o) => {
          const hay = [o.name, lbl(o.label), lbl(o.comment), o.label && o.label.en, o.label && o.label.zh].join(" ").toLowerCase();
          return words.every((w) => hay.includes(w));
        });
        if (!hits.length) return `<div class="empty">${icon("i-search")}<span>${esc(T("没有匹配的选项。", "No option matches."))}</span></div>`;
        return `<div class="po-grid">${hits.slice(0, 300).map(optionRow).join("")}</div>`;
      }

      function renderEditor() {
        const box = $("#pk-editor");
        if (!ed) { box.hidden = true; box.innerHTML = ""; return; }
        box.hidden = false;
        const d = ed.data;
        const selected = d ? d.selected : packsSelected(ed.name);
        const where = selected
          ? T("保存到游戏文件夹的 nimby3d.ini（shaderpack_options=），下次启动游戏时生效。", "Saved into nimby3d.ini in the game folder (shaderpack_options=); used the next time the game starts.")
          : T("这个光影包现在没有被选用：选项会先记住，选用它时再写进 nimby3d.ini。", "This is not the pack chosen now: its options are remembered and go into nimby3d.ini when you choose it.");
        let html = `<div class="ped-head">
            <div class="card-icon">${icon("i-sliders")}</div>
            <div class="ped-title"><h2>${esc(T("选项", "Options"))} · <span title="${esc(ed.name)}">${esc(shortName(ed.name))}</span></h2><p>${esc(where)}</p></div>
            <button type="button" class="icon-btn" id="ped-close" title="${esc(T("关闭", "Close"))}" aria-label="${esc(T("关闭", "Close"))}">${icon("i-x")}</button>
          </div>`;
        if (ed.loading) {
          html += `<div class="pk-loading"><span class="spin"></span><span>${esc(T("正在读取光影包…", "Reading the pack…"))}</span></div>`;
        } else if (ed.fail || !d) {
          html += `<div class="callout warn">${icon("i-alert")}<span>${esc(ed.fail || "?")}</span></div>`;
        } else if (!d.info) {
          const cur = d.current || {};
          const raw = Object.entries(cur.options || {}).map(([k, v]) => `${k}=${v}`).join(" ");
          html += `<div class="callout warn">${icon("i-alert")}<span>${esc((d.error && d.error.message) || "?")}</span></div>
            <p class="ped-p">${esc(T("读不出这个光影包的选项列表。你仍然可以直接写 shaderpack_options（NAME=VALUE，用空格分开）：", "The pack's list of options could not be read. You can still write shaderpack_options directly (NAME=VALUE, separated by spaces):"))}</p>
            <textarea id="po-raw" class="po-raw mono" spellcheck="false">${esc(raw)}</textarea>
            ${cur.profile ? `<p class="ped-p faint">${esc(T(`预设：${cur.profile}`, `Profile: ${cur.profile}`))}</p>` : ""}
            <div class="ped-foot"><button type="button" class="btn btn-sm btn-accent" id="po-raw-save">${icon("i-save")}<span>${esc(T("保存", "Save"))}</span></button></div>`;
        } else if (!d.info.options.length) {
          html += `<div class="empty">${icon("i-info")}<span>${esc(T("这个光影包没有可以设置的选项（有些光影包是加密或锁定的）。", "This pack exposes no options (some packs are encrypted or locked)."))}</span></div>`;
        } else {
          const info = d.info, n = Object.keys(diff()).length, isDirty = dirty();
          const profs = info.profiles || [];
          const defName = info.default_profile;
          const profLabel = (p) => lbl(p.label) || p.name;
          const defText = T("光影包默认", "Pack's defaults") + (defName ? ` (= ${profLabel(profs.find((p) => p.name === defName) || { name: defName })})` : "");
          const t0 = table();
          const invalid = Object.keys(ed.chosen).filter((k) => !t0.has(k) || !valid(t0.get(k), ed.chosen[k]));
          html += `<div class="ped-bar">
              ${profs.length ? `<label class="ped-field"><span>${esc(T("预设", "Profile"))}</span><select id="ped-profile">${[`<option value="">${esc(defText)}</option>`].concat(profs.map((p) => `<option value="${esc(p.name)}"${p.name === ed.profile ? " selected" : ""}>${esc(profLabel(p))}</option>`)).join("")}</select>${ed.profLoading ? '<span class="spin sm"></span>' : ""}</label>` : ""}
              <label class="ped-search">${icon("i-search")}<input type="search" id="ped-search" placeholder="${esc(T(`搜索 ${info.options.length} 个选项`, `Search ${info.options.length} options`))}" value="${esc(ed.search)}" spellcheck="false" autocomplete="off"></label>
              <span class="ped-count${n ? " on" : ""}">${esc(n ? T(`改了 ${n} 项`, `${n} changed`) : T("全部为默认", "All at defaults"))}</span>
              <button type="button" class="btn btn-sm btn-ghost" id="ped-reset"${!n && !ed.profile ? " disabled" : ""}>${icon("i-undo")}<span>${esc(T("恢复光影包默认", "Reset to the pack's defaults"))}</span></button>
              <button type="button" class="btn btn-sm btn-accent" id="ped-save"${isDirty ? "" : " disabled"}>${icon("i-save")}<span>${esc(isDirty ? T("保存", "Save") : T("已保存", "Saved"))}</span></button>
            </div>
            <div class="ped-notes">
              <div class="note" data-tone="info">${icon("i-info")}<span>${esc(T("标着 Nimby3D 的值是插件为 NIMBY 的尺度自己设的（比如阴影范围、云的高度）；在这里改了就用你选的值。只保存和默认不同的选项。",
                "Values marked Nimby3D are set by the add-on itself for NIMBY's scale (shadow range, cloud height…); change them here to use your own. Only options that differ from the defaults are saved."))}</span></div>
              ${ed.badProfile && !ed.profile ? `<div class="note" data-tone="warn">${icon("i-alert")}<span>${esc(T(`nimby3d.ini 选了这个光影包没有的预设 ${ed.badProfile}，光影包会打不开。保存即可去掉它。`,
                `nimby3d.ini names a profile this pack does not have (${ed.badProfile}), so the pack would not open. Save to take it out.`))}</span></div>` : ""}
              ${invalid.length ? `<div class="note" data-tone="warn">${icon("i-alert")}<span>${esc(T(`nimby3d.ini 里这些不是这个光影包的选项或值，保存时会去掉：${invalid.map((k) => k + "=" + ed.chosen[k]).join(" ")}`,
                `These in nimby3d.ini are not options or values of this pack and are dropped when you save: ${invalid.map((k) => k + "=" + ed.chosen[k]).join(" ")}`))}</span></div>` : ""}
            </div>
            <div class="ped-body" id="ped-body">${ed.search.trim() ? searchHtml(ed.search.trim()) : screenHtml()}</div>`;
        }
        const focused = document.activeElement && box.contains(document.activeElement) ? document.activeElement.id : null;
        const caret = focused === "ped-search" ? $("#ped-search").selectionStart : null;
        box.innerHTML = html;
        if (focused && $("#" + focused)) {
          $("#" + focused).focus();
          if (caret !== null) { try { $("#ped-search").setSelectionRange(caret, caret); } catch (e) { /* not text */ } }
        }
      }
      function packsSelected(name) {
        return !!(list && (list.packs || []).some((p) => p.name === name && p.selected));
      }
      function refreshRow(name) {
        const rowEl = root.querySelector(`.po-row[data-opt="${CSS.escape(name)}"]`);
        const o = table().get(name);
        if (rowEl && o) {
          const tmp = document.createElement("div");
          tmp.innerHTML = optionRow(o);
          rowEl.replaceWith(tmp.firstElementChild);
        }
        const n = Object.keys(diff()).length, isDirty = dirty();
        const cnt = $(".ped-count");
        if (cnt) { cnt.textContent = n ? T(`改了 ${n} 项`, `${n} changed`) : T("全部为默认", "All at defaults"); cnt.classList.toggle("on", !!n); }
        const sv = $("#ped-save");
        if (sv) { sv.disabled = !isDirty; sv.querySelector("span").textContent = isDirty ? T("保存", "Save") : T("已保存", "Saved"); }
        const rs = $("#ped-reset");
        if (rs) rs.disabled = !n && !ed.profile;
        root.querySelectorAll(".po-group").forEach((g) => {
          const n1 = g.querySelectorAll(".po-row.changed").length;
          const sum = g.querySelector(":scope > summary");
          let b = sum.querySelector(".badge");
          if (n1) {
            if (!b) { b = document.createElement("span"); b.className = "badge"; b.dataset.tone = "accent"; sum.appendChild(b); }
            b.textContent = T(`改了 ${n1} 项`, `${n1} changed`);
          } else if (b) b.remove();
        });
      }
      function setOption(name, v) {
        const o = table().get(name);
        if (!o) return;
        if (String(v) === baseline(o)) delete ed.chosen[name];
        else ed.chosen[name] = String(v);
        refreshRow(name);
        const el = root.querySelector(`.po-row[data-opt="${CSS.escape(name)}"] [data-set]`);
        if (el) el.focus();
      }
      const edBox = $("#pk-editor");
      edBox.addEventListener("click", async (ev) => {
        const t1 = ev.target;
        if (t1.closest("#ped-close")) {
          if (dirty()) {
            const yes = await ctx.confirm({ title: T("放弃没有保存的改动？", "Discard the changes not saved?"), ok: T("放弃", "Discard"), danger: true });
            if (!yes) return;
          }
          ed = null;
          renderEditor();
          return;
        }
        if (t1.closest("#ped-save")) return save();
        if (t1.closest("#po-raw-save")) return saveRaw();
        if (t1.closest("#ped-reset")) {
          ed.chosen = {};
          ed.profile = "";
          ed.profDefaults = null;
          renderEditor();
          return;
        }
        const sw = t1.closest('[data-set="toggle"]');
        if (sw) {
          const name = sw.closest(".po-row").dataset.opt;
          setOption(name, sw.getAttribute("aria-checked") === "true" ? "false" : "true");
          return;
        }
        const rs = t1.closest("[data-reset]");
        if (rs) {
          const name = rs.closest(".po-row").dataset.opt;
          delete ed.chosen[name];
          refreshRow(name);
        }
      });
      edBox.addEventListener("change", (ev) => {
        const t1 = ev.target;
        if (t1.id === "ped-profile") return setProfile(t1.value);
        const row1 = t1.closest(".po-row");
        if (!row1) return;
        if (t1.dataset.set === "select") setOption(row1.dataset.opt, t1.value);
        else if (t1.dataset.set === "slider") setOption(row1.dataset.opt, JSON.parse(t1.dataset.choices)[Number(t1.value)]);
      });
      edBox.addEventListener("input", (ev) => {
        const t1 = ev.target;
        if (t1.id === "ped-search") {
          ed.search = t1.value;
          const body = $("#ped-body");
          if (body) body.innerHTML = ed.search.trim() ? searchHtml(ed.search.trim()) : screenHtml();
          return;
        }
        if (t1.dataset.set === "slider") {
          const o = table().get(t1.closest(".po-row").dataset.opt);
          const v = JSON.parse(t1.dataset.choices)[Number(t1.value)];
          const out = t1.parentElement.querySelector(".po-val");
          if (o && out) out.textContent = vlabel(o, v);
        }
      });
      edBox.addEventListener("toggle", (ev) => {
        const g = ev.target;
        if (!g.classList || !g.classList.contains("po-group")) return;
        if (g.open) ed.open.add(g.dataset.screen); else ed.open.delete(g.dataset.screen);
      }, true);

      ctx.onLang(() => render());
      this._load = load;
      this._fresh = true;
      render();
      load(false);
    },
    show() {
      if (this._fresh) this._fresh = false;
      else if (this._load) this._load(true);
    },
  };
})();
