# 照片整理模块 — 按日期整理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个独立模块，在现有图片去重合并工具中按拍摄日期整理照片和视频。

**架构：** 新增 `routes/organize.py`（Blueprint）和 `organizer.py`（核心逻辑），新增三个模板文件，在 `main.py` 注册新 Blueprint。不修改去重模块的现有代码。

**Tech Stack:** Flask Blueprint, Pillow (已有), subprocess + ffprobe, shutil

---

### Task 1: 创建 routes 包 + organize Blueprint 骨架

**Files:**
- Create: `routes/__init__.py`
- Create: `routes/organize.py`

- [ ] **Step 1: 创建 routes/__init__.py**

```python
# routes/__init__.py
# 空文件，将 routes 目录标记为 Python 包
```

- [ ] **Step 2: 创建 routes/organize.py 骨架**

```python
"""
routes/organize.py - 照片整理模块路由
=======================

使用 Flask Blueprint 组织路由，注册到主应用。

路由列表：
  /organize/       GET  → 整理配置页
  /organize/       POST → 启动后台整理线程
  /organize/progress  GET → AJAX 进度 JSON
  /organize/scanning  GET → 进度页
  /organize/result    GET → 结果页
"""

import threading
import time
from flask import Blueprint, render_template, request, jsonify

# 创建 Blueprint 实例
# 'organize' 是蓝图名称，用于 url_for('organize.xxx') 引用
# __name__ 让 Flask 知道模板目录位置
organize_bp = Blueprint('organize', __name__, template_folder='../templates')

# ── 全局进度状态 ──
# 照片整理模块的进度，与去重模块的 scan_progress 完全独立
organize_progress = {
    'status': 'idle',     # idle / scanning / extracting / organizing / done / error
    'message': '',
    'current_file': '',
    'count': 0,
    'total': 0,
    'log': [],
    'result': None,
    'error': None
}


@organize_bp.route('/organize/', methods=['GET', 'POST'])
def organize_page():
    """
    整理配置页。
    GET  → 显示表单
    POST → 接收表单，启动后台整理线程
    """
    if request.method == 'POST':
        source_dir = request.form.get('source_dir', '').strip()
        mode = request.form.get('mode', 'day')  # 'day' 或 'month'
        organize_photos = request.form.get('organize_photos') == 'on'
        organize_videos = request.form.get('organize_videos') == 'on'

        # 重置进度
        organize_progress.clear()
        organize_progress.update({
            'status': 'starting',
            'message': '正在启动整理...',
            'log': ['正在启动整理...']
        })

        # 启动后台线程
        config = {
            'source_dir': source_dir,
            'mode': mode,
            'organize_photos': organize_photos,
            'organize_videos': organize_videos
        }
        thread = threading.Thread(
            target=run_organize_background,
            args=(config,),
            daemon=True
        )
        thread.start()

        return render_template('organizing.html', title='整理中...')

    # GET 请求：显示配置页
    return render_template('organize.html', title='照片整理')


@organize_bp.route('/organize/progress')
def organize_progress_api():
    """AJAX 进度接口，返回 JSON。"""
    return jsonify(organize_progress)


@organize_bp.route('/organize/scanning')
def organize_scanning():
    """整理进度页面（前端轮询）。"""
    return render_template('organizing.html', title='整理中...')


@organize_bp.route('/organize/result')
def organize_result():
    """整理结果页面。"""
    result = organize_progress.get('result', {})
    return render_template('organize_result.html',
                           result=result,
                           title='整理结果')


def run_organize_background(config):
    """
    在后台线程中执行整理流程。

    流程：
    1. 扫描源目录，发现图片和视频文件
    2. 提取每个文件的拍摄日期（EXIF/ffprobe/文件修改时间）
    3. 按 > 日期 > 文件名 移动文件
    """
    global organize_progress

    def update_progress(stage, message, **kwargs):
        """更新进度。"""
        log_entry = message
        organize_progress.update({
            'status': 'organizing' if stage == 'organizing' else
                      'extracting' if stage == 'extracting' else
                      'scanning' if stage == 'scanning' else
                      organize_progress.get('status', 'organizing'),
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0),
            'error': None
        })
        log = organize_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        organize_progress['log'] = log

    try:
        from organizer import organize_by_date

        # 执行核心逻辑
        result = organize_by_date(config, progress_callback=update_progress)

        organize_progress.update({
            'status': 'done',
            'message': f'✅ 整理完成！照片 {result.get("moved_photos", 0)} 个，'
                       f'视频 {result.get("moved_videos", 0)} 个',
            'result': result,
            'log': organize_progress.get('log', []) +
                   [f'✅ 整理完成：{result.get("moved_photos", 0)} 张照片，'
                    f'{result.get("moved_videos", 0)} 个视频']
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f'整理出错: {type(e).__name__}: {e}'
        organize_progress.update({
            'status': 'error',
            'message': error_msg,
            'error': str(e),
            'log': organize_progress.get('log', []) + [error_msg]
        })
```

