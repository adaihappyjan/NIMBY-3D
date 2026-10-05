/* The Add-on settings page of Nimby3D: every setting of the in-game panel (F10) that nimby3d.ini keeps, described by
   settings_schema.json (tools/dump_settings.cpp), shown by the panel's pages and changed in nimby3d.ini of the game
   folder line by line (manager/nimby3d_ini.py: comments and everything else in the file stay as they are). Plus where
   the add-on's files are. A page of app.js (mount(root, ctx)). */
"use strict";
(() => {
  const B = (window.N3D_BUILTIN_PAGES = window.N3D_BUILTIN_PAGES || {});
  const DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

  B.settings = {
    mount(root, ctx) {
      const T = ctx.t, U = ctx.util, esc = U.esc, icon = U.icon;
      const $ = (sel) => root.querySelector(sel);
      let data = null, filter = "all", search = "", loadSeq = 0;

      root.innerHTML = `
        <section class="card page-head" style="--i:0">
          <div class="card-icon big"><svg class="i"><use href="#i-sliders"/></svg></div>
          <div class="ph-text"><h1 id="st-title"></h1><p class="sub" id="st-lead"></p></div>
          <div class="ph-side">
            <button type="button" class="btn btn-sm btn-ghost" id="st-show"><svg class="i"><use href="#i-file"/></svg><span></span></button>
            <button type="button" class="btn btn-sm btn-ghost" id="st-reset-all"><svg class="i"><use href="#i-undo"/></svg><span></span></button>
          </div>
        </section>
        <div class="notes page-notes" id="st-notes"></div>
        <div class="st-layout">
          <aside class="card st-side" style="--i:1">
            <label class="ped-search">${icon("i-search")}<input type="search" id="st-search" spellcheck="false" autocomplete="off"></label>
            <div class="st-pages" id="st-pages" role="tablist"></div>
          </aside>
          <div class="st-main" id="st-main"></div>
        </div>
        <section class="card st-where" id="st-where" style="--i:3"></section>`;

      const L = (x) => (x && typeof x === "object" ? x[ctx.lang] || x.en || x.zh || "" : String(x ?? ""));
      const has = (s, f) => (s.flags || []).includes(f);
      const shown = () => {
        if (!data || !data.schema) return [];
        return (data.schema.settings || []).filter((s) => s.kind !== "pick" && !has(s, "station") && !has(s, "nofile"));
      };
      const value = (s) => (data.values && data.values[s.key] !== undefined ? Number(data.values[s.key]) : Number(s.default));
      const changed = (s) => Math.abs(value(s) - Number(s.default)) > 1e-9;
      const decimals = (step) => { let d = 0, x = Number(step) || 1; while (d < 3 && Math.abs(x - Math.round(x)) > 1e-6) { d++; x *= 10; } return d; };

      function fmt(s, v) {
        if (s.key === "ground_slots") return `${Math.round(v)} · ${Math.round(v * 1.5)} MB`;
        if (has(s, "percent")) return `${Math.round(v * 100)}%`;
        if (has(s, "height")) return `${v.toFixed(1)}${T(" 米", " m")}`;
        if (has(s, "metres")) return `${(v / 1000).toFixed(1)}${T(" 公里", " km")}`;
        if (has(s, "degrees")) return `${Math.round(v)}°`;
        if (has(s, "times")) return `${v.toFixed(1)}×`;
        return v.toFixed(2);
      }
      const zoneText = (h) => {
        const sign = h < 0 ? "−" : "+", a = Math.abs(h), hh = Math.floor(a), mm = Math.round((a - hh) * 60);
        return `UTC${sign}${hh}${mm ? ":" + String(mm).padStart(2, "0") : ""}`;
      };

      // ------------------------------------------------ loading and drawing
      async function load(quiet) {
        const seq = ++loadSeq;
        try {
          const r = await ctx.call("settings_get", {});
          if (seq !== loadSeq) return;
          data = r;
        } catch (e) {
          if (!quiet) ctx.toast(e.message, "error");
        }
        render();
      }
      function render() {
        $("#st-title").textContent = T("插件设置", "Add-on settings");
        $("#st-lead").textContent = T("游戏里设置面板（F10）的所有设置，保存在游戏文件夹的 nimby3d.ini 里。这里改的设置在下次启动游戏时生效。",
          "Every setting of the panel in the game (F10), kept in nimby3d.ini in the game folder. What you change here takes effect the next time the game starts.");
        $("#st-show span").textContent = T("显示 nimby3d.ini", "Show nimby3d.ini");
        $("#st-reset-all span").textContent = T("全部恢复默认", "Reset all");
        $("#st-search").placeholder = T("搜索设置", "Search settings");
        const ok = !!(data && data.schema && data.game);
        $("#st-show").disabled = !data || !data.game;
        $("#st-reset-all").disabled = !ok || !shown().some(changed);

        const notes = [];
        const note = (tone, ic, text) => notes.push(`<div class="note" data-tone="${tone}">${icon(ic)}<span>${esc(text)}</span></div>`);
        if (data && !data.game) note("danger", "i-x-circle", T("没有找到游戏文件夹（在主页选择游戏文件夹）。设置保存在游戏文件夹的 nimby3d.ini 里。",
          "The game folder was not found (choose it on the Home page). The settings are kept in nimby3d.ini in the game folder."));
        if (data && data.schema_error) note("danger", "i-x-circle", data.schema_error.error === "no_schema"
          ? T(`缺少设置说明文件 settings_schema.json：${data.schema_error.params.path}`, `The settings description settings_schema.json is missing: ${data.schema_error.params.path}`)
          : T(`无法读取 settings_schema.json：${data.schema_error.params.error}`, `settings_schema.json could not be read: ${data.schema_error.params.error}`));
        if (data && data.running) note("warn", "i-alert", T("NIMBY Rails 正在运行。游戏只在启动时读 nimby3d.ini；而在游戏里的面板（F10）改任何设置时，它会用游戏里的值重写这个文件，这期间在这里做的改动会被覆盖。最好先退出游戏再改。",
          "NIMBY Rails is running. The game reads nimby3d.ini only when it starts, and when you change anything in its panel (F10) it writes the file again with the game's values, undoing changes made here meanwhile. Best quit the game first."));
        if (data && data.ini && !data.ini.exists && data.game) note("info", "i-info", T("游戏文件夹里还没有 nimby3d.ini：现在全部是默认值。改动任何设置时会创建它。",
          "There is no nimby3d.ini in the game folder yet: everything is at its default. It is made when you change a setting."));
        $("#st-notes").innerHTML = notes.join("");

        renderPages();
        renderMain();
        renderWhere();
      }
      function inPage(s, id) { return (s.pages || []).includes(Number(id)); }
      function matches(s) {
        if (!search) return true;
        const hay = [s.key, L(s.name), L(s.hint), s.name && s.name.en, s.name && s.name.zh].join(" ").toLowerCase();
        return search.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
      }
      function renderPages() {
        const box = $("#st-pages");
        if (!data || !data.schema) { box.innerHTML = ""; return; }
        const all = shown();
        const item = (id, label, n, ic) => `<button type="button" role="tab" data-page="${id}" aria-selected="${filter === String(id)}">${ic ? icon(ic) : ""}<span>${esc(label)}</span><span class="n">${n}</span></button>`;
        let html = item("all", T("全部", "All"), all.filter(matches).length, "i-layers");
        (data.schema.pages || []).forEach((p) => { html += item(p.id, L(p.name), all.filter((s) => inPage(s, p.id) && matches(s)).length); });
        html += item("changed", T("改过的", "Changed"), all.filter((s) => changed(s) && matches(s)).length, "i-edit");
        box.innerHTML = html;
      }
      function groups() {
        const all = shown().filter(matches);
        const pagesDef = (data.schema.pages || []);
        if (filter === "all" || filter === "changed") {
          const list = filter === "changed" ? all.filter(changed) : all;
          return pagesDef.map((p) => ({ page: p, items: list.filter((s) => Number((s.pages || [])[0]) === Number(p.id)) }))
            .concat([{ page: { id: "other", name: { en: "Other", zh: "其他" } }, items: list.filter((s) => !pagesDef.some((p) => Number((s.pages || [])[0]) === Number(p.id))) }])
            .filter((g) => g.items.length);
        }
        const p = pagesDef.find((x) => String(x.id) === filter);
        return p ? [{ page: p, items: all.filter((s) => inPage(s, p.id)) }] : [];
      }
      function renderMain() {
        const box = $("#st-main");
        if (!data) { box.innerHTML = `<div class="card pk-loading"><span class="spin"></span><span>${esc(T("正在读取…", "Loading…"))}</span></div>`; return; }
        if (!data.schema) { box.innerHTML = ""; return; }
        const gs = groups();
        if (!gs.length) {
          box.innerHTML = `<div class="card empty big">${icon(search ? "i-search" : "i-check-circle")}<div><b>${esc(search ? T("没有匹配的设置", "No setting matches") : T("全部是默认值", "Everything is at its default"))}</b></div></div>`;
          return;
        }
        box.innerHTML = gs.map((g, i) => `<section class="card st-sec" style="--i:${i + 2}">
            <div class="card-head"><h2>${esc(L(g.page.name))}</h2><span class="badge">${g.items.length}</span></div>
            <div class="st-rows">${g.items.map(row).join("")}</div></section>`).join("");
      }
      function row(s) {
        const v = value(s), ch = changed(s), off = !data.game;
        const restart = has(s, "restart") ? `<span class="badge" data-tone="warn" title="${esc(T("即使在游戏里的面板改，也要重启游戏才生效", "Takes effect only after the game restarts, even when changed in the game's panel"))}">${esc(T("需重启", "Restart"))}</span>` : "";
        let ctl = "";
        if (s.kind === "toggle") {
          ctl = `<button type="button" class="switch sm" role="switch" aria-checked="${v !== 0}" data-set="toggle" aria-label="${esc(L(s.name))}"${off ? " disabled" : ""}><span class="track"><span class="thumb"></span></span></button>`;
        } else if (s.kind === "slider") {
          ctl = `<input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${v}" data-set="slider" aria-label="${esc(L(s.name))}"${off ? " disabled" : ""}><output class="st-val">${esc(fmt(s, v))}</output>`;
        } else if (s.kind === "choice") {
          const cs = s.choices || [];
          const short = cs.length <= 4 && cs.every((c) => L(c.label).length <= 9);
          ctl = short
            ? `<div class="seg st-seg" role="radiogroup" aria-label="${esc(L(s.name))}">${cs.map((c) => `<button type="button" role="radio" data-set="choice" data-value="${c.value}" aria-pressed="${Number(c.value) === v}" aria-checked="${Number(c.value) === v}"${off ? " disabled" : ""}>${esc(L(c.label))}</button>`).join("")}</div>`
            : `<select data-set="select" aria-label="${esc(L(s.name))}"${off ? " disabled" : ""}>${cs.map((c) => `<option value="${c.value}"${Number(c.value) === v ? " selected" : ""}>${esc(L(c.label))}</option>`).join("")}</select>`;
        } else if (s.kind === "date") {
          const auto = v === 0, m = auto ? new Date().getMonth() + 1 : Math.floor(v / 100), d = auto ? new Date().getDate() : v % 100;
          ctl = `<label class="st-check"><input type="checkbox" data-set="date-auto"${auto ? " checked" : ""}${off ? " disabled" : ""}><span>${esc(T("用电脑的日期", "The computer's date"))}</span></label>` +
            `<span class="st-date"${auto ? " hidden" : ""}><select data-set="date-m" aria-label="${esc(T("月", "Month"))}"${off ? " disabled" : ""}>${Array.from({ length: 12 }, (_, i) => `<option value="${i + 1}"${i + 1 === m ? " selected" : ""}>${esc(T(`${i + 1} 月`, new Date(2001, i, 1).toLocaleString("en", { month: "short" })))}</option>`).join("")}</select>` +
            `<select data-set="date-d" aria-label="${esc(T("日", "Day"))}"${off ? " disabled" : ""}>${Array.from({ length: DAYS[m - 1] }, (_, i) => `<option value="${i + 1}"${i + 1 === d ? " selected" : ""}>${esc(T(`${i + 1} 日`, String(i + 1)))}</option>`).join("")}</select></span>`;
        } else if (s.kind === "zone") {
          const auto = v === -99;
          const cur = auto ? Math.round((-new Date().getTimezoneOffset() / 60) * 2) / 2 : v;
          const opts = [];
          for (let h = Number(s.min ?? -12); h <= Number(s.max ?? 14) + 1e-9; h += Number(s.step) || 0.5) opts.push(Math.round(h * 2) / 2);
          ctl = `<label class="st-check"><input type="checkbox" data-set="zone-auto"${auto ? " checked" : ""}${off ? " disabled" : ""}><span>${esc(T("自动：按经度（含夏令时）", "Auto: by the longitude (with summer time)"))}</span></label>` +
            `<select data-set="zone" aria-label="${esc(L(s.name))}"${auto ? " hidden" : ""}${off ? " disabled" : ""}>${opts.map((h) => `<option value="${h}"${h === cur ? " selected" : ""}>${esc(zoneText(h))}</option>`).join("")}</select>`;
        }
        const hint = L(s.hint);
        return `<div class="st-row${ch ? " changed" : ""}" data-key="${esc(s.key)}">
          <div class="st-text"><div class="st-name"><span>${esc(L(s.name))}</span>${restart}</div>${hint ? `<div class="st-hint">${esc(hint)}</div>` : ""}<div class="st-key mono">${esc(s.key)}</div></div>
          <div class="st-ctl">${ctl}</div>
          <button type="button" class="icon-btn st-reset" data-reset title="${esc(T(`恢复默认（${defaultText(s)}）`, `Back to the default (${defaultText(s)})`))}" aria-label="${esc(T("恢复默认", "Back to the default"))}"${ch && !off ? "" : " hidden"}>${icon("i-undo")}</button>
        </div>`;
      }
      function defaultText(s) {
        const d = Number(s.default);
        if (s.kind === "toggle") return d ? T("开", "on") : T("关", "off");
        if (s.kind === "choice") { const c = (s.choices || []).find((x) => Number(x.value) === d); return c ? L(c.label) : String(d); }
        if (s.kind === "date") return d === 0 ? T("电脑的日期", "the computer's date") : `${Math.floor(d / 100)}-${d % 100}`;
        if (s.kind === "zone") return d === -99 ? T("自动", "auto") : zoneText(d);
        return fmt(s, d);
      }
      function renderWhere() {
        const box = $("#st-where");
        const files = (data && data.files) || [];
        const about = {
          "nimby3d.ini": [T("插件的设置：这一页和游戏里的面板（F10）都写它。", "The add-on's settings: this page and the panel in the game (F10) both write it."), "i-sliders"],
          "nimby3d_stations.txt": [T("单个车站的设置（地基、抬高、天桥），在游戏里设：F10 →“车站”页，对着视野中间的车站。", "Settings of single stations (foundation, raise, footbridge), made in the game: F10 → Stations, for the station in the middle of the view."), "i-map-pin"],
          "nimby3d_probe.log": [T("插件的日志（主页“活动”→“插件日志”也能看）。", "The add-on's log (also on the Home page: Activity → Add-on log)."), "i-terminal"],
          "ReShade.log": [T("ReShade 自己的日志。", "ReShade's own log."), "i-terminal"],
          "ReShade.ini": [T("ReShade 自己的设置（它的菜单：Shift+F2）。", "ReShade's own settings (its menu: Shift+F2)."), "i-file"],
          shaderpacks: [T("光影包（在“光影包”页管理）。", "The shader packs (managed on the Shader packs page)."), "i-sparkles"],
          state: [T("这个程序自己的设置，以及给每个光影包记住的选项。", "This program's own settings, and the options remembered for each shader pack."), "i-database"],
        };
        const nameOf = (f) => (f.id === "shaderpacks" ? T("光影包文件夹", "Shader packs folder") : f.id === "state" ? T("Nimby3D 的设置文件夹", "Nimby3D's own folder") : f.id);
        box.innerHTML = `<div class="card-head"><div class="card-icon">${icon("i-folder")}</div><h2>${esc(T("文件在哪里", "Where things are"))}</h2></div>
          <div class="st-files">${files.map((f) => {
            const [text, ic] = about[f.id] || ["", "i-file"];
            const extra = [];
            if (f.exists && f.size !== undefined) extra.push(U.bytes(f.size));
            if (f.id === "nimby3d_stations.txt" && f.exists) extra.push(T(`${f.stations || 0} 个车站单独设置`, `${f.stations || 0} stations set on their own`));
            if (!f.exists) extra.push(T("还没有", "not there yet"));
            return `<div class="st-file${f.exists ? "" : " missing"}">
              <div class="st-file-ic">${icon(ic)}</div>
              <div class="st-file-main"><div class="st-file-name"><b>${esc(nameOf(f))}</b><span class="faint">${esc(extra.join(" · "))}</span></div><div class="st-file-about">${esc(text)}</div><div class="mono st-file-path" title="${esc(f.path || "")}">${esc(f.path || "—")}</div></div>
              <button type="button" class="btn btn-sm btn-ghost" data-open="${esc(f.id)}"${f.path ? "" : " disabled"}>${icon("i-folder-open")}<span>${esc(f.exists ? T("显示", "Show") : T("打开文件夹", "Open folder"))}</span></button>
            </div>`;
          }).join("")}</div>
          ${data && (data.unknown_keys || []).length ? `<div class="note" data-tone="info">${icon("i-info")}<span>${esc(T(`nimby3d.ini 里还有这一页不显示的项（原样保留）：${data.unknown_keys.join(", ")}`, `nimby3d.ini also holds keys this page does not show (kept as they are): ${data.unknown_keys.join(", ")}`))}</span></div>` : ""}`;
      }

      // ------------------------------------------------ changing
      function refreshRow(key) {
        const s = shown().find((x) => x.key === key);
        const el = root.querySelector(`.st-row[data-key="${CSS.escape(key)}"]`);
        if (s && el) {
          const tmp = document.createElement("div");
          tmp.innerHTML = row(s);
          el.replaceWith(tmp.firstElementChild);
        }
        renderPages();
        $("#st-reset-all").disabled = !(data && data.schema && data.game) || !shown().some(changed);
      }
      async function write(changes, focusKey) {
        const before = Object.assign({}, data.values);
        Object.entries(changes).forEach(([k, v]) => {
          const s = shown().find((x) => x.key === k);
          data.values[k] = v === null ? Number(s.default) : Number(v);
        });
        Object.keys(changes).forEach(refreshRow);
        try {
          await ctx.call("settings_set", { changes });
          const r = await ctx.call("settings_get", {});
          data = r;
          Object.keys(changes).forEach(refreshRow);
          renderWhere();
        } catch (e) {
          data.values = before;
          Object.keys(changes).forEach(refreshRow);
          ctx.toast(e.message, "error");
        }
        if (focusKey) {
          const el = root.querySelector(`.st-row[data-key="${CSS.escape(focusKey)}"] [data-set]`);
          if (el && document.activeElement === document.body) el.focus();
        }
      }
      const main = $("#st-main");
      main.addEventListener("click", (ev) => {
        const t1 = ev.target, r = t1.closest(".st-row");
        if (!r || !data) return;
        const key = r.dataset.key;
        if (t1.closest("[data-reset]")) return write({ [key]: null });
        const sw = t1.closest('[data-set="toggle"]');
        if (sw && !sw.disabled) return write({ [key]: sw.getAttribute("aria-checked") === "true" ? 0 : 1 }, key);
        const ch = t1.closest('[data-set="choice"]');
        if (ch && !ch.disabled) return write({ [key]: Number(ch.dataset.value) }, key);
      });
      main.addEventListener("input", (ev) => {
        const t1 = ev.target;
        if (t1.dataset.set !== "slider") return;
        const s = shown().find((x) => x.key === t1.closest(".st-row").dataset.key);
        const out = t1.parentElement.querySelector(".st-val");
        if (s && out) out.textContent = fmt(s, Number(t1.value));
      });
      main.addEventListener("change", (ev) => {
        const t1 = ev.target, r = t1.closest(".st-row");
        if (!r) return;
        const key = r.dataset.key, set = t1.dataset.set;
        if (set === "slider" || set === "select" || set === "zone") return write({ [key]: Number(t1.value) }, key);
        if (set === "date-auto") {
          const now = new Date();
          return write({ [key]: t1.checked ? 0 : (now.getMonth() + 1) * 100 + now.getDate() }, key);
        }
        if (set === "zone-auto") return write({ [key]: t1.checked ? -99 : Math.round((-new Date().getTimezoneOffset() / 60) * 2) / 2 }, key);
        if (set === "date-m" || set === "date-d") {
          const m = Number(r.querySelector('[data-set="date-m"]').value);
          const d = Math.min(Number(r.querySelector('[data-set="date-d"]').value), DAYS[m - 1]);
          return write({ [key]: m * 100 + d }, key);
        }
      });
      $("#st-pages").addEventListener("click", (ev) => {
        const b = ev.target.closest("[data-page]");
        if (!b) return;
        filter = b.dataset.page;
        renderPages();
        renderMain();
      });
      $("#st-search").addEventListener("input", (ev) => {
        search = ev.target.value.trim();
        renderPages();
        renderMain();
      });
      $("#st-show").addEventListener("click", () => ctx.call("open_game_file", { name: "nimby3d.ini" }).catch((e) => ctx.toast(e.message, "error")));
      $("#st-reset-all").addEventListener("click", async () => {
        const n = shown().filter(changed).length;
        const yes = await ctx.confirm({ title: T("把全部设置恢复默认？", "Put every setting back to its default?"),
          body: T(`改过的 ${n} 项会从 nimby3d.ini 里去掉；文件里的其他内容（注释、光影包的选择和选项）保持不变。`, `The ${n} changed settings are taken out of nimby3d.ini; everything else in the file (comments, the shader pack and its options) stays.`),
          ok: T("全部恢复默认", "Reset all"), danger: true });
        if (!yes) return;
        try {
          await ctx.call("settings_reset_all", {});
          ctx.toast(T("已全部恢复默认", "Everything is back at its default"), "ok");
        } catch (e) { ctx.toast(e.message, "error"); }
        load(true);
      });
      $("#st-where").addEventListener("click", (ev) => {
        const b = ev.target.closest("[data-open]");
        if (b) ctx.call("open_game_file", { name: b.dataset.open }).catch((e) => ctx.toast(e.message, "error"));
      });

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
