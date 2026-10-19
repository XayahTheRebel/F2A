# 逐帧 Frameflow

把一组 PNG 序列帧转换为动态 WebP 的本地小应用。中文界面，图片只在本机浏览器和本机转换器之间传输，不会上传到云端。

## 启动

**Windows 便携版：**双击 `dist/Frameflow.exe`，浏览器会自动打开。便携版不需要安装 Python。点击页面底部「退出应用」或关闭启动窗口即可退出。

**从源码运行：**安装 Python 3.11 或更新版本，双击 `start.bat`。首次运行会检查并安装 Pillow；已有依赖时可离线使用。也可以手动执行：

```powershell
python -m pip install -r requirements.txt
python app.py
```

默认地址为 <http://127.0.0.1:8765>。端口被占用时会自动选择空闲端口，以启动窗口打印的地址为准。

## 使用

1. 拖入多张 PNG，或点击「导入 PNG」。默认按文件名自然排序，例如 `frame_1.png`、`frame_2.png`、`frame_10.png`。
2. 在底部点击帧进行定位；拖动缩略图或使用箭头按钮调整顺序。支持反转、重新排序、删除选中帧和清空序列。
3. 设置帧率、压缩方式、缩放比例和循环次数，点击「生成动态 WebP」。
4. 在「导出结果」中检查实际生成的动画，再点击「下载 WebP」。修改转换设置或序列后，旧结果自动失效。

没有素材时，可以点击「试试示例动画」。支持空格播放／暂停，左右方向键逐帧查看；焦点在输入框和按钮上时保留原有键盘操作。

- **有损压缩**：建议画质 80–90。透明度保留，颜色会按画质设置压缩。
- **无损压缩**：保留输出画布上的可见像素画质，画质滑块不参与编码。缩放本身仍会重采样像素。完全透明区域的不可见 RGB 值可能被编码器优化。
- **循环次数**：无限循环、播放一次或播放三次。序列预览会使用当前设置。
- **透明背景**：网格、浅色、深色仅用于预览，不会写进导出的文件。
- **时长**：按帧率分配毫秒级帧时长，将总时长误差控制在约 1 ms 内。

单张 PNG 会导出为静态 WebP。编码器可能合并相邻相同帧，同时保留总播放时长；界面的帧数显示导入帧数。

## 范围与限制

- 一次最多 500 帧，PNG 文件合计最多 128 MiB。
- 所有帧需要尺寸一致，单张最多 1600 万像素；输入应为单张 PNG，不能使用 APNG。
- 输出画布单边不超过 16383 像素；转换时的帧像素缓冲预算为 256 MiB，实际进程内存还包括压缩数据和编码器。超过时可降低输出比例或减少帧数。
- 同一时间执行一个转换任务。大尺寸序列和无损编码可能需要更多时间。
- 程序只监听 `127.0.0.1`，使用启动窗口给出的地址访问。没有在线服务、账号或持久化素材库。

## 开发与验证

`app.py` 提供本地 HTTP 服务；`converter.py` 处理文件验证、帧时长和 WebP 编码；`static/` 是无外部依赖的原生 HTML/CSS/JavaScript 界面。

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
node --check static/app.js
```

可选的浏览器检查需要 Playwright 及 Chromium。测试程序会自行启动隔离的本机服务，并在结束时关闭：

```powershell
python tests/run_browser.py
# 验证打包后的程序
python tests/run_browser.py --exe dist/Frameflow.exe
```

测试覆盖透明度、帧序、累计时长、循环次数、缩放、无损画质、非法输入、浏览器导入与下载、手动调序和窄屏布局。浏览器测试截图及样例 WebP 存放在已忽略的 `test-results/`。

## 打包 Windows 便携版

在 Windows 上双击 `build.bat`，或执行：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --name Frameflow --exclude-module numpy --add-data "static;static" app.py
```

产物为 `dist/Frameflow.exe`。可执行文件、构建缓存和用户素材不纳入 Git。

本次功能在 `feat/png-to-webp` 分支开发，效果确认后再合并到 `main`。