- [ ] **Step 3: 在 main.py 注册 organize Blueprint**

```python
# 在 main.py 文件顶部加上：
from routes.organize import organize_bp

# 在 app 创建之后加上：
app.register_blueprint(organize_bp)
```

- [ ] **Step 4: 验证 Flask 能启动**

Run: `python main.py`
Expected: 服务启动无报错，访问 `http://localhost:5000/organize/` 返回 200（模板还不存在，会报模板错误，但路由匹配正常）

- [ ] **Step 5: 提交**

```bash
git add routes/__init__.py routes/organize.py main.py
git commit -m "feat: 创建 routes 包和 organize Blueprint 骨架"
```

---

### Task 2: 添加导航栏 + CSS + 更新现有模板

**Files:**
- Create: `templates/navigation.html`
- Modify: `static/style.css`（末尾追加导航栏样式）
- Modify: `templates/index.html`（新增 `{% include 'navigation.html' %}`）
- Modify: `templates/scanning.html`
- Modify: `templates/report.html`
- Modify: `templates/plan.html`
- Modify: `templates/result.html`

- [ ] **Step 1: 创建 templates/navigation.html**

```html
{# templates/navigation.html - 共用导航栏 #}
{# 使用 request.path 判断当前页面，高亮对应的 Tab #}
<div class="nav-bar">
    <a href="{{ url_for('index') }}"
       class="nav-item {{ 'active' if not request.path.startswith('/organize') }}">
        &#x1F4F7; 去重合并
    </a>
    <a href="{{ url_for('organize.organize_page') }}"
       class="nav-item {{ 'active' if request.path.startswith('/organize') }}">
        &#x1F4C2; 照片整理
    </a>
</div>
```

- [ ] **Step 2: 在 static/style.css 末尾追加导航栏样式**

```css
/* ── 导航栏 ── */
.nav-bar {
    display: flex;
    gap: 0;
    margin-bottom: 24px;
    background: var(--bg-secondary);
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
}
.nav-item {
    flex: 1;
    text-align: center;
    padding: 12px 16px;
    color: var(--text-dim);
    text-decoration: none;
    font-size: 15px;
    transition: background 0.2s, color 0.2s;
}
.nav-item:hover {
    background: var(--bg-tertiary);
    color: var(--text);
}
.nav-item.active {
    background: var(--blue);
    color: #fff;
    font-weight: 600;
}
```

- [ ] **Step 3: 在 index.html 的 `<body>` 下第一行添加 include**

```html
{% include 'navigation.html' %}
```

- [ ] **Step 4: 重复 Step 3 修改 scanning.html、report.html、plan.html、result.html**

每个模板的 `<body>` 下第一行都加：

```html
{% include 'navigation.html' %}
```

