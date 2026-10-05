/* Nimby3D manager page. Talks to manager/app.py through pywebview's js_api (window) or
   POST /api/<name> with the session token (browser mode). No network beyond that. */
"use strict";
(() => {
  // ------------------------------------------------------------------ words
  const I18N = {
    zh: {
      "app.tagline": "NIMBY Rails 3D 视图 · 安装与管理",
      "nav.label": "页面", "nav.home": "主页", "nav.guide": "使用教程", "nav.about": "关于作者", "nav.packs": "光影包", "nav.settings": "插件设置",
      "act.addon_settings": "插件设置", "act.manage_packs": "管理光影包",
      "packs.now_on": "正在使用：{name}", "packs.now_off": "光影包已关闭", "packs.now_missing": "选中的光影包不在文件夹里：{name}",
      "cf.ok": "确定", "cf.cancel": "取消",
      "skin.button": "外观", "skin.title": "外观", "skin.lead": "选一套外观：配色和 Nimby3D酱的立绘。浅色 / 深色仍可以用旁边的按钮切换。",
      "skin.note": "可以给每套外观换上你自己的图（PNG、WebP 或 JPG，最大 8 MB，比如约稿的立绘）。图片会复制到 Nimby3D 自己的设置文件夹里。",
      "skin.close": "完成", "skin.replace": "换图…", "skin.restore": "恢复默认图", "skin.own": "你的图", "skin.pick_title": "选择一张图（PNG、WebP 或 JPG）", "skin.images": "图片",
      "skin.classic": "经典", "skin.afternoon": "午后", "skin.sleepy": "困困", "skin.nightshift": "夜班",
      "skin.classic_sub": "原来的样子，没有人物", "skin.afternoon_sub": "奶油与晴空", "skin.sleepy_sub": "薰衣草与薄荷", "skin.nightshift_sub": "深夜与霓虹",
      "skin.replaced": "已换上你的图", "skin.restored": "已恢复默认图",
      "about.mascot_credit": "Nimby3D酱 立绘：为 Nimby3D 用 OpenAI 图像生成制作（AI 生成）。可以在“外观”里换成你自己的图。",
      "err.bad_skin": "没有这套外观：{skin}", "err.bad_picture": "{name} 不是 PNG、WebP 或 JPG 图片。", "err.picture_too_big": "{name} 超过 {mb} MB。",
      "err.picture_size": "{name} 是 {w}×{h} 像素：每边要在 {lo} 到 {hi} 之间。",
      "log.pack_imported": "已添加光影包：{name}", "log.pack_removed": "已把光影包移到回收站：{name}", "log.pack_chosen": "光影包：{name}（nimby3d.ini）",
      "log.packs_on": "光影包已打开（nimby3d.ini）", "log.packs_off": "光影包已关闭（nimby3d.ini）", "log.pack_options": "光影包选项：{name}，设置了 {n} 项",
      "log.settings_written": "nimby3d.ini：{keys}", "log.settings_reset": "nimby3d.ini：{n} 项设置恢复默认",
      "err.pack_exists": "已经有一个叫 {name} 的光影包。", "err.not_a_pack": "{name} 不是光影包（里面没有带着色器程序的 shaders 文件夹）。",
      "err.not_a_zip": "{name} 不是 ZIP 文件。", "err.pack_missing": "找不到：{path}", "err.bad_pack": "不是光影包的名字：{name}",
      "err.already_there": "{name} 已经在光影包文件夹里了。", "err.recycle_failed": "无法把 {name} 移到回收站。",
      "err.packinfo_missing": "缺少读取光影包的工具 n3d_packinfo.exe（{path}）。", "err.packinfo_failed": "读取光影包失败：{error}",
      "err.bad_profile": "这个光影包没有这个预设：{name}", "err.bad_option": "这个光影包不接受：{options}", "err.no_packs": "光影包文件夹里还没有光影包。",
      "err.no_schema": "缺少设置说明文件 settings_schema.json（{path}）。", "err.bad_schema": "无法读取 settings_schema.json：{error}",
      "err.bad_setting": "{key} 不是 nimby3d.ini 里的设置。", "err.bad_value": "{key}：{value} 不是一个数。", "err.bad_file": "不是插件的文件：{name}",
      "err.no_train_editor": "没有安装列车编辑器。", "err.train_editor_broken": "列车编辑器无法载入：{error}", "err.no_such_call": "没有这个调用：{name}",
      "err.bad_request": "请求无效：{message}",
      "guide.toc": "本页内容", "guide.title": "使用教程", "guide.lead": "从一键安装到游戏里的每个按键：使用 Nimby3D 需要知道的都在这里。", "guide.or": "或",
      "about.title": "关于作者", "about.lead": "一个想在游戏窗口里看到自己线路 3D 样子的小愿望。", "about.alt": "adaihappyjan 的头像",
      "about.callme": "叫我阿达就好啦！", "about.hello": "各位玩 NIMBY Rails 的大家好呀～",
      "about.p1": "这里是 adaihappyjan，叫我阿达就好啦！(≧▽≦)/",
      "about.p2": "Nimby3D 的起点很简单：我特别想看看自己在 NIMBY Rails 里修的线路“立起来”是什么样子，而且就在游戏窗口里看，不用切到别的程序。",
      "about.p3": "于是就有了这个插件：地形、高架和隧道、车站和列车，一点一点地从地图上立了起来！ヽ(✿ﾟ▽ﾟ)ノ",
      "about.p4": "它和 NIMBY Timetable Toolkit（时刻表工具箱）一起开发，同样免费、开放。以后除了继续做我想到的新东西，也会努力把大家的反馈和点子加进去！(๑•̀ㅂ•́)و✧",
      "about.p5": "真的非常感谢每一位愿意试试 Nimby3D、给我反馈的朋友！要是你的线路也能在 3D 里跑起来，我会超级开心～",
      "about.credit_pre": "头像绘制：", "about.credit_artist": "PoLa（pixiv）", "about.credit_mid": " · 作品", "about.credit_work": "「水着ルビー」",
      "about.thanks": "谢谢大家！(づ｡◕‿‿◕｡)づ ♡", "about.repo": "在 GitHub 上找到我", "about.toolkit": "NIMBY Timetable Toolkit",
      "act.install_play": "安装并开始游戏", "act.play": "开始游戏", "act.update_play": "更新并开始游戏", "act.enable_play": "启用并开始游戏",
      "act.repair_play": "修复并开始游戏", "act.running": "游戏运行中", "act.get_game": "在 Steam 获取 NIMBY Rails", "act.check_again": "重新检测",
      "op.play": "开始游戏", "done.launched": "正在启动 NIMBY Rails…", "done.launched_body": "地图会以 3D 显示。按 F8 可在 2D 和 3D 之间切换。",
      "done.install_launched": "安装完成，正在启动 NIMBY Rails…", "done.enable_launched": "已启用，正在启动 NIMBY Rails…",
      "err.already_running": "NIMBY Rails 已经在运行。", "err.bad_link": "这个链接不能打开。", "log.launched": "正在启动 NIMBY Rails",
      "hero.no_game.steam": "Nimby3D 需要 Steam 上的 NIMBY Rails。在 Steam 安装游戏后点“重新检测”；如果游戏装在 Steam 没有列出的文件夹里，就选择那个文件夹。",
      "pill.no_game": "未找到游戏", "pill.not_installed": "未安装", "pill.installed": "已启用", "pill.disabled": "已停用",
      "pill.update": "有更新", "pill.incomplete": "安装不完整", "pill.running": "游戏运行中", "pill.loading": "正在读取…",
      "lang.label": "语言", "theme.system": "主题：跟随系统", "theme.light": "主题：浅色", "theme.dark": "主题：深色",
      "eyebrow": "NIMBY Rails · ReShade 插件",
      "hero.no_game.title": "没有找到<g> NIMBY Rails</g>",
      "hero.no_game.sub": "在 Steam 库里没有找到游戏。请选择游戏文件夹（里面有 NimbyRails.exe）。",
      "hero.no_game.sub_dir": "{dir} 里没有 NimbyRails.exe。请选择游戏文件夹。",
      "hero.not_installed.title": "把地图变成 <g>3D</g>",
      "hero.not_installed.sub": "一键安装 ReShade 和 Nimby3D 插件，从你最新的存档导出车站、轨道和地形，然后启动游戏。",
      "hero.installed.title": "Nimby3D <g>已启用</g>",
      "hero.installed.sub": "点“开始游戏”，地图就会以 3D 显示。线路有变化时点“更新存档数据”，或打开自动同步。",
      "hero.installed_running.sub": "游戏正在运行。存档数据可以随时更新，插件几秒内就会读到。",
      "hero.staged.sub": "新版本已经放好；游戏还在使用启动时的版本，重启游戏后生效。",
      "hero.disabled.title": "Nimby3D <g>已停用</g>",
      "hero.disabled.sub": "文件都还在，但游戏启动时不会加载 ReShade 和插件。随时可以重新启用。",
      "hero.update.title": "有<g>新版本</g>可用",
      "hero.update.sub": "已安装 {a}，可安装 {b}。更新会保留你的设置和人物模型。",
      "hero.incomplete.title": "安装<g>不完整</g>",
      "hero.incomplete.sub": "有文件缺失，或者上次安装中断了。重新安装即可修复。",
      "act.install": "安装并启用", "act.update": "更新", "act.repair": "修复安装", "act.enable": "启用", "act.disable": "停用",
      "act.refresh": "更新存档数据", "act.watch": "自动同步存档", "act.remove": "卸载并删除", "act.choose_game": "选择游戏文件夹…",
      "act.open_folder": "打开文件夹", "act.change": "更改…", "act.autodetect": "自动检测", "act.choose_save": "选择存档…",
      "act.use_newest": "使用最新存档", "act.choose_avatar": "选择 VRM 模型…", "act.clear_avatar": "移除",
      "busy.install": "正在安装…", "busy.refresh": "正在更新存档数据…", "busy.enable": "正在启用…", "busy.disable": "正在停用…",
      "busy.remove": "正在卸载…", "busy.avatar": "正在复制人物模型…", "busy.clear_avatar": "正在移除人物模型…", "busy.sync": "正在同步存档…",
      "op.install": "安装", "op.refresh": "更新存档数据", "op.enable": "启用", "op.disable": "停用", "op.remove": "卸载并删除",
      "op.avatar": "设置人物模型", "op.clear_avatar": "移除人物模型", "op.sync": "自动同步",
      "note.running": "游戏正在运行：现在安装或更新也可以，但要到下次启动游戏才生效；停用和卸载需要先关闭游戏。",
      "note.staged": "新版本已放好，重启游戏后生效。旧版本的副本会在游戏关闭后自动清理。",
      "note.foreign_dxgi": "游戏文件夹里有一个不是 Nimby3D 安装的 dxgi.dll（可能是你自己的 ReShade）。Nimby3D 不会覆盖或删除它。",
      "note.other_proxies": "游戏文件夹里还有其他注入用的 DLL：{names}。它们可能和 ReShade 冲突。",
      "note.no_build": "没有找到可以安装的文件：{what}",
      "note.no_saves": "存档文件夹里还没有存档：{dir}",
      "note.stale": "有比已导出数据更新的存档。点“更新存档数据”同步。",
      "note.watching": "自动同步已开启：游戏每次存档（包括自动存档）后几秒内更新数据。关闭 Nimby3D 时停止。",
      "note.watch_elsewhere": "另一个程序（命令行 watch）正在同步存档。",
      "note.saves_safe": "Nimby3D 只读取存档，从不修改；只会删除它自己安装的文件。",
      "card.game": "游戏", "card.addon": "插件", "card.data": "存档数据", "card.avatar": "人物模型", "card.packs": "光影包",
      "game.folder": "文件夹", "game.found": "来源",
      "how.steam": "在 Steam 库中找到", "how.manual": "你选择的文件夹", "how.env": "环境变量 N3D_GAME_DIR", "how.default": "默认位置", "how.argument": "命令行参数",
      "game.running": "运行中", "game.closed": "未运行", "game.missing": "未找到", "game.saves": "存档", "game.saves_count": "{n} 个存档", "game.saves_one": "1 个存档",
      "addon.installed": "已安装", "addon.available": "可安装", "addon.files": "文件", "addon.no_build": "没有可安装的版本", "addon.off": "已停用",
      "src.payload": "随附", "src.dev": "开发版本", "src.env": "环境变量", "src.argument": "参数",
      "reshade.ours": "由 Nimby3D 安装", "reshade.ours_off": "由 Nimby3D 安装 · 已停用", "reshade.foreign": "他人的 dxgi.dll", "reshade.none": "未安装", "reshade.update": "有新版本",
      "files.ok": "{n} 个文件完好", "files.problems": "{missing} 个缺失 · {modified} 个已改动", "files.disabled": "{n} 个已停用", "files.none": "没有文件",
      "files.show": "查看文件", "files.hide": "收起",
      "file.ok": "完好", "file.present": "存在", "file.missing": "缺失", "file.modified": "已改动", "file.disabled": "已停用", "file.unreadable": "无法读取",
      "data.from": "来自存档", "data.source": "使用", "data.none": "尚未导出", "data.exported": "{when}导出", "data.auto": "自动：最新存档",
      "data.auto_name": "自动：最新存档 · {name}", "data.pinned": "固定：{name}", "data.stale": "有更新的存档", "data.stations": "车站",
      "data.nodes": "轨道节点", "data.platforms": "站台", "data.signals": "信号机", "data.no_saves": "没有存档",
      "avatar.none_title": "未设置人物模型", "avatar.none": "第三人称视角里看不到自己的人物。选择一个 VRM 模型即可。",
      "avatar.cleared": "已移除；安装时不会自动放回。", "avatar.meta": "{size} · 下次启动游戏时载入", "avatar.hand": "不是 Nimby3D 放进去的",
      "avatar.note": "VRM 模型的版权归原作者所有。Nimby3D 只把它复制到你自己的游戏文件夹，不会分发。",
      "packs.count": "{n} 个", "packs.none": "在 %APPDATA%\\.minecraft\\shaderpacks 里没有找到光影包。",
      "packs.hint": "在“光影包”页选择光影包并调整它的选项；也可以在游戏里按 F10 →“画面”选择（实验功能，仅 NVIDIA，默认关闭）。",
      "activity.title": "活动", "tab.activity": "记录", "tab.addon": "插件日志", "tab.reshade": "ReShade 日志",
      "log.empty": "还没有活动。安装、更新或同步时的每一步都会显示在这里。", "log.missing": "还没有这个日志文件（游戏启动后才会写入）。",
      "log.meta": "{path} · {size} · 最后 {n} 行", "log.refresh": "刷新", "log.open": "在资源管理器中显示",
      "log.start": "▶ {op}", "log.ok": "✓ {op}：完成", "log.fail": "✕ {op}：{msg}",
      "step.prepare": "准备", "step.export_data": "读取存档", "step.export_tracks": "导出轨道", "step.export_dem": "导出地形", "step.reshade": "ReShade",
      "step.reshade_ini": "ReShade 设置", "step.addon": "插件", "step.data": "放入存档数据", "step.shaders": "着色器缓存", "step.landcover": "地表覆盖",
      "step.ambient": "车辆与船只模型", "step.textures": "表面纹理", "step.avatar": "人物模型", "step.remove": "删除文件", "step.done": "完成",
      "done.install": "安装完成", "done.install_body": "下次启动游戏时生效。", "done.install_running": "已安装，重启游戏后生效",
      "done.install_running_body": "游戏会继续使用启动时的版本。", "done.refresh": "存档数据已更新", "done.refresh_body": "{stations} 个车站 · {nodes} 个轨道节点",
      "done.disable": "已停用", "done.disable_body": "游戏下次启动时不会加载 ReShade 和插件。", "done.enable": "已启用", "done.enable_running": "已启用，下次启动游戏时生效",
      "done.remove": "已卸载", "done.remove_body": "删除了 {n} 个文件或文件夹。", "done.remove_partial": "部分文件没能删除",
      "done.avatar": "人物模型已设置", "done.clear_avatar": "人物模型已移除", "done.save_pinned": "已改用存档 {name}", "done.save_auto": "已改为使用最新存档",
      "done.game_set": "游戏文件夹已更改", "done.game_auto": "已切换为自动检测",
      "watch.on": "自动同步已开启", "watch.off": "自动同步已关闭", "watch.synced": "已同步 {save}", "watch.stopped": "自动同步已停止",
      "op.failed": "{op}失败",
      "err.game_running": "NIMBY Rails 正在运行。请先退出游戏。",
      "err.foreign_dxgi": "游戏文件夹里已有一个不是 Nimby3D 安装的 dxgi.dll。为了不破坏它，没有安装。",
      "err.game_not_found": "在 {dir} 没有找到 NimbyRails.exe。",
      "err.game_not_found_anywhere": "没有在任何 Steam 库里找到 NIMBY Rails。请手动选择游戏文件夹。",
      "err.missing_source": "找不到要安装的文件：{path}", "err.no_saves": "{dir} 里没有存档。", "err.save_missing": "找不到存档：{path}",
      "err.not_installed": "Nimby3D 还没有安装。", "err.export_failed": "无法读取存档 {name}：{error}",
      "err.in_use": "{name} 正被占用。请关闭游戏后再试。", "err.avatar_bad": "{name} 不是 VRM 模型。", "err.avatar_missing": "找不到文件：{path}",
      "err.avatar_not_ours": "这个 nimby3d_avatar.vrm 不是 Nimby3D 放进去的，请手动删除。", "err.busy": "正在进行另一项操作，请稍候。",
      "err.bad_folder": "这个文件夹里没有 NimbyRails.exe。", "err.bad_save": "{name} 不是 NIMBY Rails 存档（.nimbyrails5）。",
      "err.no_dialog": "无法打开文件选择窗口。", "err.watch_elsewhere": "另一个程序已经在同步存档（进程 {pid}）。",
      "err.unexpected": "出现意外错误：{message}", "err.offline": "与 Nimby3D 后台的连接断开了。", "err.token": "会话已失效，请重新打开 Nimby3D。",
      "rm.title": "卸载并删除 Nimby3D？", "rm.lead": "下面列出的文件会从游戏文件夹中删除。游戏本身的文件不会被动。",
      "rm.delete": "将删除", "rm.edit": "将修改", "rm.keep": "保留", "rm.total": "共 {n} 项 · {size}",
      "rm.purge": "同时删除插件的设置和学习到的数据（nimby3d.ini、nimby3d_units.txt、截图转储等）", "rm.saves": "存档不会被修改",
      "rm.blocked": "NIMBY Rails 正在运行。请先退出游戏再卸载。", "rm.cancel": "取消", "rm.confirm": "卸载并删除", "rm.nothing": "没有需要删除的文件。",
      "rm.loading": "正在列出文件…", "rm.modified": "已改动",
      "reason.reshade": "ReShade", "reason.reshade_generated": "ReShade 生成", "reason.addon": "插件", "reason.addon_log": "插件日志", "reason.aside": "旧版本副本",
      "reason.scratch": "临时文件", "reason.record": "安装记录", "reason.user_data": "设置 / 学习数据", "reason.not_ours": "不是 Nimby3D 安装的",
      "reason.no_record": "没有安装记录证明它属于 Nimby3D", "reason.in_use_by_other_reshade": "另一个 ReShade 在使用", "reason.strip_keys": "只移除 Nimby3D 添加的 {n} 项设置",
      "path.title": "游戏文件夹", "path.lead": "输入 NIMBY Rails 的安装文件夹（里面有 NimbyRails.exe）。", "path.ok": "使用这个文件夹",
      "foot.safe": "只读取存档 · 只删除自己安装的文件", "foot.browser": "浏览器模式",
      "rel.now": "刚刚", "rel.min": "{n} 分钟前", "rel.hour": "{n} 小时前", "rel.day": "{n} 天前",
      "fatal.title": "无法连接到 Nimby3D 后台", "fatal.body": "请关闭这个页面，重新运行 Nimby3D.cmd。",
      // lines of tools/install.py (by their key)
      "log.exporting": "读取存档 {save}", "log.put": "{name}：{result}",
      "log.no_dem": "游戏文件夹里没有地形文件（resources/maps/dem400.pmtiles），nimby3d_dem.bin 保持不变",
      "log.installed": "已安装到 {game}",
      "log.data_from": "{save} 的数据：{stations} 个车站，{nodes} 个轨道节点（{special}/{all} 在高架或隧道），{platforms} 个站台，{signals} 个信号机，{dem} 块地形",
      "log.running_next_start": "游戏正在运行，会继续使用启动时的版本。重启游戏后使用新版本。",
      "log.refreshed": "{time} {save} 的数据：{stations} 个车站，{nodes} 个轨道节点，{platforms} 个站台，{signals} 个信号机",
      "log.watching": "正在监视 {dir} 里的存档", "log.watch_failed": "暂时无法读取 {name}（{error}），稍后重试",
      "log.disabled_file": "{name} → {to}", "log.dxgi_not_ours_kept": "dxgi.dll 不是本工具安装的：保持不变（只停用插件）",
      "log.disabled": "已停用：游戏启动时不加载 ReShade 和插件，直到重新启用", "log.enable_foreign_dxgi": "已有他人的 dxgi.dll：Nimby3D 的 ReShade 保持关闭",
      "log.enabled_file": "{from_} → {name}", "log.enabled": "已启用", "log.enabled_running": "已启用：下次启动游戏时生效",
      "log.avatar_replacing": "替换一个不是本工具放进去的 nimby3d_avatar.vrm", "log.avatar_set": "人物模型：{name}（{size} MB）",
      "log.avatar_set_running": "人物模型：{name}（{size} MB），下次启动游戏时载入", "log.avatar_cleared": "已移除人物模型",
      "log.kept_file": "保留 {name}（不是本工具安装的）", "log.removed": "已删除：{names}", "log.remove_failed": "无法删除：{names}",
      "log.ini_stripped": "ReShade.ini：移除了本工具添加的设置，保留你的设置",
    },
    en: {
      "app.tagline": "3D view for NIMBY Rails · install & manage",
      "nav.label": "Pages", "nav.home": "Home", "nav.guide": "Guide", "nav.about": "About", "nav.packs": "Shader packs", "nav.settings": "Add-on settings",
      "act.addon_settings": "Add-on settings", "act.manage_packs": "Manage shader packs",
      "packs.now_on": "In use: {name}", "packs.now_off": "Shader packs are off", "packs.now_missing": "The chosen pack is not in the folder: {name}",
      "cf.ok": "OK", "cf.cancel": "Cancel",
      "skin.button": "Appearance", "skin.title": "Appearance", "skin.lead": "Pick a look: colours and a picture of Nimby3D-chan. Light or dark still switches with the button beside it.",
      "skin.note": "Each look can take a picture of your own (PNG, WebP or JPG up to 8 MB, a commissioned drawing for instance). It is copied into Nimby3D's own settings folder.",
      "skin.close": "Done", "skin.replace": "Replace picture…", "skin.restore": "Restore default", "skin.own": "your picture", "skin.pick_title": "Choose a picture (PNG, WebP or JPG)", "skin.images": "Pictures",
      "skin.classic": "Classic", "skin.afternoon": "Lazy Afternoon", "skin.sleepy": "Sleepy", "skin.nightshift": "Night Shift",
      "skin.classic_sub": "The original look, no character", "skin.afternoon_sub": "Soft cream and sky", "skin.sleepy_sub": "Pastel lavender and mint", "skin.nightshift_sub": "Navy night, neon glow",
      "skin.replaced": "Your picture is in place", "skin.restored": "Back to the default picture",
      "about.mascot_credit": "Nimby3D-chan (Nimby3D酱) artwork: generated with OpenAI image generation for Nimby3D (AI-generated). Appearance lets you put in your own.",
      "err.bad_skin": "No such look: {skin}", "err.bad_picture": "{name} is not a PNG, WebP or JPG picture.", "err.picture_too_big": "{name} is larger than {mb} MB.",
      "err.picture_size": "{name} is {w}×{h} pixels: each side must be {lo} to {hi}.",
      "err.pack_exists": "There is already a pack named {name}.", "err.not_a_pack": "{name} is not a shader pack (there is no shaders folder with programs in it).",
      "err.not_a_zip": "{name} is not a ZIP file.", "err.pack_missing": "Not found: {path}", "err.bad_pack": "Not a pack name: {name}",
      "err.already_there": "{name} is already in the shader packs folder.", "err.recycle_failed": "{name} could not be moved to the Recycle Bin.",
      "err.packinfo_missing": "The pack reader n3d_packinfo.exe is missing ({path}).", "err.packinfo_failed": "The pack could not be read: {error}",
      "err.bad_profile": "The pack has no profile {name}.", "err.bad_option": "The pack does not take: {options}", "err.no_packs": "There are no shader packs in the folder yet.",
      "err.no_schema": "The settings description settings_schema.json is missing ({path}).", "err.bad_schema": "settings_schema.json could not be read: {error}",
      "err.bad_setting": "{key} is not a setting of nimby3d.ini.", "err.bad_value": "{key}: {value} is not a number.", "err.bad_file": "Not one of the add-on's files: {name}",
      "err.no_train_editor": "The train editor is not installed.", "err.train_editor_broken": "The train editor could not be loaded: {error}", "err.no_such_call": "No such call: {name}",
      "err.bad_request": "Bad request: {message}",
      "guide.toc": "On this page", "guide.title": "Guide", "guide.lead": "From the one-click install to every key in the game: everything you need to use Nimby3D.", "guide.or": "or",
      "about.title": "About the author", "about.lead": "A small wish to see my own network in 3D, right in the game window.", "about.alt": "Portrait of adaihappyjan",
      "about.callme": "You can call me Adai!", "about.hello": "Hello, fellow NIMBY Rails players～",
      "about.p1": "I'm adaihappyjan; you can call me Adai!(≧▽≦)/",
      "about.p2": "Nimby3D started from a simple wish: I really wanted to see the network I built in NIMBY Rails stand up in 3D, right in the game window, without switching to another program.",
      "about.p3": "So this add-on happened: terrain, viaducts and tunnels, stations and trains, rising from the map bit by bit!ヽ(✿ﾟ▽ﾟ)ノ",
      "about.p4": "It is built alongside the NIMBY Timetable Toolkit and, like it, is free and open. Besides the new things I think of, I'll keep working your feedback and ideas into it!(๑•̀ㅂ•́)و✧",
      "about.p5": "A huge thank-you to everyone who gives Nimby3D a try and sends feedback! If your network comes alive in 3D too, I'll be super happy～",
      "about.credit_pre": "Portrait art: ", "about.credit_artist": "PoLa (pixiv)", "about.credit_mid": " · from ", "about.credit_work": "“水着ルビー”",
      "about.thanks": "Thank you!(づ｡◕‿‿◕｡)づ ♡", "about.repo": "Find me on GitHub", "about.toolkit": "NIMBY Timetable Toolkit",
      "act.install_play": "Install & Play", "act.play": "Play", "act.update_play": "Update & Play", "act.enable_play": "Enable & Play",
      "act.repair_play": "Repair & Play", "act.running": "Game running", "act.get_game": "Get NIMBY Rails on Steam", "act.check_again": "Check again",
      "op.play": "Play", "done.launched": "Starting NIMBY Rails…", "done.launched_body": "The map shows in 3D. F8 switches between 2D and 3D.",
      "done.install_launched": "Installed — starting NIMBY Rails…", "done.enable_launched": "Enabled — starting NIMBY Rails…",
      "err.already_running": "NIMBY Rails is already running.", "err.bad_link": "That link can't be opened.",
      "hero.no_game.steam": "Nimby3D needs NIMBY Rails from Steam. Install the game there, then click Check again. If it is installed in a folder Steam doesn't list, choose that folder.",
      "pill.no_game": "Game not found", "pill.not_installed": "Not installed", "pill.installed": "Enabled", "pill.disabled": "Disabled",
      "pill.update": "Update available", "pill.incomplete": "Incomplete", "pill.running": "Game running", "pill.loading": "Loading…",
      "lang.label": "Language", "theme.system": "Theme: follow system", "theme.light": "Theme: light", "theme.dark": "Theme: dark",
      "eyebrow": "NIMBY Rails · ReShade add-on",
      "hero.no_game.title": "<g>NIMBY Rails</g> not found",
      "hero.no_game.sub": "The game isn't in any Steam library. Choose the game folder (the one with NimbyRails.exe).",
      "hero.no_game.sub_dir": "There is no NimbyRails.exe in {dir}. Choose the game folder.",
      "hero.not_installed.title": "Turn the map into <g>3D</g>",
      "hero.not_installed.sub": "One click installs ReShade and the Nimby3D add-on, exports stations, track and terrain from your newest save, and starts the game.",
      "hero.installed.title": "Nimby3D is <g>on</g>",
      "hero.installed.sub": "Click Play and the map shows in 3D. Refresh the save data when your network changes, or turn on auto-sync.",
      "hero.installed_running.sub": "The game is running. Refresh the save data any time; the add-on picks it up within seconds.",
      "hero.staged.sub": "The new version is in place; the game keeps the one it started with until you restart it.",
      "hero.disabled.title": "Nimby3D is <g>off</g>",
      "hero.disabled.sub": "The files are kept, but the game starts without ReShade and the add-on. Turn it back on any time.",
      "hero.update.title": "An <g>update</g> is ready",
      "hero.update.sub": "Installed {a}, available {b}. Updating keeps your settings and player figure.",
      "hero.incomplete.title": "Installation <g>incomplete</g>",
      "hero.incomplete.sub": "Some files are missing or the last install was interrupted. Installing again repairs it.",
      "act.install": "Install & enable", "act.update": "Update", "act.repair": "Repair", "act.enable": "Enable", "act.disable": "Disable",
      "act.refresh": "Refresh save data", "act.watch": "Auto-sync saves", "act.remove": "Uninstall & delete", "act.choose_game": "Choose game folder…",
      "act.open_folder": "Open folder", "act.change": "Change…", "act.autodetect": "Auto-detect", "act.choose_save": "Choose save…",
      "act.use_newest": "Use newest save", "act.choose_avatar": "Choose VRM model…", "act.clear_avatar": "Remove",
      "busy.install": "Installing…", "busy.refresh": "Refreshing save data…", "busy.enable": "Enabling…", "busy.disable": "Disabling…",
      "busy.remove": "Uninstalling…", "busy.avatar": "Copying the figure…", "busy.clear_avatar": "Removing the figure…", "busy.sync": "Syncing save…",
      "op.install": "Install", "op.refresh": "Refresh save data", "op.enable": "Enable", "op.disable": "Disable", "op.remove": "Uninstall",
      "op.avatar": "Set player figure", "op.clear_avatar": "Remove player figure", "op.sync": "Auto-sync",
      "note.running": "The game is running: you can install or update now, but it takes effect the next time the game starts. Disabling and uninstalling need the game closed.",
      "note.staged": "The new version is in place and takes effect when you restart the game. Copies of the old one are cleaned up once the game is closed.",
      "note.foreign_dxgi": "The game folder has a dxgi.dll that Nimby3D didn't install (maybe your own ReShade). Nimby3D won't overwrite or delete it.",
      "note.other_proxies": "Other injector DLLs are in the game folder: {names}. They may conflict with ReShade.",
      "note.no_build": "A file to install was not found: {what}",
      "note.no_saves": "There are no saves yet in {dir}",
      "note.stale": "There is a newer save than the exported data. Refresh the save data to catch up.",
      "note.watching": "Auto-sync is on: the data is refreshed a few seconds after each save (autosaves too). It stops when Nimby3D closes.",
      "note.watch_elsewhere": "Another program (the command-line watch) is already syncing saves.",
      "note.saves_safe": "Nimby3D only reads your saves and never changes them; it deletes only files it installed.",
      "card.game": "Game", "card.addon": "Add-on", "card.data": "Save data", "card.avatar": "Player figure", "card.packs": "Shader packs",
      "game.folder": "Folder", "game.found": "Source",
      "how.steam": "Found in your Steam library", "how.manual": "Folder you chose", "how.env": "N3D_GAME_DIR variable", "how.default": "Default location", "how.argument": "Command-line argument",
      "game.running": "Running", "game.closed": "Not running", "game.missing": "Not found", "game.saves": "Saves", "game.saves_count": "{n} saves", "game.saves_one": "1 save",
      "addon.installed": "Installed", "addon.available": "Available", "addon.files": "Files", "addon.no_build": "No build available", "addon.off": "off",
      "src.payload": "bundled", "src.dev": "dev build", "src.env": "env variable", "src.argument": "argument",
      "reshade.ours": "Installed by Nimby3D", "reshade.ours_off": "Installed by Nimby3D · off", "reshade.foreign": "Someone else's dxgi.dll", "reshade.none": "Not installed", "reshade.update": "update ready",
      "files.ok": "{n} files OK", "files.problems": "{missing} missing · {modified} changed", "files.disabled": "{n} disabled", "files.none": "No files",
      "files.show": "Show files", "files.hide": "Hide",
      "file.ok": "OK", "file.present": "Present", "file.missing": "Missing", "file.modified": "Changed", "file.disabled": "Disabled", "file.unreadable": "Unreadable",
      "data.from": "From save", "data.source": "Using", "data.none": "Not exported yet", "data.exported": "exported {when}", "data.auto": "Automatic: newest save",
      "data.auto_name": "Automatic: newest · {name}", "data.pinned": "Pinned: {name}", "data.stale": "Newer save", "data.stations": "Stations",
      "data.nodes": "Track nodes", "data.platforms": "Platforms", "data.signals": "Signals", "data.no_saves": "No saves",
      "avatar.none_title": "No player figure", "avatar.none": "The third-person view shows no one. Choose a VRM model to see yourself.",
      "avatar.cleared": "Removed; installing won't put it back.", "avatar.meta": "{size} · loaded the next time the game starts", "avatar.hand": "not put there by Nimby3D",
      "avatar.note": "VRM models belong to their authors. Nimby3D only copies yours into your own game folder and never shares it.",
      "packs.count": "{n} found", "packs.none": "No shader packs found in %APPDATA%\\.minecraft\\shaderpacks.",
      "packs.hint": "Choose a pack and set its options on the Shader packs page, or in the game: F10 → Picture (experimental, NVIDIA only, off by default).",
      "activity.title": "Activity", "tab.activity": "Log", "tab.addon": "Add-on log", "tab.reshade": "ReShade log",
      "log.empty": "No activity yet. Every step of an install, refresh or sync shows up here.", "log.missing": "This log doesn't exist yet (the game writes it once it starts).",
      "log.meta": "{path} · {size} · last {n} lines", "log.refresh": "Refresh", "log.open": "Show in Explorer",
      "log.start": "▶ {op}", "log.ok": "✓ {op}: done", "log.fail": "✕ {op}: {msg}",
      "step.prepare": "Preparing", "step.export_data": "Reading the save", "step.export_tracks": "Exporting track", "step.export_dem": "Exporting terrain", "step.reshade": "ReShade",
      "step.reshade_ini": "ReShade settings", "step.addon": "Add-on", "step.data": "Placing save data", "step.shaders": "Shader cache", "step.landcover": "Land cover",
      "step.ambient": "Vehicle and boat models", "step.textures": "Surface textures", "step.avatar": "Player figure", "step.remove": "Deleting files", "step.done": "Done",
      "done.install": "Installed", "done.install_body": "It takes effect the next time you start the game.", "done.install_running": "Installed — restart the game to use it",
      "done.install_running_body": "The game keeps the version it started with.", "done.refresh": "Save data refreshed", "done.refresh_body": "{stations} stations · {nodes} track nodes",
      "done.disable": "Disabled", "done.disable_body": "The game starts without ReShade and the add-on next time.", "done.enable": "Enabled", "done.enable_running": "Enabled — takes effect the next time the game starts",
      "done.remove": "Uninstalled", "done.remove_body": "{n} files or folders deleted.", "done.remove_partial": "Some files could not be deleted",
      "done.avatar": "Player figure set", "done.clear_avatar": "Player figure removed", "done.save_pinned": "Now using the save {name}", "done.save_auto": "Now using the newest save",
      "done.game_set": "Game folder changed", "done.game_auto": "Switched to auto-detect",
      "watch.on": "Auto-sync is on", "watch.off": "Auto-sync is off", "watch.synced": "Synced {save}", "watch.stopped": "Auto-sync stopped",
      "op.failed": "{op} failed",
      "err.game_running": "NIMBY Rails is running. Quit the game first.",
      "err.foreign_dxgi": "The game folder already has a dxgi.dll that Nimby3D didn't install. To keep it intact, nothing was installed.",
      "err.game_not_found": "NimbyRails.exe was not found in {dir}.",
      "err.game_not_found_anywhere": "NIMBY Rails wasn't found in any Steam library. Choose the game folder yourself.",
      "err.missing_source": "A file to install is missing: {path}", "err.no_saves": "There are no saves in {dir}.", "err.save_missing": "Save not found: {path}",
      "err.not_installed": "Nimby3D is not installed yet.", "err.export_failed": "Could not read the save {name}: {error}",
      "err.in_use": "{name} is in use. Close the game and try again.", "err.avatar_bad": "{name} is not a VRM model.", "err.avatar_missing": "File not found: {path}",
      "err.avatar_not_ours": "This nimby3d_avatar.vrm wasn't put there by Nimby3D; delete it yourself.", "err.busy": "Another operation is running. Please wait.",
      "err.bad_folder": "That folder doesn't contain NimbyRails.exe.", "err.bad_save": "{name} is not a NIMBY Rails save (.nimbyrails5).",
      "err.no_dialog": "Couldn't open the file dialog.", "err.watch_elsewhere": "Another program is already syncing saves (process {pid}).",
      "err.unexpected": "Unexpected error: {message}", "err.offline": "Lost the connection to the Nimby3D backend.", "err.token": "This session has expired. Open Nimby3D again.",
      "rm.title": "Uninstall and delete Nimby3D?", "rm.lead": "The files listed below will be deleted from the game folder. The game's own files are not touched.",
      "rm.delete": "Will be deleted", "rm.edit": "Will be edited", "rm.keep": "Kept", "rm.total": "{n} items · {size}",
      "rm.purge": "Also delete the add-on's settings and what it learned (nimby3d.ini, nimby3d_units.txt, frame dumps …)", "rm.saves": "Your saves are never touched",
      "rm.blocked": "NIMBY Rails is running. Quit the game before uninstalling.", "rm.cancel": "Cancel", "rm.confirm": "Uninstall & delete", "rm.nothing": "Nothing to delete.",
      "rm.loading": "Listing files…", "rm.modified": "changed",
      "reason.reshade": "ReShade", "reason.reshade_generated": "written by ReShade", "reason.addon": "add-on", "reason.addon_log": "add-on log", "reason.aside": "old copy",
      "reason.scratch": "scratch file", "reason.record": "install record", "reason.user_data": "settings / learned data", "reason.not_ours": "not installed by Nimby3D",
      "reason.no_record": "no install record proves it is Nimby3D's", "reason.in_use_by_other_reshade": "used by another ReShade", "reason.strip_keys": "only the {n} settings Nimby3D added are removed",
      "path.title": "Game folder", "path.lead": "Enter the NIMBY Rails install folder (the one with NimbyRails.exe).", "path.ok": "Use this folder",
      "foot.safe": "Reads saves only · deletes only what it installed", "foot.browser": "browser mode",
      "rel.now": "just now", "rel.min": "{n} min ago", "rel.hour": "{n} h ago", "rel.day": "{n} d ago",
      "fatal.title": "Can't reach the Nimby3D backend", "fatal.body": "Close this page and run Nimby3D.cmd again.",
    },
  };
  // the results tools/install.py reports per file, in Chinese
  const RESULT_ZH = [
    [/^copied$/, "已复制"], [/^unchanged$/, "未变化"], [/^staged$/, "已就绪（下次启动游戏生效）"], [/^written$/, "已写入"], [/^updated$/, "已更新"],
    [/^not copied while the game runs$/, "游戏运行中，暂不替换"], [/^not made.*$/, "未生成"], [/^not included$/, "未包含"], [/^left as it is while the game runs$/, "游戏运行中，保持不变"],
    [/^kept as it is.*$/, "保持不变（已有插件所需设置）"], [/^kept your settings, added (\d+) the add-on needs$/, "保留你的设置，补充了 $1 项插件所需设置"],
    [/^none compiled yet.*$/, "还没有编译好的着色器"], [/^not there.*$/, "没有模型文件"], [/^(\d+) of (\d+) files copied(, (\d+) in use.*)?$/, "复制了 $1/$2 个文件"],
    [/^unchanged \((\d+) files\)$/, "未变化（$1 个文件）"], [/^unchanged \((\d+) shaders\)$/, "未变化（$1 个着色器）"],
    [/^(\d+) from the replay host, (\d+) in all$/, "新增 $1 个，共 $2 个着色器"], [/^none at .*$/, "没有人物模型（第三人称里看不到人物）"],
    [/^none \(taken out.*$/, "无（已在管理器中移除）"], [/^none \(choose a VRM.*$/, "没有人物模型（可在 Nimby3D 里选择自己的 VRM 模型）"], [/^none \(the chosen file.*$/, "无（所选文件已不存在）"], [/^kept \(the chosen file.*$/, "保留（所选文件已不存在）"],
    [/^kept the one already there.*$/, "保留已有的模型（不是本工具放进去的）"], [/^nothing to remove$/, "没有要删除的文件"],
  ];

  // ------------------------------------------------------------------ state
  let lang = "en", themePref = "system", S = null, curOp = null, seq = 0, mode = "window";
  let progress = { fraction: null, step: null };
  let logTab = "activity", logOpen = true, filesOpen = false, SHOT = false, shotHash = "", view = "home";
  const STEAM_APPID = "1134710";
  // The Nimby3D repository (its Releases page has the downloads)
  const NIMBY3D_REPO = "https://github.com/adaihappyjan/NIMBY-3D";
  // the portrait on the About page: art by PoLa on pixiv (credited under it)
  const LINKS = { repo: NIMBY3D_REPO, toolkit: "https://github.com/adaihappyjan/NIMBY-Timetable-Toolkit",
    pola: "https://www.pixiv.net/users/26489227", artwork: "https://www.pixiv.net/artworks/110183004" };
  const logEvents = [];
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function t(key, p) {
    let s = I18N[lang][key];
    if (s === undefined) s = I18N.en[key];
    if (s === undefined) return key;
    if (p) s = s.replace(/\{(\w+)\}/g, (m, k) => (p[k] !== undefined && p[k] !== null ? String(p[k]) : m));
    return s;
  }
  const tHtml = (key, p) => esc(t(key, p)).replace(/&lt;g&gt;(.*?)&lt;\/g&gt;/g, '<span class="grad">$1</span>');
  const icon = (id, cls = "i") => `<svg class="${cls}"><use href="#${id}"/></svg>`;

  // ------------------------------------------------------------------ pages
  /* The page's own pages: home, packs, settings, guide, about. packs and settings are built in page_packs.js and
     page_settings.js (window.N3D_BUILTIN_PAGES), with the same interface as a registered page.

     Registered pages: window.N3D_PAGES, an array that scripts loaded after this one push their pages into (at any
     time; replacing the whole array works too, and window.N3D_registerPage(page) is the same as a push):
       { id, icon: "<svg …>…</svg>", title: { zh, en }, mount(root, ctx), unmount?(), show?(), hide?() }
     Each gets a tab in the header after the built-in ones, in the order they register. mount(root, ctx) is called
     once, the first time the page is shown, with root an empty element of its own; the page stays in the document
     while another one shows (its root is hidden), so what is typed there is kept. show() / hide() are called each
     time it is shown or left; unmount() when a page with the same id replaces it, and when the window closes.
     ctx: call(method, args) -> Promise (a "trains.*" method goes to manager/trains.py; rejects with an Error whose
     message is the backend's error, and .code), t(zh, en), lang, onLang(cb) -> unsubscribe, toast(message, kind
     'ok'|'warn'|'error'|'info'), confirm({title, body, ok, danger}) -> Promise<boolean>, openExternal(url),
     pickFile({title, filters: [[label, "*.json;*.gov"]], save, name}) -> Promise<path|null>,
     pickFolder({title}) -> Promise<path|null>, status() -> the Home page's status object, go(viewId). */
  const BUILTIN_VIEWS = ["home", "packs", "settings", "guide", "about"];
  const pages = new Map(); // id -> {def, btn, root, mounted, ctx}
  const langListeners = new Set();
  let bridgeReady = null, markBridgeReady = null;
  bridgeReady = new Promise((resolve) => { markBridgeReady = resolve; });

  function viewRoot(v) {
    if (BUILTIN_VIEWS.includes(v)) return $("#view-" + v);
    const p = pages.get(v.replace(/^page-/, ""));
    return p ? p.root : null;
  }
  function builtinPage(v) {
    const b = window.N3D_BUILTIN_PAGES || {};
    return v === "packs" || v === "settings" ? b[v] : null;
  }
  function pageOf(v) {
    if (v.startsWith("page-")) {
      const p = pages.get(v.slice(5));
      return p ? p : null;
    }
    const def = builtinPage(v);
    if (!def) return null;
    if (!builtinState[v]) builtinState[v] = { def, root: $("#view-" + v), mounted: false, ctx: null, id: v };
    return builtinState[v];
  }
  const builtinState = {};
  function callHook(p, hook) {
    if (p && p.mounted && typeof p.def[hook] === "function") {
      try { p.def[hook](); } catch (e) { console.error(e); }
    }
  }
  function mountPage(p) {
    if (p.mounted) return;
    p.mounted = true;
    p.ctx = p.ctx || makeCtx(p.id);
    try {
      p.def.mount(p.root, p.ctx);
    } catch (e) {
      console.error(e);
      p.root.innerHTML = `<div class="card page-error">${icon("i-x-circle")}<span>${esc(String(e && e.message || e))}</span></div>`;
    }
  }
  function setView(v) {
    if (!BUILTIN_VIEWS.includes(v) && !(v.startsWith("page-") && pages.has(v.slice(5)))) v = "home";
    const before = view;
    if (before !== v) callHook(pageOf(before), "hide");
    view = v;
    $$("main > .view").forEach((el) => { el.hidden = el !== viewRoot(v); });
    $$("#nav [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === v)));
    const p = pageOf(v);
    if (p) {
      if (!p.mounted) mountPage(p);
      callHook(p, "show");
    }
    try { sessionStorage.setItem("n3d-view", v); } catch (e) { /* private mode */ }
    window.scrollTo({ top: 0 });
    fitNav();
  }

  function pageTitle(def) {
    const t0 = def.title || {};
    return (typeof t0 === "string" ? t0 : t0[lang] || t0.en || t0.zh) || def.id;
  }
  function registerPage(def) {
    if (!def || typeof def !== "object" || def.id === undefined || typeof def.mount !== "function") {
      console.warn("N3D_PAGES: a page needs an id and mount(root, ctx)", def);
      return;
    }
    const id = String(def.id).replace(/[^\w-]/g, "_");
    let p = pages.get(id);
    if (p) {
      if (p.def === def) return;
      if (p.mounted && typeof p.def.unmount === "function") {
        try { p.def.unmount(); } catch (e) { console.error(e); }
      }
      p.def = def;
      p.mounted = false;
      p.root.innerHTML = "";
    } else {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "tab");
      btn.dataset.view = "page-" + id;
      btn.setAttribute("aria-selected", "false");
      btn.setAttribute("aria-controls", "view-page-" + id);
      btn.addEventListener("click", () => setView("page-" + id));
      $("#nav").appendChild(btn);
      const root = document.createElement("div");
      root.className = "view page-host";
      root.id = "view-page-" + id;
      root.setAttribute("role", "tabpanel");
      root.hidden = true;
      $("main").insertBefore(root, $("main > footer.foot"));
      p = { id, def, btn, root, mounted: false, ctx: null };
      pages.set(id, p);
    }
    renderPageTab(p);
    renderGuide();
    fitNav();
    if (view === "page-" + id) setView(view);
    else if (pendingView === "page-" + id) { pendingView = null; setView("page-" + id); }
  }
  function renderPageTab(p) {
    const svg = typeof p.def.icon === "string" && /^\s*<svg[\s>]/i.test(p.def.icon) ? p.def.icon : icon("i-layers");
    p.btn.innerHTML = `<span class="pg-icon" aria-hidden="true">${svg}</span><span class="lbl">${esc(pageTitle(p.def))}</span>`;
    p.btn.title = pageTitle(p.def);
  }
  let pendingView = null; // a registered page remembered across a reload, shown once it registers
  // window.N3D_PAGES: an array whose push registers; replacing the array adopts its pages
  function pageArray(items) {
    const a = [];
    Object.defineProperty(a, "push", {
      enumerable: false,
      value: (...xs) => { xs.forEach((x) => { Array.prototype.push.call(a, x); registerPage(x); }); return a.length; },
    });
    (items || []).forEach((x) => Array.prototype.push.call(a, x));
    return a;
  }
  const earlyPages = Array.isArray(window.N3D_PAGES) ? window.N3D_PAGES.slice() : [];
  let pageList = pageArray([]);
  try {
    Object.defineProperty(window, "N3D_PAGES", {
      configurable: true,
      get: () => pageList,
      set: (v) => { pageList = pageArray([]); (Array.isArray(v) ? v : []).forEach((x) => pageList.push(x)); },
    });
  } catch (e) {
    window.N3D_PAGES = pageList;
  }
  window.N3D_registerPage = (def) => { pageList.push(def); };

  // the context a page gets
  function makeCtx(pageId) {
    return {
      call: (method, args) => pageCall(method, args),
      t: (zh, en) => (lang === "zh" ? zh : en),
      get lang() { return lang; },
      onLang(cb) {
        if (typeof cb === "function") langListeners.add(cb);
        return () => langListeners.delete(cb);
      },
      toast(message, kind) {
        const tone = { ok: "ok", warn: "warn", error: "danger", danger: "danger", info: "info" }[kind] || "info";
        const lines = String(message ?? "").split("\n");
        toast(tone, lines[0], lines.slice(1).join("\n"));
      },
      confirm: (o) => confirmDialog(o || {}),
      openExternal: (url) => pageCall("open_url", [String(url)]).then(() => true),
      pickFile: (o = {}) => pageCall("pick_file", { title: o.title || "", filters: o.filters || [], save: !!o.save, name: o.name || "" }).then((r) => r.path || null),
      pickFolder: (o = {}) => pageCall("pick_dir", { title: o.title || "" }).then((r) => r.path || null),
      status: () => S,
      go: (v) => setView(String(v)),
      page: pageId,
      util: { esc, icon, bytes, when, rel, num },
    };
  }
  async function pageCall(method, args) {
    await bridgeReady;
    const res = await Bridge.call("page_call", String(method), args === undefined ? {} : args);
    if (res && res.ok) return res.result;
    const known = res && I18N.en["err." + res.error];
    const err = new Error(known ? errText(res) : (res && (res.message || res.error)) || "?");
    err.code = res && res.error;
    err.params = (res && res.params) || {};
    err.response = res;
    throw err;
  }
  function confirmDialog(o) {
    const dlg = $("#dlg-confirm");
    $("#cf-title").textContent = o.title || "";
    $("#cf-body").textContent = o.body || "";
    $("#cf-body").hidden = !o.body;
    $("#cf-ok").textContent = o.ok || t("cf.ok");
    $("#cf-cancel").textContent = o.cancel || t("cf.cancel");
    $("#cf-ok").className = "btn btn-dlg " + (o.danger ? "btn-danger-solid" : "btn-primary");
    $("#cf-icon").className = "dlg-icon" + (o.danger ? "" : " info");
    $("#cf-icon").innerHTML = icon(o.danger ? "i-alert" : "i-help");
    return new Promise((resolve) => {
      let done = false;
      const finish = (v) => {
        if (done) return;
        done = true;
        cleanup();
        if (dlg.open) dlg.close();
        resolve(v);
      };
      const onOk = (ev) => { ev.preventDefault(); finish(true); };
      const onCancel = () => finish(false);
      const onClose = () => finish(false);
      const cleanup = () => {
        $("#cf-form").removeEventListener("submit", onOk);
        $("#cf-cancel").removeEventListener("click", onCancel);
        dlg.removeEventListener("close", onClose);
      };
      $("#cf-form").addEventListener("submit", onOk);
      $("#cf-cancel").addEventListener("click", onCancel);
      dlg.addEventListener("close", onClose);
      if (dlg.open) dlg.close();
      dlg.showModal();
      (o.danger ? $("#cf-cancel") : $("#cf-ok")).focus();
    });
  }

  // the tabs: when they do not fit beside everything else, only the current one keeps its name
  function fitNav() {
    const bar = $(".topbar");
    if (!bar) return;
    bar.classList.remove("compact", "tight");
    if (bar.scrollWidth > bar.clientWidth + 1) bar.classList.add("compact");
    if (bar.scrollWidth > bar.clientWidth + 1) bar.classList.add("tight");
  }

  // **bold** and `code` in the guide's text; everything else is plain text
  const rich = (text) => esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  function keyHtml(k) {
    if (k.startsWith("~")) return `<span class="mouse">${icon("i-mouse")}${esc(k.slice(1))}</span>`;
    if (/^[A-Z](?: [A-Z])+$/.test(k)) return `<span class="combo">${k.split(" ").map((c) => `<kbd>${esc(c)}</kbd>`).join("")}</span>`;
    return `<span class="combo">${k.split("+").map((c) => `<kbd>${esc(c)}</kbd>`).join('<span class="plus">+</span>')}</span>`;
  }
  function blockHtml(b) {
    const [kind, a, c] = b;
    if (kind === "p") return `<p>${rich(a)}</p>`;
    if (kind === "h3") return `<h3>${rich(a)}</h3>`;
    if (kind === "steps") return `<ol class="steps">${a.map((x) => `<li><span>${rich(x)}</span></li>`).join("")}</ol>`;
    if (kind === "bullets") return `<ul class="bullets">${a.map((x) => `<li>${rich(x)}</li>`).join("")}</ul>`;
    if (kind === "note" || kind === "ok" || kind === "warn") {
      const ic = { note: "i-info", ok: "i-shield", warn: "i-alert" }[kind];
      return `<div class="callout ${kind === "note" ? "" : kind}">${icon(ic)}<span>${rich(a)}</span></div>`;
    }
    if (kind === "keys") {
      const rows = c.map(([keys, text]) => `<tr><td class="k">${keys.map(keyHtml).join(`<span class="alt">${esc(t("guide.or"))}</span>`)}</td><td>${rich(text)}</td></tr>`).join("");
      return `<div class="keys-title">${esc(a)}</div><table class="keys"><tbody>${rows}</tbody></table>`;
    }
    if (kind === "swatches") return `<div class="swatches">${a.map(([col, text]) => `<div class="swatch"><i style="--c:${esc(col)}"></i><span>${rich(text)}</span></div>`).join("")}</div>`;
    if (kind === "goto") {
      const target = viewFor(a);
      return target ? `<div class="guide-goto"><button type="button" class="btn btn-sm btn-ghost" data-goto="${esc(target)}">${icon("i-external")}<span>${esc(c)}</span></button></div>` : "";
    }
    return "";
  }
  // a built-in view, or the first registered page whose id has this word in it
  function viewFor(word) {
    if (BUILTIN_VIEWS.includes(word)) return word;
    for (const id of pages.keys()) if (id.toLowerCase().includes(String(word).toLowerCase())) return "page-" + id;
    return null;
  }
  let guideObserver = null;
  function renderGuide() {
    const all = (window.N3D_GUIDE || {})[lang] || (window.N3D_GUIDE || {}).en;
    if (!all) return;
    const guide = all.filter((sec) => !sec.requires || viewFor(sec.requires));
    $("#guide-sections").innerHTML = guide.map((sec, i) =>
      `<section class="card gsec" id="g-${esc(sec.id)}" style="--i:${i + 1}" aria-labelledby="gh-${esc(sec.id)}">` +
      `<div class="card-head"><div class="card-icon">${icon(sec.icon)}</div><h2 id="gh-${esc(sec.id)}">${esc(sec.title)}</h2></div>` +
      sec.body.map(blockHtml).join("") + "</section>").join("");
    $$("#guide-sections [data-goto]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.goto)));
    $("#toc").innerHTML = guide.map((sec) => `<button type="button" data-sec="${esc(sec.id)}">${icon(sec.icon)}<span>${esc(sec.title)}</span></button>`).join("");
    $$("#toc [data-sec]").forEach((b) => b.addEventListener("click", () => {
      const el = $("#g-" + b.dataset.sec);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      setCurrent(b.dataset.sec);
    }));
    setCurrent(guide[0].id);
    if (guideObserver) guideObserver.disconnect();
    if ("IntersectionObserver" in window) {
      guideObserver = new IntersectionObserver((entries) => {
        const seen = entries.filter((e) => e.isIntersecting).sort((x, y) => x.boundingClientRect.top - y.boundingClientRect.top)[0];
        if (seen) setCurrent(seen.target.id.slice(2));
      }, { rootMargin: "-90px 0px -55% 0px" });
      $$(".gsec").forEach((el) => guideObserver.observe(el));
    }
  }
  function setCurrent(id) {
    $$("#toc [data-sec]").forEach((b) => b.setAttribute("aria-current", String(b.dataset.sec === id)));
  }

  // ------------------------------------------------------------------ backend
  const Bridge = {
    kind: null, token: null,
    async init() {
      SHOT = /[#&]shot=1/.test(location.hash); // a still picture of the page (no long poll), for rendering checks
      shotHash = location.hash;
      if (SHOT) document.documentElement.classList.add("still");
      const m = location.hash.match(/[#&]t=([\w-]+)/);
      if (m) {
        try { sessionStorage.setItem("n3d-token", m[1]); } catch (e) { /* private mode */ }
        this.token = m[1];
        history.replaceState(null, "", location.pathname);
      } else {
        try { this.token = sessionStorage.getItem("n3d-token"); } catch (e) { this.token = null; }
      }
      if (this.token && location.protocol.startsWith("http") && !window.pywebview) { this.kind = "http"; return; }
      if (window.pywebview && window.pywebview.api && window.pywebview.api.hello) { this.kind = "pywebview"; return; }
      await new Promise((resolve) => {
        window.addEventListener("pywebviewready", resolve, { once: true });
        setTimeout(resolve, 6000);
      });
      if (window.pywebview && window.pywebview.api) { this.kind = "pywebview"; return; }
      if (this.token) { this.kind = "http"; return; }
      throw new Error("no backend");
    },
    async call(name, ...args) {
      try {
        if (this.kind === "pywebview") return (await window.pywebview.api[name](...args)) || { ok: false, error: "unexpected", params: { message: "empty" } };
        const r = await fetch("/api/" + name, {
          method: "POST", cache: "no-store",
          headers: { "Content-Type": "application/json", "X-Nimby3D-Token": this.token || "" },
          body: JSON.stringify({ args }),
        });
        if (r.status === 401) return { ok: false, error: "token" };
        return await r.json();
      } catch (e) {
        return { ok: false, error: "offline", message: String(e) };
      }
    },
  };

  // ------------------------------------------------------------------ formatting
  const sha8 = (s) => (s ? String(s).slice(0, 8) : "");
  function bytes(n) {
    if (n === null || n === undefined) return "";
    if (n >= 1073741824) return (n / 1073741824).toFixed(2) + " GB";
    if (n >= 1048576) return (n / 1048576).toFixed(n >= 104857600 ? 0 : 1) + " MB";
    if (n >= 1024) return Math.round(n / 1024) + " KB";
    return n + " B";
  }
  function when(epoch) {
    if (!epoch) return "";
    const d = new Date(epoch * 1000);
    const pad = (x) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function rel(epoch) {
    if (!epoch) return "";
    const s = Math.max(0, Date.now() / 1000 - epoch);
    if (s < 60) return t("rel.now");
    if (s < 3600) return t("rel.min", { n: Math.floor(s / 60) });
    if (s < 86400) return t("rel.hour", { n: Math.floor(s / 3600) });
    return t("rel.day", { n: Math.floor(s / 86400) });
  }
  const isoEpoch = (iso) => (iso ? Date.parse(iso) / 1000 : null);
  const num = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString(lang === "zh" ? "zh-CN" : "en-US"));
  const compact = (n) => {
    if (n === null || n === undefined) return "—";
    if (Math.abs(n) < 10000) return num(n);
    try { return new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n); } catch (e) { return num(n); }
  };
  const clock = (epoch) => {
    const d = new Date(epoch * 1000);
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map((x) => String(x).padStart(2, "0")).join(":");
  };
  function errText(res) {
    if (!res) return t("err.offline");
    const key = "err." + res.error;
    if (I18N.en[key]) return t(key, Object.assign({ message: res.message }, res.params || {}));
    return res.message || res.error || "?";
  }

  // ------------------------------------------------------------------ theme and language
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  function applyTheme() {
    const resolved = themePref === "system" ? (media && media.matches ? "light" : "dark") : themePref;
    document.documentElement.dataset.theme = resolved;
    const btn = $("#theme-btn");
    const ic = themePref === "system" ? "i-monitor" : themePref === "light" ? "i-sun" : "i-moon";
    btn.innerHTML = icon(ic);
    btn.title = t("theme." + themePref);
    btn.setAttribute("aria-label", t("theme." + themePref));
  }
  if (media && media.addEventListener) media.addEventListener("change", () => themePref === "system" && applyTheme());

  function applyLang() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    $$("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
    $$("[data-i18n-alt]").forEach((el) => el.setAttribute("alt", t(el.dataset.i18nAlt)));
    $$("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    renderGuide();
    $$(".seg [data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    $("#btn-log-refresh").title = t("log.refresh");
    $("#btn-log-refresh").setAttribute("aria-label", t("log.refresh"));
    $("#btn-log-open").title = t("log.open");
    $("#btn-log-open").setAttribute("aria-label", t("log.open"));
    $$("#nav [data-view]").forEach((b) => { if (!b.dataset.view.startsWith("page-")) b.title = b.querySelector(".lbl").textContent; });
    pages.forEach(renderPageTab);
    applyTheme();
    if (S) render();
    renderLog();
    langListeners.forEach((cb) => { try { cb(lang); } catch (e) { console.error(e); } });
    fitNav();
  }

  // ------------------------------------------------------------------ appearance skins
  /* Colours (style.css: :root[data-skin=…], light and dark) and a picture of Nimby3D-chan (manager/ui/skins, made by
     tools/make_skins.py) or one of the player's own (kept in the manager's state folder: skin_set_picture). mode: the
     theme a skin suits, taken when it is chosen (the theme button still switches). pv: the picker's little preview
     (background, card, accent, text). */
  const SKINS = [
    { id: "classic", mode: null, art: null, pv: ["#0b1220", "#18233a", "linear-gradient(135deg,#3ee0c6,#4fb6ff 52%,#8085ff)", "#e9eef6"] },
    { id: "afternoon", mode: "light", art: "skins/afternoon.webp", thumb: "skins/afternoon_thumb.webp", pv: ["#fbf5ea", "#fffdf8", "linear-gradient(135deg,#8fd6f2,#4aa6ea 55%,#7d93f2)", "#2b2a33"] },
    { id: "sleepy", mode: "light", art: "skins/sleepy.webp", thumb: "skins/sleepy_thumb.webp", pv: ["#f5f1fb", "#ffffff", "linear-gradient(135deg,#a8e9d0,#bfaef5 55%,#f2b8da)", "#2d2840"] },
    { id: "nightshift", mode: "dark", art: "skins/nightshift.webp", thumb: "skins/nightshift_thumb.webp", pv: ["#070b18", "#111a38", "linear-gradient(135deg,#2ef0ff,#4f8bff 50%,#a35cff)", "#e6ecff"] },
  ];
  let skin = "classic";
  const skinPics = {}; // skin -> data: URL of the player's own picture
  const skinDef = (id) => SKINS.find((s) => s.id === id) || SKINS[0];
  const skinArt = (id) => skinPics[skinDef(id).id] || skinDef(id).art;
  function applySkin() {
    const d = skinDef(skin), url = skinArt(skin), root = document.documentElement;
    root.dataset.skin = d.id;
    root.classList.toggle("skin-art", !!url);
    root.style.setProperty("--mascot-url", url ? `url("${url}")` : "none");
    $$("img.mascot").forEach((img) => {
      if (url) {
        if (img.getAttribute("src") !== url) img.setAttribute("src", url);
        img.hidden = false;
      } else {
        img.hidden = true;
        img.removeAttribute("src");
      }
    });
    try { localStorage.setItem("n3d-skin", d.id); } catch (e) { /* private mode */ }
  }
  function setSkin(id) {
    const d = skinDef(id);
    skin = d.id;
    if (d.mode && themePref !== d.mode) {
      themePref = d.mode;
      Bridge.call("set_pref", "theme", themePref);
      applyTheme();
    }
    Bridge.call("set_pref", "skin", skin);
    applySkin();
    renderSkinDialog();
  }
  async function loadSkinPictures(list) {
    for (const id of Object.keys(list || {})) {
      const r = await Bridge.call("skin_picture", id);
      if (r.ok && r.data) skinPics[id] = r.data;
    }
    applySkin();
  }
  function renderSkinDialog() {
    const grid = $("#skin-grid");
    grid.innerHTML = SKINS.map((d) => {
      const url = skinPics[d.id] || d.thumb || d.art;
      const [bg, surface, grad, text] = d.pv;
      const acts = d.art ? `<div class="skin-acts"><button type="button" class="btn btn-sm btn-ghost" data-replace="${d.id}">${icon("i-image")}<span>${esc(t("skin.replace"))}</span></button>` +
        (skinPics[d.id] ? `<button type="button" class="btn btn-sm btn-ghost" data-restore="${d.id}">${icon("i-undo")}<span>${esc(t("skin.restore"))}</span></button>` : "") + "</div>" : "";
      return `<div class="skin-card${d.id === skin ? " on" : ""}">
        <button type="button" class="skin-pick" data-pick="${d.id}" aria-pressed="${d.id === skin}">
          <span class="skin-pv" style="--pv-bg:${bg};--pv-surface:${surface};--pv-grad:${grad};--pv-text:${text}">
            <span class="pv-top"><i></i><b></b></span><span class="pv-card"><i></i><i></i><b></b></span>
            ${url ? `<img src="${esc(url)}" alt="" class="pv-art">` : '<svg class="pv-logo"><use href="#logo"/></svg>'}
            ${d.id === skin ? `<span class="pv-on">${icon("i-check")}</span>` : ""}
          </span>
          <span class="skin-name">${esc(t("skin." + d.id))}${skinPics[d.id] ? `<em>${esc(t("skin.own"))}</em>` : ""}</span>
          <span class="skin-sub">${esc(t("skin." + d.id + "_sub"))}</span>
        </button>${acts}
      </div>`;
    }).join("");
  }
  async function replaceSkinPicture(id) {
    const r = await Bridge.call("pick_file", t("skin.pick_title"), [[t("skin.images"), "*.png;*.webp;*.jpg;*.jpeg"]], false, "");
    if (!r.ok) { toast("danger", errText(r)); return; }
    if (!r.path) return;
    const res = await Bridge.call("skin_set_picture", id, r.path);
    if (!res.ok) { toast("danger", errText(res)); return; }
    skinPics[id] = res.data;
    if (id !== skin) setSkin(id);
    else { applySkin(); renderSkinDialog(); }
    toast("ok", t("skin.replaced"));
  }
  async function restoreSkinPicture(id) {
    const res = await Bridge.call("skin_reset_picture", id);
    if (!res.ok) { toast("danger", errText(res)); return; }
    delete skinPics[id];
    applySkin();
    renderSkinDialog();
    toast("ok", t("skin.restored"));
  }
  function openSkins() {
    renderSkinDialog();
    $("#dlg-skin").showModal();
    const on = $("#skin-grid .skin-card.on .skin-pick");
    if (on) on.focus();
  }

  // ------------------------------------------------------------------ toasts
  function toast(tone, title, body, ms = 5200) {
    const ic = { ok: "i-check", danger: "i-x-circle", warn: "i-alert", info: "i-info" }[tone] || "i-info";
    const el = document.createElement("div");
    el.className = "toast";
    el.dataset.tone = tone;
    el.innerHTML = `<div class="ticon">${icon(ic)}</div><div><div class="ttitle">${esc(title)}</div>${body ? `<div class="tbody">${esc(body)}</div>` : ""}</div>` +
      `<button type="button" class="tclose" aria-label="×">${icon("i-x")}</button>`;
    const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 280); };
    el.querySelector(".tclose").addEventListener("click", close);
    $("#toasts").appendChild(el);
    while ($("#toasts").children.length > 4) $("#toasts").firstChild.remove();
    if (ms) setTimeout(close, tone === "danger" ? ms * 1.8 : ms);
  }

  // ------------------------------------------------------------------ the log
  function translateResult(r) {
    if (lang !== "zh" || typeof r !== "string") return r;
    for (const [re, zh] of RESULT_ZH) if (re.test(r)) return r.replace(re, zh);
    return r;
  }
  function logText(e) {
    if (e.type === "log") {
      if (lang === "zh" && e.key && I18N.zh["log." + e.key]) {
        const p = Object.assign({}, e.params || {});
        if (p.result !== undefined) p.result = translateResult(p.result);
        if (p.names !== undefined) p.names = translateResult(p.names);
        return t("log." + e.key, p);
      }
      return e.text;
    }
    if (e.type === "op_start") return t("log.start", { op: t("op." + e.op) });
    if (e.type === "op_end") return e.ok ? t("log.ok", { op: t("op." + e.op) }) : t("log.fail", { op: t("op." + e.op), msg: errText(e) });
    if (e.type === "watch") return e.running ? t("watch.on") : e.error ? `${t("watch.stopped")}: ${errText(e)}` : t("watch.off");
    return "";
  }
  function logClass(e) {
    if (e.type === "op_start") return "op";
    if (e.type === "op_end") return e.ok ? "ok" : "err";
    if (e.type === "watch") return e.error ? "warn" : "op";
    if (e.type === "log" && /^(watch_failed|remove_failed|kept_file|dxgi_not_ours_kept|enable_foreign_dxgi|avatar_replacing|no_dem|running_next_start)$/.test(e.key || "")) return "warn";
    return "";
  }
  function addLog(e) {
    if (!["log", "op_start", "op_end", "watch"].includes(e.type)) return;
    if (e.type === "op_end" && e.op === "sync" && e.ok) return;
    if (e.type === "op_start" && e.op === "sync") return;
    logEvents.push(e);
    if (logEvents.length > 500) logEvents.splice(0, logEvents.length - 500);
    if (logTab === "activity") {
      const list = $("#log");
      const empty = list.querySelector(".empty-line");
      if (empty) empty.remove();
      const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
      list.appendChild(logItem(e));
      while (list.children.length > 500) list.firstChild.remove();
      if (atBottom) list.scrollTop = list.scrollHeight;
    }
  }
  function logItem(e) {
    const li = document.createElement("li");
    li.className = logClass(e);
    li.innerHTML = `<span class="tm">${clock(e.t)}</span><span class="tx">${esc(logText(e))}</span>`;
    return li;
  }
  function renderLog() {
    const list = $("#log");
    list.innerHTML = "";
    if (!logEvents.length) {
      const li = document.createElement("li");
      li.className = "empty-line";
      li.textContent = t("log.empty");
      list.appendChild(li);
    } else {
      const frag = document.createDocumentFragment();
      logEvents.forEach((e) => frag.appendChild(logItem(e)));
      list.appendChild(frag);
      list.scrollTop = list.scrollHeight;
    }
  }

  let logFileTimer = null;
  async function loadLogFile() {
    const name = logTab === "addon" ? "nimby3d_probe.log" : "ReShade.log";
    const res = await Bridge.call("read_log", name, 200);
    const pre = $("#logfile"), meta = $("#logfile-meta");
    if (!res.ok) { pre.textContent = errText(res); meta.hidden = true; return; }
    const lg = res.log;
    if (!lg.exists) { pre.textContent = t("log.missing"); meta.hidden = true; return; }
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.textContent = lg.lines.join("\n");
    meta.hidden = false;
    meta.textContent = t("log.meta", { path: lg.path, size: bytes(lg.size), n: lg.lines.length });
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }
  function setLogTab(tab, save = true) {
    logTab = tab;
    $$("#log-tabs [data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    const file = tab !== "activity";
    $("#log").hidden = file;
    $("#logfile").hidden = !file;
    $("#logfile-meta").hidden = !file;
    $("#btn-log-refresh").hidden = !file;
    $("#btn-log-open").hidden = !file;
    clearInterval(logFileTimer);
    if (file) {
      loadLogFile();
      logFileTimer = setInterval(() => { if (!document.hidden && logOpen) loadLogFile(); }, 4000);
    } else {
      renderLog();
    }
    if (save) Bridge.call("set_pref", "log_tab", tab);
  }
  function setLogOpen(open, save = true) {
    logOpen = open;
    $("#activity").dataset.open = String(open);
    $("#activity-toggle").setAttribute("aria-expanded", String(open));
    if (save) Bridge.call("set_pref", "log_open", open);
  }

  // ------------------------------------------------------------------ progress
  function renderProgress() {
    const bar = $("#progress"), label = $("#op-label");
    if (!curOp) {
      bar.classList.add("done");
      bar.classList.remove("indeterminate");
      label.innerHTML = "";
      $("#pill-busy").hidden = true;
      return;
    }
    bar.classList.remove("done");
    const indeterminate = progress.fraction === null || curOp === "sync";
    bar.classList.toggle("indeterminate", indeterminate);
    if (!indeterminate) bar.querySelector(".bar").style.width = Math.max(3, progress.fraction * 100).toFixed(1) + "%";
    const step = progress.step && progress.step !== "done" ? " · " + t("step." + progress.step) : "";
    const pct = indeterminate ? "" : `<span class="pct">${Math.round(progress.fraction * 100)}%</span>`;
    label.innerHTML = `<span class="spin"></span><span>${esc(t("busy." + curOp))}${esc(step)}</span>${pct}`;
    $("#pill-busy").hidden = false;
    $("#pill-busy .label").textContent = t("busy." + curOp);
  }

  // ------------------------------------------------------------------ rendering the state
  // One big button that does the next sensible thing; when the game is not running it also starts it.
  function primaryFor(s) {
    const st = s.state;
    const running = !!(s.game && s.game.running);
    const go = (act, icon, label, op, playLabel) => (running ? { act, icon, label, op, play: false } : { act, icon: "i-play", label: playLabel, op, play: true });
    if (st === "no_game") return { act: "get_game", icon: "i-steam", label: "act.get_game", op: null };
    if (st === "not_installed") return go("install", "i-download", "act.install", "install", "act.install_play");
    if (st === "incomplete") return go("install", "i-download", "act.repair", "install", "act.repair_play");
    if (st === "disabled") return go("enable", "i-power", "act.enable", "enable", "act.enable_play");
    if (s.update_available) return Object.assign(go("install", "i-update", "act.update", "install", "act.update_play"), { icon: "i-update" });
    if (running) return { act: "none", icon: "i-play", label: "act.running", op: null, running: true };
    return { act: "play", icon: "i-play", label: "act.play", op: null };
  }
  const STATE_TONE = { no_game: "danger", not_installed: "info", installed: "ok", disabled: "muted", update: "warn", incomplete: "warn" };

  function note(tone, ic, text) {
    return `<div class="note" data-tone="${tone}">${icon(ic)}<span>${esc(text)}</span></div>`;
  }

  function render() {
    const s = S;
    document.body.classList.remove("loading");
    const st = s.state;
    const running = !!(s.game && s.game.running);
    const pillKey = st === "installed" && s.update_available ? "update" : st;
    const busy = curOp || (s.app && s.app.busy);
    const saves = s.saves || {};
    const haveSave = !!(saves.chosen_info ? saves.chosen_info.exists : saves.newest);
    const src = s.sources || {};
    const missingSrc = ["addon", "reshade"].filter((k) => !(src[k] && src[k].exists));

    // header
    const pill = $("#pill-state");
    pill.dataset.tone = STATE_TONE[pillKey] || "muted";
    pill.querySelector(".label").textContent = t("pill." + pillKey);
    pill.classList.toggle("pulse", pillKey === "update");
    $("#pill-running").hidden = !running;

    // hero
    const hero = $("#hero");
    hero.dataset.state = st;
    const titleKey = pillKey === "update" ? "hero.update.title" : `hero.${st}.title`;
    $("#hero-title").innerHTML = tHtml(titleKey);
    let sub;
    if (pillKey === "update") sub = t("hero.update.sub", { a: sha8(s.installed && s.installed.sha) || "—", b: sha8(s.available && s.available.sha) || "—" });
    else if (st === "installed" && (s.staged || []).length) sub = t("hero.staged.sub");
    else if (st === "installed" && running) sub = t("hero.installed_running.sub");
    else if (st === "no_game" && s.game && s.game.dir) sub = t("hero.no_game.sub_dir", { dir: s.game.dir });
    else if (st === "no_game") sub = t("hero.no_game.steam");
    else sub = t(`hero.${st}.sub`);
    $("#hero-sub").textContent = sub;
    const eyebrow = [t("eyebrow")];
    if (s.installed && s.installed.sha) eyebrow.push(`build ${sha8(s.installed.sha)}`);
    $("#hero-eyebrow").innerHTML = eyebrow.map(esc).join('<span class="sep">·</span>');

    const p = primaryFor(s);
    const pb = $("#primary");
    pb.dataset.act = p.act;
    pb.dataset.play = p.play ? "1" : "";
    pb.classList.toggle("is-running", !!p.running);
    const isBusyHere = busy && p.op && busy === p.op;
    pb.classList.toggle("busy", !!isBusyHere);
    pb.innerHTML = (isBusyHere ? '<span class="spin"></span>' : icon(p.icon)) + `<span class="label">${esc(isBusyHere ? t("busy." + busy) : t(p.label))}</span>`;
    let primaryOff = !!busy || !!p.running;
    if (p.act === "install" && (missingSrc.length || !haveSave)) primaryOff = true;
    pb.disabled = primaryOff;
    $("#btn-game-folder").hidden = st !== "no_game";
    $("#btn-recheck").hidden = st !== "no_game";

    const installedLike = st === "installed" || st === "disabled";
    const toggle = $("#btn-toggle");
    toggle.hidden = st !== "installed";
    toggle.querySelector(".label").textContent = t("act.disable");
    toggle.disabled = !!busy || running;
    toggle.title = running ? t("note.running") : "";
    const rb = $("#btn-refresh");
    rb.hidden = !(installedLike || st === "incomplete");
    rb.disabled = !!busy || !haveSave;
    const sw = $("#watch-switch");
    sw.hidden = !installedLike;
    const watchOn = !!(s.watch && s.watch.running);
    const elsewhere = watchOn && !(s.app && s.app.watch_own);
    sw.setAttribute("aria-checked", String(watchOn));
    sw.disabled = elsewhere;
    sw.title = elsewhere ? t("note.watch_elsewhere") : t("note.watching");
    const rm = $("#btn-remove");
    rm.hidden = !(installedLike || st === "incomplete" || (s.manifest && s.manifest.exists));
    rm.disabled = !!busy;

    const notes = [];
    if (running && st !== "no_game") notes.push(note("info", "i-info", t("note.running")));
    if ((s.staged || []).length) notes.push(note("warn", "i-clock", t("note.staged")));
    if (s.reshade && s.reshade.foreign_dxgi) notes.push(note("warn", "i-alert", t("note.foreign_dxgi")));
    if (s.reshade && (s.reshade.other_proxies || []).length) notes.push(note("warn", "i-alert", t("note.other_proxies", { names: s.reshade.other_proxies.join(", ") })));
    if (st !== "no_game" && (st !== "installed" || s.update_available) && missingSrc.length) {
      notes.push(note("danger", "i-x-circle", t("note.no_build", { what: missingSrc.map((k) => (src[k] && src[k].path) || k).join(", ") })));
    }
    if (st !== "no_game" && !haveSave) notes.push(note("warn", "i-alert", t("note.no_saves", { dir: saves.dir || "?" })));
    if (installedLike && s.data && s.data.stale && !watchOn) notes.push(note("info", "i-refresh", t("note.stale")));
    if (watchOn) notes.push(note("ok", "i-sync", elsewhere ? t("note.watch_elsewhere") : t("note.watching")));
    notes.push(note("ok", "i-shield", t("note.saves_safe")));
    const html = notes.slice(0, 4).join("");
    if ($("#hero-notes").dataset.html !== html) { $("#hero-notes").innerHTML = html; $("#hero-notes").dataset.html = html; }

    renderGame(s, running, busy);
    renderAddon(s);
    renderData(s, busy);
    renderAvatar(s, busy);
    renderPacks(s);
    $("#foot-version").textContent = `Nimby3D v${(s.app && s.app.version) || ""}${mode === "browser" ? " · " + t("foot.browser") : ""}`;
    renderProgress();
  }

  function setBadge(el, tone, text) {
    el.hidden = !text;
    el.dataset.tone = tone || "";
    const label = el.querySelector(".label");
    label.textContent = text || "";
    label.classList.remove("sk");
  }
  function clearSk(...ids) { ids.forEach((id) => $(id).classList.remove("sk")); }

  function renderGame(s, running, busy) {
    const g = s.game || {};
    clearSk("#game-dir", "#game-how", "#game-saves");
    setBadge($("#game-badge"), !g.found ? "danger" : running ? "accent" : "", !g.found ? t("game.missing") : running ? t("game.running") : t("game.closed"));
    $("#game-dir").textContent = g.dir || "—";
    $("#game-dir").title = g.dir || "";
    $("#game-how").textContent = g.how ? t("how." + g.how) : "—";
    const sv = s.saves || {};
    $("#game-saves").innerHTML = sv.dir ? `<span class="mono" style="color:var(--text-2)">${esc(sv.dir)}</span><span class="sub-line">${esc(t(sv.count === 1 ? "game.saves_one" : "game.saves_count", { n: sv.count || 0 }))}</span>` : "—";
    $("#game-saves").title = sv.dir || "";
    $("#btn-open-game").disabled = !g.found;
    $("#btn-choose-game").disabled = !!busy;
    $("#btn-auto-game").hidden = !(s.app && s.app.manual_game);
    $("#btn-auto-game").disabled = !!busy;
  }

  function renderAddon(s) {
    clearSk("#addon-installed", "#addon-available", "#addon-reshade", "#files-summary");
    const st = s.state;
    const key = st === "installed" && s.update_available ? "update" : st;
    setBadge($("#addon-badge"), STATE_TONE[key], t("pill." + key));
    const inst = s.installed || {}, av = s.available || {};
    $("#addon-installed").innerHTML = inst.sha
      ? `<span class="sha">${esc(sha8(inst.sha))}</span>${st === "disabled" ? ` <span class="faint">· ${esc(t("addon.off"))}</span>` : ""}<span class="sub-line">${esc(when(inst.mtime))}</span>`
      : "—";
    const how = s.sources && s.sources.addon ? s.sources.addon.how : null;
    $("#addon-available").innerHTML = av.sha
      ? `<span class="sha">${esc(sha8(av.sha))}</span> <span class="faint">· ${esc(t("src." + how))}</span><span class="sub-line">${esc(when(av.mtime))}</span>`
      : `<span class="faint">${esc(t("addon.no_build"))}</span>`;
    $("#addon-available").title = av.path || "";
    const r = s.reshade || {};
    let rs = t("reshade.none");
    if (r.foreign_dxgi) rs = `<span style="color:var(--warn)">${esc(t("reshade.foreign"))}</span>`;
    else if (r.ours) rs = esc(st === "disabled" ? t("reshade.ours_off") : t("reshade.ours")) + (r.update ? ` <span class="faint">· ${esc(t("reshade.update"))}</span>` : "");
    else rs = esc(rs);
    $("#addon-reshade").innerHTML = rs;
    const fs = s.files_summary;
    const files = s.files || [];
    const sum = $("#files-summary");
    if (!fs || !files.length) {
      sum.textContent = t("files.none");
      sum.style.color = "";
    } else if (fs.missing || fs.modified) {
      sum.textContent = t("files.problems", { missing: fs.missing, modified: fs.modified });
      sum.style.color = "var(--warn)";
    } else if (fs.disabled) {
      sum.textContent = t("files.ok", { n: fs.ok }) + " · " + t("files.disabled", { n: fs.disabled });
      sum.style.color = "";
    } else {
      sum.textContent = t("files.ok", { n: fs.ok });
      sum.style.color = "";
    }
    const tg = $("#files-toggle");
    tg.hidden = !files.length;
    tg.setAttribute("aria-expanded", String(filesOpen));
    tg.querySelector("span").textContent = filesOpen ? t("files.hide") : t("files.show");
    const list = $("#file-list");
    list.hidden = !filesOpen || !files.length;
    const ICON = { ok: "i-check-circle", present: "i-check-circle", missing: "i-x-circle", modified: "i-alert", disabled: "i-minus-circle", unreadable: "i-alert" };
    list.innerHTML = files.map((f) => {
      const extra = f.files ? ` (${f.files})` : "";
      return `<li title="${esc(t("file." + f.state))}">${icon(ICON[f.state] || "i-info", "i st " + f.state)}<span class="fname">${esc(f.name)}${esc(extra)}</span><span class="fsize">${esc(f.size ? bytes(f.size) : t("file." + f.state))}</span></li>`;
    }).join("");
  }

  function renderData(s, busy) {
    clearSk("#data-from", "#data-source", "#st-stations", "#st-nodes", "#st-platforms", "#st-signals");
    const d = s.data || {};
    const saves = s.saves || {};
    if (d.save_name) {
      const ex = isoEpoch(d.exported_at);
      $("#data-from").innerHTML = `${esc(d.save_name)}<span class="sub-line" title="${esc(when(ex))}">${esc(t("data.exported", { when: rel(ex) }))}</span>`;
    } else {
      $("#data-from").innerHTML = `<span class="faint">${esc(t("data.none"))}</span>`;
    }
    $("#data-from").title = d.save || "";
    const pinned = s.app && s.app.pinned_save;
    if (pinned) {
      const name = pinned.split(/[\\/]/).pop();
      $("#data-source").innerHTML = `${icon("i-pin", "i")} ${esc(t("data.pinned", { name }))}`.replace('class="i"', 'class="i" style="width:14px;height:14px;vertical-align:-2px;color:var(--accent)"');
    } else if (saves.newest) {
      $("#data-source").textContent = t("data.auto_name", { name: saves.newest.name });
    } else {
      $("#data-source").innerHTML = `<span class="faint">${esc(t("data.no_saves"))}</span>`;
    }
    $("#data-source").title = pinned || (saves.newest && saves.newest.path) || saves.dir || "";
    [["#st-stations", d.stations], ["#st-nodes", d.nodes], ["#st-platforms", d.platforms], ["#st-signals", d.signals]].forEach(([id, v]) => {
      $(id).textContent = compact(v);
      $(id).title = num(v);
    });
    const stale = (s.state === "installed" || s.state === "disabled") && d.stale;
    setBadge($("#data-badge"), "warn", stale ? t("data.stale") : "");
    $("#btn-newest-save").hidden = !pinned;
    $("#btn-newest-save").disabled = !!busy;
    $("#btn-choose-save").disabled = !!busy;
  }

  function renderAvatar(s, busy) {
    clearSk("#avatar-name");
    const a = s.avatar || {};
    const tile = $("#avatar-tile");
    tile.classList.toggle("none", !a.present);
    if (a.present) {
      $("#avatar-name").textContent = a.name || "nimby3d_avatar.vrm";
      $("#avatar-name").title = a.source || "";
      $("#avatar-meta").textContent = t("avatar.meta", { size: bytes(a.size) }) + (a.ours ? "" : " · " + t("avatar.hand"));
    } else {
      $("#avatar-name").textContent = t("avatar.none_title");
      $("#avatar-name").title = "";
      $("#avatar-meta").textContent = a.cleared ? t("avatar.cleared") : t("avatar.none");
    }
    const found = s.game && s.game.found;
    $("#btn-choose-avatar").disabled = !!busy || !found;
    $("#btn-clear-avatar").disabled = !!busy || !a.present;
  }

  function renderPacks(s) {
    const packs = s.shaderpacks || [];
    setBadge($("#packs-badge"), packs.length ? "accent" : "", t("packs.count", { n: packs.length }));
    const pk = s.pack;
    const chosen = pk && pk.name ? pk.name : null;
    const there = chosen && packs.some((n) => n.toLowerCase() === chosen.toLowerCase());
    const now = $("#pack-now");
    now.hidden = !pk || !s.game || !s.game.found;
    if (pk) {
      const tone = pk.enabled && there ? "ok" : pk.enabled ? "warn" : "muted";
      const text = pk.enabled && there ? t("packs.now_on", { name: chosen.replace(/\.zip$/i, "") }) : pk.enabled && chosen ? t("packs.now_missing", { name: chosen }) : t("packs.now_off");
      now.innerHTML = `<span class="dot" data-tone="${tone}"></span><span>${esc(text)}</span>`;
    }
    const box = $("#packs");
    if (!packs.length) {
      box.innerHTML = `<div class="empty">${icon("i-sparkles")}<span>${esc(t("packs.none"))}</span></div>`;
      return;
    }
    const max = 10;
    const sel = (n) => pk && pk.enabled && chosen && n.toLowerCase() === chosen.toLowerCase();
    const order = packs.slice().sort((a, b) => (sel(b) ? 1 : 0) - (sel(a) ? 1 : 0));
    let html = order.slice(0, max).map((n) => `<span class="chip${sel(n) ? " on" : ""}" title="${esc(n)}">${icon(sel(n) ? "i-check" : "i-sparkles")}<span>${esc(n.replace(/\.zip$/i, ""))}</span></span>`).join("");
    if (packs.length > max) html += `<span class="chip more" title="${esc(order.slice(max).join("\n"))}">+${packs.length - max}</span>`;
    box.innerHTML = html;
  }

  // ------------------------------------------------------------------ talking to the backend
  let statusPending = null;
  async function refreshStatus() {
    if (statusPending) return statusPending;
    statusPending = (async () => {
      const res = await Bridge.call("status");
      if (res.ok) {
        S = res.status;
        if (S.app && !curOp && S.app.busy) curOp = S.app.busy;
        render();
      } else if (res.error === "offline" || res.error === "token") {
        offline(res);
      }
    })();
    try { await statusPending; } finally { statusPending = null; }
  }
  let statusTimer = null;
  function scheduleStatus(ms = 150) {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(refreshStatus, ms);
  }

  let offlineShown = false;
  function offline(res) {
    if (offlineShown) return;
    offlineShown = true;
    toast("danger", t("err.offline"), res && res.error === "token" ? t("err.token") : t("fatal.body"), 0);
  }

  function onEvent(e, replay) {
    switch (e.type) {
      case "log": addLog(e); break;
      case "progress":
        if (e.op && e.op === curOp) { progress = { fraction: e.fraction, step: e.step }; renderProgress(); }
        break;
      case "op_start":
        addLog(e);
        if (!replay) { curOp = e.op; progress = { fraction: null, step: null }; if (S) render(); }
        break;
      case "op_end":
        addLog(e);
        if (!replay) {
          curOp = null;
          progress = { fraction: null, step: null };
          finished(e);
          scheduleStatus(50);
        }
        break;
      case "watch":
        addLog(e);
        if (!replay && e.error) toast("warn", t("watch.stopped"), errText(e));
        if (!replay) scheduleStatus(50);
        break;
      case "synced":
        if (!replay) toast("ok", t("watch.synced", { save: (e.result && e.result.save || "").split(/[\\/]/).pop() }), t("done.refresh_body", { stations: num(e.result && e.result.stations), nodes: num(e.result && e.result.nodes) }), 3500);
        break;
      case "status_changed":
        if (!replay) scheduleStatus(80);
        break;
      default: break;
    }
  }

  function finished(e) {
    const r = e.result || {};
    if (!e.ok) {
      if (e.op !== "sync") toast("danger", t("op.failed", { op: t("op." + e.op) }), errText(e));
      return;
    }
    switch (e.op) {
      case "install":
        if (r.launched) toast("ok", t("done.install_launched"), t("done.launched_body"));
        else if (r.running) toast("ok", t("done.install_running"), t("done.install_running_body"));
        else toast("ok", t("done.install"), t("done.refresh_body", { stations: num(r.stations), nodes: num(r.nodes) }) + " · " + t("done.install_body"));
        break;
      case "refresh": toast("ok", t("done.refresh"), t("done.refresh_body", { stations: num(r.stations), nodes: num(r.nodes) })); break;
      case "disable": toast("ok", t("done.disable"), t("done.disable_body")); break;
      case "enable":
        if (r.launched) toast("ok", t("done.enable_launched"), t("done.launched_body"));
        else toast("ok", r.running ? t("done.enable_running") : t("done.enable"));
        break;
      case "remove":
        if ((r.failed || []).length) toast("warn", t("done.remove_partial"), r.failed.map((f) => f.name).join(", "));
        else toast("ok", t("done.remove"), t("done.remove_body", { n: (r.removed || []).length }));
        break;
      case "avatar": toast("ok", t("done.avatar"), r.avatar || ""); break;
      case "clear_avatar": toast("ok", t("done.clear_avatar")); break;
      default: break;
    }
  }

  async function pollEvents() {
    for (;;) {
      const res = await Bridge.call("events", seq, 15);
      if (!res.ok) {
        if (res.error === "token") { offline(res); return; }
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }
      if (offlineShown) { offlineShown = false; toast("ok", "Nimby3D", "✓"); }
      if (res.reset) { seq = 0; }
      for (const e of res.events) onEvent(e, false);
      seq = res.seq;
    }
  }

  async function act(name, ...args) {
    const res = await Bridge.call(name, ...args);
    if (!res.ok && !res.cancelled) {
      if (res.error === "no_dialog" && name === "choose_game_folder") { openPath(); return res; }
      const opKey = "op." + (opOf[name] || name);
      if (res.error === "busy") toast("info", t("err.busy"));
      else if (I18N.en[opKey]) toast("danger", t("op.failed", { op: t(opKey) }), errText(res));
      else toast("danger", errText(res));
    }
    if (res.ok && res.op) { curOp = curOp || res.op; progress = { fraction: null, step: null }; if (S) render(); }
    scheduleStatus(60);
    return res;
  }
  const opOf = { install: "install", refresh: "refresh", enable: "enable", disable: "disable", remove: "remove", choose_avatar: "avatar", clear_avatar: "clear_avatar", watch_start: "sync" };

  // ------------------------------------------------------------------ the remove dialog
  let planReq = 0;
  async function loadPlan() {
    const id = ++planReq;
    const purge = $("#rm-purge").checked;
    $("#rm-delete").innerHTML = `<li><span></span><span class="faint">${esc(t("rm.loading"))}</span></li>`;
    $("#rm-confirm").disabled = true;
    const res = await Bridge.call("remove_plan", purge);
    if (id !== planReq) return;
    if (!res.ok) { $("#rm-delete").innerHTML = `<li><span></span><span>${esc(errText(res))}</span></li>`; return; }
    const plan = res.plan;
    const row = (e, tone, ic) => {
      const reason = e.reason === "strip_keys" ? t("reason.strip_keys", { n: (e.keys || []).length }) : t("reason." + e.reason);
      const mod = e.modified ? ` · ${t("rm.modified")}` : "";
      const size = e.dir ? `${e.files} · ${bytes(e.size)}` : e.size !== undefined ? bytes(e.size) : "";
      return `<li>${icon(ic, "i st " + tone)}<span class="pname" title="${esc(e.name)}">${esc(e.name)}${e.dir ? "\\" : ""}</span><span class="preason">${esc(reason + mod)}</span><span class="psize">${esc(size)}</span></li>`;
    };
    $("#rm-delete").innerHTML = plan.delete.length ? plan.delete.map((e) => row(e, "danger", "i-trash")).join("") : `<li><span></span><span class="faint">${esc(t("rm.nothing"))}</span></li>`;
    const total = plan.delete.reduce((a, e) => a + (e.size || 0), 0);
    $("#rm-total").textContent = plan.delete.length ? t("rm.total", { n: plan.delete.length, size: bytes(total) }) : "";
    $("#rm-edit-wrap").hidden = !plan.edit.length;
    $("#rm-edit").innerHTML = plan.edit.map((e) => row(e, "warn", "i-edit")).join("");
    $("#rm-keep-wrap").hidden = !plan.keep.length;
    $("#rm-keep").innerHTML = plan.keep.map((e) => row(e, "ok", "i-shield")).join("");
    $("#rm-blocked").hidden = !plan.blocked;
    $("#rm-confirm").disabled = !!plan.blocked || !plan.delete.length;
  }
  function openRemove() {
    $("#rm-purge").checked = false;
    $("#dlg-remove").showModal();
    $("#rm-cancel").focus();
    loadPlan();
  }

  // ------------------------------------------------------------------ the folder dialog (when no native picker)
  function openPath() {
    $("#path-input").value = (S && S.game && S.game.dir) || "";
    $("#path-err").textContent = "";
    $("#dlg-path").showModal();
    $("#path-input").focus();
    $("#path-input").select();
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    $$(".seg [data-lang]").forEach((b) => b.addEventListener("click", () => {
      lang = b.dataset.lang;
      Bridge.call("set_pref", "lang", lang);
      applyLang();
    }));
    $("#theme-btn").addEventListener("click", () => {
      themePref = { system: "light", light: "dark", dark: "system" }[themePref] || "system";
      Bridge.call("set_pref", "theme", themePref);
      applyTheme();
    });
    $("#skin-btn").addEventListener("click", openSkins);
    $("#skin-close").addEventListener("click", () => $("#dlg-skin").close());
    $("#skin-grid").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-pick],[data-replace],[data-restore]");
      if (!b) return;
      if (b.dataset.pick) setSkin(b.dataset.pick);
      else if (b.dataset.replace) replaceSkinPicture(b.dataset.replace);
      else if (b.dataset.restore) restoreSkinPicture(b.dataset.restore);
    });
    $("#primary").addEventListener("click", async () => {
      const a = $("#primary").dataset.act;
      const play = $("#primary").dataset.play === "1";
      if (a === "get_game") act("open_url", "steam://store/" + STEAM_APPID);
      else if (a === "play") { const r = await act("play"); if (r.ok) toast("ok", t("done.launched"), t("done.launched_body")); }
      else if (a === "install" || a === "enable") act(a, play);
      else if (a === "choose_game") act("choose_game_folder").then((r) => r.ok && toast("ok", t("done.game_set"), r.dir));
    });
    $("#btn-game-folder").addEventListener("click", async () => {
      const r = await act("choose_game_folder");
      if (r.ok) toast("ok", t("done.game_set"), r.dir);
    });
    $("#btn-recheck").addEventListener("click", () => refreshStatus());
    $$("#nav [data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
    $("#nav").addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      const tabs = $$("#nav [data-view]");
      const i = tabs.findIndex((b) => b.dataset.view === view);
      const next = tabs[(i + (ev.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      setView(next.dataset.view);
    });
    $$("[data-link]").forEach((b) => b.addEventListener("click", () => act("open_url", LINKS[b.dataset.link])));
    $$("#view-home [data-goto]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.goto)));
    $("#btn-toggle").addEventListener("click", () => act("disable"));
    $("#btn-refresh").addEventListener("click", () => act("refresh"));
    $("#watch-switch").addEventListener("click", async () => {
      const on = $("#watch-switch").getAttribute("aria-checked") === "true";
      $("#watch-switch").setAttribute("aria-checked", String(!on));
      const r = await act(on ? "watch_stop" : "watch_start");
      if (r.ok && on) toast("info", t("watch.off"));
    });
    $("#btn-remove").addEventListener("click", openRemove);
    $("#rm-purge").addEventListener("change", loadPlan);
    $("#rm-cancel").addEventListener("click", () => $("#dlg-remove").close());
    $("#rm-confirm").addEventListener("click", async () => {
      const purge = $("#rm-purge").checked;
      $("#dlg-remove").close();
      act("remove", purge);
    });
    $("#btn-open-game").addEventListener("click", () => act("open_game_folder"));
    $("#btn-choose-game").addEventListener("click", async () => {
      const r = await act("choose_game_folder");
      if (r.ok) toast("ok", t("done.game_set"), r.dir);
    });
    $("#btn-auto-game").addEventListener("click", async () => {
      const r = await act("auto_game_folder");
      if (r.ok) toast("info", t("done.game_auto"), (r.found && r.found.dir) || "");
    });
    $("#path-cancel").addEventListener("click", () => $("#dlg-path").close());
    $("#path-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const r = await Bridge.call("set_game_folder", $("#path-input").value);
      if (r.ok) { $("#dlg-path").close(); toast("ok", t("done.game_set"), r.dir); scheduleStatus(20); }
      else $("#path-err").textContent = errText(r);
    });
    $("#btn-choose-save").addEventListener("click", async () => {
      const r = await act("choose_save");
      if (r.ok) toast("info", t("done.save_pinned", { name: (r.save || "").split(/[\\/]/).pop() }));
    });
    $("#btn-newest-save").addEventListener("click", async () => {
      const r = await act("use_newest_save");
      if (r.ok) toast("info", t("done.save_auto"));
    });
    $("#btn-choose-avatar").addEventListener("click", () => act("choose_avatar"));
    $("#btn-clear-avatar").addEventListener("click", () => act("clear_avatar"));
    $("#files-toggle").addEventListener("click", () => { filesOpen = !filesOpen; if (S) renderAddon(S); });
    $("#activity-toggle").addEventListener("click", () => setLogOpen(!logOpen));
    $$("#log-tabs [data-tab]").forEach((b) => b.addEventListener("click", () => setLogTab(b.dataset.tab)));
    $("#log-tabs").addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      const tabs = $$("#log-tabs [data-tab]");
      const i = tabs.findIndex((b) => b.dataset.tab === logTab);
      const next = tabs[(i + (ev.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      setLogTab(next.dataset.tab);
    });
    $("#btn-log-refresh").addEventListener("click", loadLogFile);
    $("#btn-log-open").addEventListener("click", () => act("open_log", logTab === "addon" ? "nimby3d_probe.log" : "ReShade.log"));
    document.addEventListener("visibilitychange", () => { if (!document.hidden) scheduleStatus(10); });
    setInterval(() => { if (!document.hidden && !curOp) refreshStatus(); }, 4000);
    setInterval(() => { if (S && !document.hidden) { renderData(S, curOp); } }, 30000); // relative times
  }

  function fatal() {
    document.body.classList.remove("loading");
    $("main").innerHTML = `<div class="fatal"><h2>${esc(t("fatal.title"))}</h2><p>${esc(t("fatal.body"))}</p></div>`;
  }

  async function boot() {
    lang = (navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en";
    try { skin = skinDef(localStorage.getItem("n3d-skin")).id; } catch (e) { skin = "classic"; }
    applySkin();
    applyTheme();
    applyLang();
    wire();
    earlyPages.forEach((p) => pageList.push(p)); // pages registered before this script ran
    try { await Bridge.init(); } catch (e) { fatal(); return; }
    const h = await Bridge.call("hello");
    if (!h.ok) { fatal(); return; }
    markBridgeReady();
    mode = h.mode;
    $("#app-version").textContent = "v" + h.version;
    lang = h.prefs.lang || h.default_lang || lang; // a remembered choice, else the system's language
    themePref = h.prefs.theme || "system";
    skin = skinDef(h.prefs.skin).id;
    const shotSkin = SHOT && shotHash.match(/[#&]skin=(\w+)/);
    if (shotSkin) skin = skinDef(shotSkin[1]).id; // (a still picture of another skin: not remembered)
    applySkin();
    loadSkinPictures(h.skin_pictures);
    logOpen = h.prefs.log_open !== false;
    logTab = h.prefs.log_tab || "activity";
    applyLang();
    setLogOpen(logOpen, false);
    const backlog = await Bridge.call("events", 0, 0);
    if (backlog.ok) {
      backlog.events.forEach((e) => onEvent(e, true));
      seq = backlog.seq;
    }
    setLogTab(logTab, false);
    await refreshStatus();
    if (!SHOT) pollEvents();
    else if (/[#&]open=remove/.test(shotHash)) openRemove();
    if (SHOT) {
      const m = shotHash.match(/[#&]view=([\w-]+)/);
      if (m) { if (m[1].startsWith("page-") && !pages.has(m[1].slice(5))) pendingView = m[1]; else setView(m[1]); }
    } else {
      let last = null;
      try { last = sessionStorage.getItem("n3d-view"); } catch (e) { last = null; }
      if (last && last !== "home") {
        if (last.startsWith("page-") && !pages.has(last.slice(5))) pendingView = last;
        else setView(last);
      }
    }
  }

  window.__n3d = { get state() { return S; }, get lang() { return lang; }, t, render: () => S && render(), setView, get pages() { return [...pages.keys()]; } }; // for tests
  window.addEventListener("pagehide", () => {
    pages.forEach((p) => { if (p.mounted && typeof p.def.unmount === "function") { try { p.def.unmount(); } catch (e) { /* closing */ } } });
  });
  if ("ResizeObserver" in window) new ResizeObserver(() => fitNav()).observe(document.documentElement);
  else window.addEventListener("resize", fitNav);
  boot();
})();
