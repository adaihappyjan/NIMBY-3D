/* The guide page of Nimby3D, in English and Chinese. Rendered by app.js.
   Blocks: ["p", text] ["steps", [text...]] ["bullets", [text...]] ["note"|"ok"|"warn", text] ["h3", text]
   ["keys", caption, [[[keys...], text], ...]] ["swatches", [[colour, text], ...]] ["goto", view or page-id word, label].
   A section with requires: "<word>" shows only when a registered page's id has that word in it.
   In text: **bold**, `code`. Keys: "Ctrl+F8" (pressed together), "W A S D" (each), "~text" (a mouse action);
   several in a row are alternatives. */
"use strict";
window.N3D_GUIDE = {
  en: [
    { id: "what", icon: "i-cube", title: "What Nimby3D is", body: [
      ["p", "Nimby3D shows the NIMBY Rails map in **3D**, right inside the game's own window: the terrain, the track on the ground, on viaducts and in tunnels, the stations and the trains."],
      ["p", "It is an add-on for **ReShade**, a free tool that the game loads when it starts. This program installs ReShade and the add-on into the game folder, exports what the add-on needs from your save (stations, track, terrain), keeps that data up to date, and removes everything again when you want."],
      ["p", "Trains use Nimby3D's own models or the 3D models of the train mods you use in the game. No third-party models are bundled."],
    ] },
    { id: "start", icon: "i-play", title: "Getting started", body: [
      ["steps", [
        "On the **Home** page, click **Install & Play**. Nimby3D finds the game through Steam, installs ReShade and the add-on, exports stations, track and terrain from your newest save, and starts NIMBY Rails.",
        "The map turns 3D (**F8** switches between 2D and 3D). Next time, click **Play** in Nimby3D, or start the game from Steam as usual.",
        "After you change your network, click **Refresh save data**, or turn on **Auto-sync saves**: while Nimby3D is open it refreshes the data a few seconds after every save, autosaves included. New track shows at once; its platforms and signals come with the next refresh.",
      ]],
      ["note", "Installing or updating while the game runs works, but takes effect the next time the game starts. **Disable** and **Uninstall** need the game closed."],
    ] },
    { id: "keys", icon: "i-keyboard", title: "In-game controls", body: [
      ["keys", "The 3D view", [
        [["F8"], "3D view on / off"],
        [["~Middle-button drag"], "Turn and tilt the view; drag back up to return to 2D"],
        [["~Right-button drag", "W A S D"], "Pan"],
        [["~Mouse wheel"], "Zoom about the cursor"],
        [["Ctrl+F8"], "Terrain exaggeration: 1×, 2×, 3×, 5×"],
        [["Shift+F8"], "Show / hide what is underground"],
        [["Ctrl+Shift+F8"], "Weather"],
        [["Ctrl+F9"], "Station markers"],
        [["Ctrl+Shift+F9"], "Sound"],
        [["F10"], "The Nimby3D settings panel in the game (F10 or Esc closes it)"],
        [["F12"], "Screenshot (Steam's key)"],
      ]],
      ["keys", "First and third person", [
        [["Ctrl+F10"], "First person: walk around the map"],
        [["W A S D"], "Walk"],
        [["Shift"], "Run"],
        [["Space"], "Jump. In first person, Space does not pause the game"],
        [["~Mouse wheel"], "Zoom the eye"],
        [["C", "Shift+F10"], "Third person, behind your figure"],
        [["R"], "Get on / off the car beside you"],
      ]],
      ["note", "With the settings Nimby3D writes, ReShade's own menu opens with **Shift+F2**."],
    ] },
    { id: "packs", icon: "i-sparkles", title: "Shader packs", body: [
      ["p", "Nimby3D can draw the 3D view with Minecraft shader packs made for **Iris** or **OptiFine**. This is experimental, works on **NVIDIA** graphics cards only for now, and is off by default."],
      ["h3", "The Shader packs page"],
      ["steps", [
        "Open the **Shader packs** page (at the top). It lists the packs in `%APPDATA%\\.minecraft\\shaderpacks`, the folder Minecraft uses. Add one with **Add a .zip…** or **Add a folder…** (a pack has a `shaders` folder inside), or put it there yourself.",
        "Click **Use** beside a pack and turn on **Draw the 3D view with a shader pack**. Nimby3D writes the choice into `nimby3d.ini` in the game folder.",
        "Start the game: the pack is used from the next start. While the game runs you can also pick it in the game: **F10** → **Picture** → **Minecraft shader pack (experimental)**.",
      ]],
      ["p", "**Options** opens the pack's own settings, grouped the way the pack groups them, with its profiles and a search box. Only what differs from the defaults is saved, and each pack keeps its own options when you switch between packs. Values marked **Nimby3D** are set by the add-on itself for NIMBY's scale (shadow range, cloud height…); change them to use your own."],
      ["ok", "Removing a pack moves it to the Recycle Bin, so it can always be restored."],
      ["goto", "packs", "Open the Shader packs page"],
    ] },
    { id: "settings", icon: "i-sliders", title: "Add-on settings", body: [
      ["p", "The **Add-on settings** page has every setting of the panel in the game (**F10**), on the same pages: performance, picture, world, railway, stations, controls, time and sound. A change goes into `nimby3d.ini` in the game folder and takes effect the next time the game starts."],
      ["bullets", [
        "The search box finds a setting by its name or its explanation; **Changed** lists the settings that differ from their defaults.",
        "The ↺ button beside a setting puts it back to its default; **Reset all** puts every setting back.",
        "Settings marked **Restart** take effect only after a restart, even when changed in the game's panel.",
        "Only the lines of the settings you change are written: comments, the shader pack and its options and anything else in the file stay as they are.",
      ]],
      ["warn", "While the game runs, its panel writes `nimby3d.ini` again whenever you change something there, with the game's own values. Change settings here with the game closed."],
      ["h3", "Where things are"],
      ["bullets", [
        "`nimby3d.ini` (game folder): the add-on's settings.",
        "`nimby3d_stations.txt` (game folder): settings of single stations (foundation, raise, footbridge), made in the game: **F10** → **Stations**, for the station in the middle of the view.",
        "`nimby3d_probe.log` and `ReShade.log` (game folder): the logs, also in the Activity panel on the Home page.",
        "`%LOCALAPPDATA%\\Nimby3D`: this program's own settings and the options it remembers for each shader pack.",
      ]],
      ["goto", "settings", "Open the Add-on settings page"],
    ] },
    { id: "look", icon: "i-palette", title: "Appearance", body: [
      ["p", "The palette button at the top right picks a look for Nimby3D: **Classic**, **Lazy Afternoon**, **Sleepy** or **Night Shift**, each with its own colours and a picture of Nimby3D-chan, the mascot. Light or dark still switches with the button beside it."],
      ["p", "**Replace picture…** puts a picture of your own into a look (PNG, WebP or JPG, up to 8 MB, a commissioned drawing for instance); **Restore default** takes it out again. The pictures of Nimby3D-chan that come with Nimby3D are AI-generated (OpenAI image generation)."],
    ] },
    { id: "trains", icon: "i-train", title: "Train editor", requires: "train", body: [
      ["p", "The **Train editor** page works on the 3D models of trains that Nimby3D draws for your train mods (from the Steam Workshop or your local mods folder). The page itself explains each step."],
      ["goto", "train", "Open the Train editor"],
    ] },
    { id: "figure", icon: "i-user", title: "Your figure", body: [
      ["p", "In third person you see yourself as a 3D figure: standing on platforms, walking, riding trains. Nimby3D uses a **VRM model** (.vrm) of your choice."],
      ["steps", [
        "On the Home page, under **Player figure**, click **Choose VRM model…** and pick the file.",
        "Start (or restart) the game. Press **Ctrl+F10** for first person, then **C** for third person.",
      ]],
      ["ok", "The model is copied only into your own game folder and is never uploaded or shared. Models belong to their authors: follow their terms of use. **Remove** takes it out of the game folder again."],
    ] },
    { id: "uninstall", icon: "i-trash", title: "Uninstalling", body: [
      ["p", "**Uninstall & delete** on the Home page removes exactly the files Nimby3D put into the game folder; the confirmation lists them first. A dxgi.dll or ReShade settings that were there before are left alone, and **your saves are never changed**."],
      ["p", "Tick the box in the confirmation to also delete the add-on's own settings and what it learned (nimby3d.ini, nimby3d_units.txt, frame dumps)."],
      ["p", "**Disable** keeps the files but lets the game start without ReShade and the add-on; **Enable** turns them back on. Disable and Uninstall need the game closed."],
    ] },
    { id: "trouble", icon: "i-help", title: "Troubleshooting", body: [
      ["h3", "The status square"],
      ["p", "A small square at the bottom left of the game window shows what the add-on is doing:"],
      ["swatches", [["#ef4444", "Red: finding where the view is on the map"], ["#22c55e", "Green: found the place"], ["#22d3ee", "Cyan: showing 3D"], ["#f59e0b", "Orange: 3D, but the place is not known"]]],
      ["h3", "Logs"],
      ["p", "The **Add-on log** and **ReShade log** tabs in the Activity panel on the Home page show the last lines of `nimby3d_probe.log` and `ReShade.log` from the game folder. The folder button next to them opens the file in Explorer."],
      ["h3", "Nothing changes in the game?"],
      ["bullets", [
        "Check that the Home page says **Enabled**. After Disable, click **Enable**.",
        "Press **F8**: the 3D view may simply be switched off.",
        "Restart the game after installing; changes take effect at the next start.",
        "If Nimby3D reports another program's dxgi.dll, it will not overwrite it. Remove that ReShade first if you want Nimby3D's.",
      ]],
    ] },
  ],
  zh: [
    { id: "what", icon: "i-cube", title: "Nimby3D 是什么", body: [
      ["p", "Nimby3D 让 NIMBY Rails 的地图直接在游戏自己的窗口里以 **3D** 显示：地形，地面、高架和隧道里的轨道，车站和列车。"],
      ["p", "它是 **ReShade** 的一个插件（ReShade 是游戏启动时加载的免费工具）。这个程序把 ReShade 和插件装进游戏文件夹，从你的存档导出插件需要的数据（车站、轨道、地形）并保持更新，需要时再把它们全部删除。"],
      ["p", "列车使用 Nimby3D 自带的模型，或你在游戏里使用的列车模组的 3D 模型。不附带任何第三方模型。"],
    ] },
    { id: "start", icon: "i-play", title: "开始使用", body: [
      ["steps", [
        "在 **主页** 点 **安装并开始游戏**。Nimby3D 会通过 Steam 找到游戏，安装 ReShade 和插件，从你最新的存档导出车站、轨道和地形，然后启动 NIMBY Rails。",
        "地图会变成 3D（**F8** 在 2D 和 3D 之间切换）。以后在 Nimby3D 里点 **开始游戏**，或者像平常一样从 Steam 启动游戏。",
        "修改线路后点 **更新存档数据**，或者打开 **自动同步存档**：Nimby3D 开着时，游戏每次存档（包括自动存档）后几秒内自动更新数据。新建的轨道会立即显示，它的站台和信号机在下次更新后出现。",
      ]],
      ["note", "游戏运行时也可以安装或更新，但要到下次启动游戏才生效。**停用** 和 **卸载** 需要先关闭游戏。"],
    ] },
    { id: "keys", icon: "i-keyboard", title: "游戏内操作", body: [
      ["keys", "3D 视图", [
        [["F8"], "打开 / 关闭 3D 视图"],
        [["~中键拖动"], "转动和倾斜视角；向上拖回去即回到 2D"],
        [["~右键拖动", "W A S D"], "平移"],
        [["~滚轮"], "以鼠标位置为中心缩放"],
        [["Ctrl+F8"], "地形夸张：1×、2×、3×、5×"],
        [["Shift+F8"], "显示 / 隐藏地下部分"],
        [["Ctrl+Shift+F8"], "天气"],
        [["Ctrl+F9"], "车站标记"],
        [["Ctrl+Shift+F9"], "声音"],
        [["F10"], "游戏里的 Nimby3D 设置面板（F10 或 Esc 关闭）"],
        [["F12"], "截图（Steam 的按键）"],
      ]],
      ["keys", "第一人称与第三人称", [
        [["Ctrl+F10"], "第一人称：在地图上行走"],
        [["W A S D"], "行走"],
        [["Shift"], "奔跑"],
        [["Space"], "跳跃。第一人称时空格不会暂停游戏"],
        [["~滚轮"], "拉近 / 拉远视线"],
        [["C", "Shift+F10"], "第三人称，镜头在你的人物身后"],
        [["R"], "上 / 下旁边的那节车"],
      ]],
      ["note", "按 Nimby3D 写入的设置，ReShade 自己的菜单用 **Shift+F2** 打开。"],
    ] },
    { id: "packs", icon: "i-sparkles", title: "光影包", body: [
      ["p", "Nimby3D 可以用为 **Iris** 或 **OptiFine** 制作的 Minecraft 光影包来渲染 3D 视图。这是实验功能，目前只支持 **NVIDIA** 显卡，默认关闭。"],
      ["h3", "“光影包”页"],
      ["steps", [
        "打开顶部的 **光影包** 页。它列出 `%APPDATA%\\.minecraft\\shaderpacks`（Minecraft 用的那个文件夹）里的光影包。用 **添加 .zip…** 或 **添加文件夹…** 添加光影包（光影包里面有 `shaders` 文件夹），也可以自己放进那个文件夹。",
        "在光影包旁边点 **使用**，并打开 **用光影包画三维视图**。Nimby3D 会把选择写进游戏文件夹的 `nimby3d.ini`。",
        "启动游戏：从下次启动开始使用这个光影包。游戏运行时也可以在游戏里选：**F10** →“画面”→“Minecraft 光影包（实验）”。",
      ]],
      ["p", "**选项** 打开光影包自己的设置，按光影包自己的分组排列，带预设和搜索框。只保存和默认不同的选项；在光影包之间切换时，每个光影包的选项都会记住。标着 **Nimby3D** 的值是插件为 NIMBY 的尺度自己设的（阴影范围、云的高度等），改了就用你选的值。"],
      ["ok", "移除光影包时会把它移到回收站，随时可以还原。"],
      ["goto", "packs", "打开“光影包”页"],
    ] },
    { id: "settings", icon: "i-sliders", title: "插件设置", body: [
      ["p", "**插件设置** 页有游戏里设置面板（**F10**）的全部设置，按同样的分页排列：性能、画面、世界、铁路、车站、操作、时间与声音。改动写进游戏文件夹的 `nimby3d.ini`，下次启动游戏时生效。"],
      ["bullets", [
        "搜索框按名字或说明查找设置；**改过的** 列出和默认值不同的设置。",
        "设置旁边的 ↺ 按钮把它恢复默认；**全部恢复默认** 恢复所有设置。",
        "标着 **需重启** 的设置，即使在游戏面板里改，也要重启游戏才生效。",
        "只写你改动的那几行：注释、光影包的选择和选项，以及文件里的其他内容都保持原样。",
      ]],
      ["warn", "游戏运行时，在游戏面板里改任何设置，它都会用游戏里的值重新写 `nimby3d.ini`。请在关闭游戏时在这里改设置。"],
      ["h3", "文件在哪里"],
      ["bullets", [
        "`nimby3d.ini`（游戏文件夹）：插件的设置。",
        "`nimby3d_stations.txt`（游戏文件夹）：单个车站的设置（地基、抬高、天桥），在游戏里设：**F10** →“车站”，对着视野中间的车站。",
        "`nimby3d_probe.log` 和 `ReShade.log`（游戏文件夹）：日志，主页的活动面板里也能看。",
        "`%LOCALAPPDATA%\\Nimby3D`：这个程序自己的设置，以及给每个光影包记住的选项。",
      ]],
      ["goto", "settings", "打开“插件设置”页"],
    ] },
    { id: "look", icon: "i-palette", title: "外观", body: [
      ["p", "右上角的调色板按钮可以给 Nimby3D 选外观：**经典**、**午后**、**困困** 或 **夜班**，各有自己的配色和吉祥物 Nimby3D酱的立绘。浅色 / 深色仍然用旁边的按钮切换。"],
      ["p", "**换图…** 可以给一套外观换上你自己的图（PNG、WebP 或 JPG，最大 8 MB，比如约稿的立绘）；**恢复默认图** 再换回来。Nimby3D 自带的 Nimby3D酱 立绘是 AI 生成的（OpenAI 图像生成）。"],
    ] },
    { id: "trains", icon: "i-train", title: "列车编辑器", requires: "train", body: [
      ["p", "**列车编辑器** 页用来处理 Nimby3D 为你的列车模组（Steam 创意工坊或本地模组文件夹里的）画的列车 3D 模型。页面里会说明每一步。"],
      ["goto", "train", "打开列车编辑器"],
    ] },
    { id: "figure", icon: "i-user", title: "你的人物", body: [
      ["p", "第三人称时你能看到自己的 3D 人物：站在站台上、走路、乘车。Nimby3D 使用你选择的 **VRM 模型**（.vrm）。"],
      ["steps", [
        "在主页的 **人物模型** 卡片里点 **选择 VRM 模型…**，选中文件。",
        "启动（或重启）游戏。按 **Ctrl+F10** 进入第一人称，再按 **C** 切到第三人称。",
      ]],
      ["ok", "模型只会复制到你自己的游戏文件夹，不会上传或分享。模型的版权归原作者所有，请遵守作者的使用条款。点 **移除** 即可把它从游戏文件夹删掉。"],
    ] },
    { id: "uninstall", icon: "i-trash", title: "卸载", body: [
      ["p", "主页上的 **卸载并删除** 只删除 Nimby3D 放进游戏文件夹的文件，删除前会列出确切的清单。原本就有的 dxgi.dll 或 ReShade 设置保持不动，**存档永远不会被修改**。"],
      ["p", "在确认窗口里勾选复选框，可以同时删除插件自己的设置和学习到的数据（nimby3d.ini、nimby3d_units.txt、截图转储）。"],
      ["p", "**停用** 保留文件，但游戏启动时不加载 ReShade 和插件；**启用** 再把它们打开。停用和卸载需要先关闭游戏。"],
    ] },
    { id: "trouble", icon: "i-help", title: "疑难解答", body: [
      ["h3", "状态方块"],
      ["p", "游戏窗口左下角的小方块显示插件当前的状态："],
      ["swatches", [["#ef4444", "红色：正在寻找视野在地图上的位置"], ["#22c55e", "绿色：已找到位置"], ["#22d3ee", "青色：正在显示 3D"], ["#f59e0b", "橙色：3D 已开启，但位置未知"]]],
      ["h3", "日志"],
      ["p", "主页底部活动面板里的 **插件日志** 和 **ReShade 日志** 标签页显示游戏文件夹中 `nimby3d_probe.log` 和 `ReShade.log` 的最后几行；旁边的文件夹按钮可在资源管理器中打开它们。"],
      ["h3", "游戏里没有变化？"],
      ["bullets", [
        "确认主页显示 **已启用**；停用过的话点 **启用**。",
        "按 **F8**：3D 视图可能只是被关掉了。",
        "安装后要重新启动游戏才会生效。",
        "如果 Nimby3D 提示有别的程序的 dxgi.dll，它不会覆盖；想用 Nimby3D 的话先移除那个 ReShade。",
      ]],
    ] },
  ],
};