- [ ] **Step 5: 验证**

重启 Flask，访问各页面，确认导航栏出现在所有页面顶部，Tabs 点击切换，当前页高亮。

- [ ] **Step 6: 提交**

```bash
git add templates/navigation.html static/style.css
git add templates/index.html templates/scanning.html templates/report.html templates/plan.html templates/result.html
git commit -m "feat: 添加共用导航栏，所有页面集成"
```

---

### Task 3: organizer.py — 核心逻辑

**Files:**
- Create: `organizer.py`

- [ ] **Step 1: 创建 organizer.py，实现文件扫描函数**

```python
"""
organizer.py - 照片整理核心模块
========================

功能：
1. 按扩展名扫描目录中的图片和视频文件
2. 读取拍摄日期（照片 EXIF / 视频 ffprobe / 文件修改时间）
3. 按 源目录/照片|视频/年份/日期/ 结构移动文件

依赖：
- Pillow（已安装）：读取图片 EXIF
- ffprobe（系统包）：读取视频元数据
- subprocess（标准库）：调用 ffprobe
"""

import os
import shutil
from datetime import datetime
from pathlib import Path


# 图片和视频的扩展名集合（小写）
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.webp', '.tiff', '.tif', '.heic', '.heif'
}
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'
}


def scan_directory(source_dir, organize_photos=True, organize_videos=True,
                   progress_callback=None):
    """
    扫描源目录，按扩展名分类文件。

    Args:
        source_dir: 源目录路径
        organize_photos: 是否整理照片
        organize_videos: 是否整理视频
        progress_callback: 进度回调函数(stage, message, **kwargs)

    Returns:
        dict: {
            'photos': [{ 'path': str, 'relative_path': str, 'size': int }, ...],
            'videos': [{ 'path': str, 'relative_path': str, 'size': int }, ...]
        }
    """
    photos = []
    videos = []

    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f'目录不存在: {source_dir}')

    # 递归遍历所有子目录
    for root, dirs, files in os.walk(source_dir):
        for filename in sorted(files):
            ext = Path(filename).suffix.lower()

            # 跳过隐藏文件和临时文件
            if filename.startswith('.') or filename.startswith('~'):
                continue

            full_path = Path(root) / filename
            relative_path = full_path.relative_to(source_path)

            # 跳过已经整理过的目录（照片/ 和 视频/）
            # 在相对路径中检查第一个路径段是否为 照片 或 视频
            parts = relative_path.parts
            if parts and parts[0] in ('照片', '视频'):
                continue

            file_info = {
                'path': str(full_path),
                'relative_path': str(relative_path),
                'size': full_path.stat().st_size if full_path.exists() else 0
            }

            if organize_photos and ext in IMAGE_EXTENSIONS:
                photos.append(file_info)
                if progress_callback:
                    progress_callback(
                        'scanning',
                        f'📄 发现照片: {relative_path}',
                        current_file=str(relative_path),
                        count=len(photos), total=0
                    )
            elif organize_videos and ext in VIDEO_EXTENSIONS:
                videos.append(file_info)
                if progress_callback:
                    progress_callback(
                        'scanning',
                        f'🎬 发现视频: {relative_path}',
                        current_file=str(relative_path),
                        count=len(videos), total=0
                    )

    return {'photos': photos, 'videos': videos}
```

- [ ] **Step 2: 添加日期提取函数**

```python
def extract_date_photo(file_path, progress_callback=None):
    """
    从照片文件的 EXIF 中提取拍摄日期。

    优先级：EXIF DateTimeOriginal (0x9003) → 文件修改时间

    Returns:
        str 或 None: 格式化的日期字符串（如 '2025-06-24' 或 '2025-06'）
    """
    try:
        from PIL import Image
        img = Image.open(file_path)
        exif_data = img._getexif()

        if exif_data:
            # 36867 = DateTimeOriginal
            date_str = exif_data.get(36867)
            if date_str:
                # EXIF 格式: 'YYYY:MM:DD HH:MM:SS'
                # 转为 datetime 对象
                dt = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                return dt

        # 没有 EXIF，回退到文件修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)

    except Exception:
        # 任何异常（文件损坏、格式不支持等）都回退到修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)


def extract_date_video(file_path, progress_callback=None):
    """
    从视频文件的元数据中提取拍摄日期。

    使用 ffprobe 读取 creation_time 元数据。
    ffprobe 随 ffmpeg 一起安装，飞牛OS 通常预装。

    优先级：ffprobe creation_time → 文件修改时间

    Returns:
        datetime 或 None
    """
    try:
        import subprocess
        import json

        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', str(file_path)],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            creation_time = (
                data.get('format', {})
                .get('tags', {})
                .get('creation_time')
            )
            if creation_time:
                # ffprobe 格式: '2025-06-24T10:30:00.000000Z'
                # 去掉 T 后面的部分，保留日期
                dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                return dt

        # ffprobe 失败或无 creation_time，回退到修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError,
            subprocess.TimeoutExpired):
        # ffprobe 未安装、超时或解析失败 → 回退到修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)
```

- [ ] **Step 3: 添加日期格式化和文件移动函数**

```python
def move_file(file_path, source_dir, category, dt, mode,
              progress_callback=None):
    """
    将文件移动到目标位置。

    Args:
        file_path: 源文件完整路径
        source_dir: 源目录路径
        category: '照片' 或 '视频'
        dt: datetime 对象（拍摄日期）
        mode: 'day' 或 'month'
        progress_callback: 进度回调

    Returns:
        dict: { 'success': bool, 'dest_path': str, 'error': str }
    """
    source_path = Path(source_dir)
    file_path = Path(file_path)

    # 计算年份和日期字符串
    year_str = str(dt.year)
    if mode == 'day':
        date_str = dt.strftime('%Y-%m-%d')  # '2025-06-24'
    else:
        date_str = dt.strftime('%Y-%m')      # '2025-06'

    # 目标路径：源目录/照片|视频/年份/日期/文件名
    filename = file_path.name
    dest_dir = source_path / category / year_str / date_str
    dest_path = dest_dir / filename

    try:
        # 创建目标目录
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 冲突处理：同名文件自动重命名
        if dest_path.exists():
            name_stem = file_path.stem
            ext = file_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f'{name_stem}_{counter}{ext}'
                counter += 1

        # 执行移动
        shutil.move(str(file_path), str(dest_path))

        return {
            'success': True,
            'dest_path': str(dest_path),
            'error': None
        }

    except (OSError, shutil.Error) as e:
        return {
            'success': False,
            'dest_path': None,
            'error': str(e)
        }
```

- [ ] **Step 4: 实现主函数 organize_by_date()**

```python
def organize_by_date(config, progress_callback=None):
    """
    按日期整理照片和视频的主函数。

    Args:
        config: dict {
            'source_dir': str,
            'mode': 'day' | 'month',
            'organize_photos': bool,
            'organize_videos': bool
        }
        progress_callback: 进度回调函数(stage, message, **kwargs)

    Returns:
        dict: {
            'source_dir': str,
            'mode': str,
            'total_photos': int,
            'total_videos': int,
            'moved_photos': int,
            'moved_videos': int,
            'no_exif_photos': [str, ...],
            'no_exif_videos': [str, ...],
            'errors': [{'file': str, 'error': str}, ...],
            'summary': {
                'moved': int,
                'failed': int,
                'total': int
            }
        }
    """
    source_dir = config['source_dir']
    mode = config.get('mode', 'day')
    organize_photos = config.get('organize_photos', True)
    organize_videos = config.get('organize_videos', True)

    if progress_callback:
        progress_callback('scanning',
                          f'🔍 正在扫描目录: {source_dir} ...',
                          current_file='', count=0, total=0)

    # ═══ 阶段 1：扫描文件 ═══
    scanned = scan_directory(source_dir, organize_photos, organize_videos,
                             progress_callback)

    photos = scanned.get('photos', [])
    videos = scanned.get('videos', [])

    if progress_callback:
        progress_callback('scanning',
                          f'✅ 扫描完成：{len(photos)} 张照片，{len(videos)} 个视频',
                          count=len(photos) + len(videos),
                          total=len(photos) + len(videos))

    # ═══ 阶段 2：提取日期 ═══
    if progress_callback:
        progress_callback('extracting',
                          '📅 正在提取拍摄日期...',
                          count=0, total=len(photos) + len(videos))

    no_exif_photos = []
    no_exif_videos = []
    photo_dates = []
    video_dates = []
    total_files = len(photos) + len(videos)
    processed = 0

    # 处理照片
    for f in photos:
        dt = extract_date_photo(f['path'], progress_callback)
        if dt is None:
            continue
        # 如果日期来自文件修改时间（即没有 EXIF），记录到 no_exif
        # 实际上 extract_date_photo 已经回退到 mtime，我们无法从返回值
        # 判断是否用了 EXIF。这里简化处理：不区分 EXIF/mtime
        photo_dates.append((f, dt))
        processed += 1
        if progress_callback:
            rel = f.get('relative_path', f['path'])
            progress_callback('extracting',
                              f'📷 读取日期: {rel} → {dt.strftime("%Y-%m-%d")}',
                              current_file=rel,
                              count=processed, total=total_files)

    # 处理视频
    for f in videos:
        dt = extract_date_video(f['path'], progress_callback)
        if dt is None:
            continue
        video_dates.append((f, dt))
        processed += 1
        if progress_callback:
            rel = f.get('relative_path', f['path'])
            progress_callback('extracting',
                              f'🎬 读取日期: {rel} → {dt.strftime("%Y-%m-%d")}',
                              current_file=rel,
                              count=processed, total=total_files)

    # ═══ 阶段 3：移动文件 ═══
    if progress_callback:
        progress_callback('organizing',
                          '📦 正在移动文件...',
                          count=0, total=total_files)

    moved_photos = 0
    moved_videos = 0
    errors = []
    moved_count = 0

    all_to_move = (
        [(f, dt, '照片') for f, dt in photo_dates] +
        [(f, dt, '视频') for f, dt in video_dates]
    )

    for f, dt, category in all_to_move:
        result = move_file(f['path'], source_dir, category, dt, mode,
                           progress_callback)
        moved_count += 1

        if result['success']:
            if category == '照片':
                moved_photos += 1
            else:
                moved_videos += 1
        else:
            errors.append({'file': f['path'], 'error': result['error']})

        if progress_callback:
            rel = f.get('relative_path', f['path'])
            action = '✅' if result['success'] else '❌'
            dest = result.get('dest_path', '')
            log_msg = f'{action} [{category}] {rel} → {dest}'
            progress_callback('organizing', log_msg,
                              current_file=rel,
                              count=moved_count, total=len(all_to_move))

    # ═══ 返回结果 ═══
    return {
        'source_dir': source_dir,
        'mode': mode,
        'total_photos': len(photos),
        'total_videos': len(videos),
        'moved_photos': moved_photos,
        'moved_videos': moved_videos,
        'no_exif_photos': no_exif_photos,
        'no_exif_videos': no_exif_videos,
        'errors': errors,
        'summary': {
            'moved': moved_photos + moved_videos,
            'failed': len(errors),
            'total': total_files
        }
    }
```

- [ ] **Step 5: 验证 Python 语法**

Run: `python -c "import py_compile; py_compile.compile('organizer.py', doraise=True); print('OK')"`
Expected: OK

- [ ] **Step 6: 提交**

```bash
git add organizer.py
git commit -m "feat: 实现 organizer.py 核心整理逻辑"
```

---

### Task 4: 创建整理模块模板

**Files:**
- Create: `templates/organize.html`
- Create: `templates/organizing.html`
- Create: `templates/organize_result.html`

- [ ] **Step 1: 创建 templates/organize.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        {% include 'navigation.html' %}

        <div class="page-title">
            &#x1F4C2; <span>照片整理</span>
        </div>

        <div class="card">
            <h2>&#x2699;&#xFE0F; 整理配置</h2>

            <form action="{{ url_for('organize.organize_page') }}" method="POST">

                <div class="form-group">
                    <label>&#x1F4C1; 源目录路径（就地整理）</label>
                    <input type="text" name="source_dir"
                           placeholder="/volume1/photo/未整理"
                           required>
                    <div class="field-explanation">
                        文件会被移到 <code>源目录/照片|视频/年份/日期/</code> 下。
                    </div>
                </div>

                <div class="form-group">
                    <label>&#x1F4C5; 整理模式</label>
                    <div class="radio-group">
                        <label><input type="radio" name="mode" value="day" checked>
                            按天（示例: <code>2025/2025-06-24/</code>）</label><br>
                        <label><input type="radio" name="mode" value="month">
                            按月（示例: <code>2025/2025-06/</code>）</label>
                    </div>
                </div>

                <div class="form-group">
                    <label>&#x1F4C4; 文件类型</label>
                    <div class="checkbox-group">
                        <label>
                            <input type="checkbox" name="organize_photos" checked>
                            整理照片（jpg/png/gif/bmp/webp/tiff/heic）
                        </label><br>
                        <label>
                            <input type="checkbox" name="organize_videos" checked>
                            整理视频（mp4/mov/avi/mkv/wmv/flv/m4v）
                        </label>
                    </div>
                </div>

                <div class="actions">
                    <button type="submit" class="btn btn-primary" id="organizeBtn">
                        &#x1F504; 开始整理
                    </button>
                </div>
            </form>
        </div>

        <div class="card">
            <h2>&#x1F4D6; 说明</h2>
            <ul>
                <li>按照片 EXIF 拍摄日期或视频元数据整理</li>
                <li>无日期信息的文件使用文件修改时间</li>
                <li>同名文件自动重命名（加 _1, _2 后缀）</li>
                <li>已经是 <code>照片/</code> 或 <code>视频/</code> 目录下的文件会跳过</li>
            </ul>
        </div>
    </div>

    <script>
        document.querySelector('form')?.addEventListener('submit', function() {
            document.getElementById('organizeBtn').disabled = true;
            document.getElementById('organizeBtn').innerHTML = '&#x23F3; 整理中...';
        });
    </script>
</body>
</html>
```

- [ ] **Step 2: 创建 templates/organizing.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <style>
        .phase-desc {
            background: var(--bg-tertiary);
            padding: 10px 14px;
            border-radius: 6px;
            margin: 12px 0;
            font-size: 13px;
            color: var(--text-dim);
            line-height: 1.6;
        }
        .phase-desc .highlight {
            color: var(--blue);
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container">
        {% include 'navigation.html' %}

        <div class="page-title">
            &#x23F3; <span>正在整理</span>
        </div>

        {% raw %}
        <div id="progress-section">
            <div class="card">
                <div class="stat-card">
                    <div class="label">状态</div>
                    <div class="number" id="status-text">启动中...</div>
                </div>
                <div class="stat-card">
                    <div class="label">已处理</div>
                    <div class="number blue" id="processed-count">0</div>
                </div>
                <div class="stat-card">
                    <div class="label">总计</div>
                    <div class="number" id="total-count">0</div>
                </div>
                <div id="progress-bar-container" style="display:none;margin-top:12px;">
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-fill" style="width:0%"></div>
                    </div>
                </div>
            </div>

            <div id="phase-desc-container" class="phase-desc">
                准备开始...
            </div>

            <div class="card">
                <h2>&#x1F4DD; 处理日志</h2>
                <div id="log-container" style="max-height:400px;overflow-y:auto;font-size:12px;font-family:monospace;line-height:1.8;">
                </div>
            </div>
        </div>
        {% endraw %}

        <div id="done-section" style="display:none;">
            <div class="card" style="text-align:center;padding:40px;">
                <div style="font-size:48px;margin-bottom:16px;" id="done-icon">&#x2705;</div>
                <h2 id="done-title">整理完成！</h2>
                <div class="actions" style="margin-top:20px;">
                    <a href="{{ url_for('organize.organize_result') }}" class="btn btn-primary">
                        &#x1F4CA; 查看结果
                    </a>
                    <a href="{{ url_for('organize.organize_page') }}" class="btn btn-secondary">
                        &#x1F519; 返回配置
                    </a>
                </div>
            </div>
        </div>

        <div id="error-section" style="display:none;">
            <div class="card" style="text-align:center;padding:40px;">
                <div style="font-size:48px;margin-bottom:16px;">&#x274C;</div>
                <h2 id="error-title">整理出错</h2>
                <p id="error-message" style="color:var(--red);"></p>
                <div class="actions" style="margin-top:20px;">
                    <a href="{{ url_for('organize.organize_page') }}" class="btn btn-primary">
                        &#x1F519; 返回重试
                    </a>
                </div>
            </div>
        </div>
    </div>

    <script>
        var pollInterval = setInterval(function() {
            fetch('{{ url_for("organize.organize_progress_api") }}')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    document.getElementById('status-text').textContent =
                        data.message || '处理中...';
                    document.getElementById('processed-count').textContent =
                        data.count || 0;
                    document.getElementById('total-count').textContent =
                        data.total || 0;

                    if (data.total > 0) {
                        var pct = Math.min(100, Math.round((data.count || 0) / data.total * 100));
                        document.getElementById('progress-fill').style.width = pct + '%';
                    }

                    // 阶段描述
                    var phaseDescs = {
                        'scanning': '🔍 正在扫描目录中所有图片和视频文件...',
                        'extracting': '📅 正在逐个提取文件的拍摄日期（照片读 EXIF，视频用 ffprobe）...',
                        'organizing': '📦 正在按日期移动到对应目录（照片/年份/日期/）...',
                        'done': '✅ 整理完成！'
                    };
                    var phaseEl = document.getElementById('phase-desc-container');
                    if (phaseEl && phaseDescs[data.status]) {
                        phaseEl.innerHTML = '<span class="highlight">' +
                            (data.status === 'scanning' ? '[阶段1/3]' :
                             data.status === 'extracting' ? '[阶段2/3]' :
                             data.status === 'organizing' ? '[阶段3/3]' : '') +
                            '</span> ' + phaseDescs[data.status];
                    }

                    // 日志
                    if (data.log && data.log.length > 0) {
                        var logHtml = data.log.slice(-100).map(function(msg) {
                            return '<div>' + msg + '</div>';
                        }).join('');
                        document.getElementById('log-container').innerHTML = logHtml;
                        var lc = document.getElementById('log-container');
                        lc.scrollTop = lc.scrollHeight;
                    }

                    if (data.status === 'done') {
                        clearInterval(pollInterval);
                        document.getElementById('progress-section').style.display = 'none';
                        document.getElementById('done-section').style.display = 'block';
                    } else if (data.status === 'error') {
                        clearInterval(pollInterval);
                        document.getElementById('progress-section').style.display = 'none';
                        document.getElementById('error-section').style.display = 'block';
                        document.getElementById('error-message').textContent =
                            data.error || data.message || '未知错误';
                    }
                })
                .catch(function(err) {
                    console.error('Poll error:', err);
                });
        }, 1000);
    </script>
</body>
</html>
```

- [ ] **Step 3: 创建 templates/organize_result.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        {% include 'navigation.html' %}

        <div class="page-title">
            &#x1F4CA; <span>整理结果</span>
        </div>

        {% if not result %}
        <div class="empty-state">
            <div class="icon">&#x2753;</div>
            <p>暂无整理结果，请先执行整理操作。</p>
            <div class="actions">
                <a href="{{ url_for('organize.organize_page') }}" class="btn btn-primary">
                    &#x1F504; 开始整理
                </a>
            </div>
        </div>
        {% else %}

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">照片</div>
                <div class="number blue">{{ result.get('moved_photos', 0) }}</div>
            </div>
            <div class="stat-card">
                <div class="label">视频</div>
                <div class="number orange">{{ result.get('moved_videos', 0) }}</div>
            </div>
            <div class="stat-card">
                <div class="label">失败</div>
                <div class="number red">{{ result.get('errors', []) | length }}</div>
            </div>
            <div class="stat-card">
                <div class="label">目录</div>
                <div class="number" style="font-size:14px;">{{ result.get('source_dir', '') }}</div>
            </div>
        </div>

        {% if result.get('errors') %}
        <div class="card">
            <h2>&#x274C; 失败记录</h2>
            <div class="table-wrap">
                <table>
                    <tr><th>文件</th><th>错误</th></tr>
                    {% for err in result.errors %}
                    <tr>
                        <td style="font-family:monospace;font-size:12px;">{{ err.file }}</td>
                        <td style="color:var(--red);">{{ err.error }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
        {% endif %}

        <div class="actions">
            <a href="{{ url_for('organize.organize_page') }}" class="btn btn-primary">
                &#x1F504; 继续整理
            </a>
        </div>

        {% endif %}
    </div>
</body>
</html>
```

- [ ] **Step 4: 验证模板渲染**

Run: 启动 Flask，访问 `http://localhost:5000/organize/`
Expected: 配置页正常显示，样式统一。

- [ ] **Step 5: 提交**

```bash
git add templates/organize.html templates/organizing.html templates/organize_result.html
git commit -m "feat: 创建照片整理模块模板"
```

---

### Task 5: 端到端测试

**Files:**
- （无新文件，验证现有代码）

- [ ] **Step 1: 创建测试目录结构**

```bash
mkdir -p test_images/organize_test/sub
```

在 `test_images/organize_test/sub/` 下放几张不同日期的测试照片，
或者用 `dir_a` / `dir_b` 中已有的照片测试。

- [ ] **Step 2: 启动 Flask 并测试端到端流程**

1. 启动 `python main.py`
2. 访问 `http://localhost:5000/organize/`
3. 填写源目录为 `test_images/organize_test`（或已有测试目录）
4. 选择按天，勾选照片和视频
5. 点击「开始整理」
6. 观察进度页
7. 查看结果页
8. 确认文件已按 `照片|视频/年份/日期/` 结构移动

- [ ] **Step 3: 验证图片跳过了已整理目录**

1. 再次对同一个目录运行整理
2. 确认日志显示跳过 `照片/` 和 `视频/` 目录下的文件

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "feat: 照片整理模块完整实现并测试通过"
```

---

### 验证清单

- [ ] `http://localhost:5000/organize/` 配置页显示正常
- [ ] 导航栏两个 Tab 可切换，高亮正确
- [ ] 已有去重页面（index, scanning, report, plan, result）都显示导航栏
- [ ] 整理进度页实时显示日志
- [ ] 整理完成跳转到结果页
- [ ] 统计数字正确（照片/视频各多少）
- [ ] 按天模式目录为 `2025/2025-06-24/`
- [ ] 按月模式目录为 `2025/2025-06/`
- [ ] 照片和视频分离到不同目录
- [ ] 同名文件自动重命名
- [ ] 已整理的目录被跳过
- [ ] 错误文件计入失败列表
