# 单目录查重模块 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个独立模块，在单个目录中找出 SHA256 精确重复和 pHash 视觉相似的照片，让用户对比后勾选要删除的，安全移入回收区。

**Architecture:** 与照片整理模块相同，使用独立 Blueprint。核心逻辑在 `dedup_single.py`，路由在 `routes/dedup_single.py`。复用 scanner.py 的 `sha256_hash` 和 imagehash 计算逻辑。

**Tech Stack:** Flask Blueprint, Pillow (已有), imagehash (已有), hashlib (标准库)

---

### Task 1: 核心逻辑 — dedup_single.py

**Files:**
- Create: `dedup_single.py`

**功能：** 扫描目录、计算 SHA256 + pHash、分组、删除

**Step 1: 创建文件头部、导入和常量**

```python
"""
dedup_single.py - 单目录查重核心模块
=========================

功能：
1. 扫描目录中所有图片文件，计算 SHA256 和 pHash
2. 按 SHA256 精确分组 + pHash 视觉相似分组
3. 展示文件属性（分辨率、大小、修改时间）
4. 删除选中文件（移入回收区）

依赖：
- hashlib（标准库）：SHA256
- Pillow（已安装）：读取图片、获取分辨率
- imagehash（已安装）：感知哈希
"""

import os
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image
import imagehash

# 图片扩展名集合（与 scanner.py 保持一致）
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'
}

# pHash 汉明距离阈值：低于此值视为视觉相似
# 值越小越严格，10 是常用的默认值
PHASH_THRESHOLD = 10
```

**Step 2: 实现 sha256_hash 函数**

```python
def sha256_hash(file_path):
    """
    计算文件的 SHA256 哈希值（分块读取，避免大文件 OOM）。
    与 scanner.py 中的实现一致。

    Args:
        file_path: 文件路径

    Returns:
        str: 64 位十六进制哈希值，失败返回 None
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)  # 64KB
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, PermissionError):
        return None
```

**Step 3: 实现 calculate_phash 函数**

```python
def calculate_phash(file_path):
    """
    计算单张图片的感知哈希（pHash）。

    Args:
        file_path: 图片文件路径

    Returns:
        str: 16 位十六进制字符串，失败返回 None
    """
    try:
        with Image.open(file_path) as img:
            phash = imagehash.phash(img, hash_size=8)
            return str(phash)
    except Exception:
        return None
```

**Step 4: 实现 scan_directory 函数**

```python
def scan_directory(source_dir, progress_callback=None):
    """
    扫描目录，找出所有图片文件，计算 SHA256。

    Args:
        source_dir: 源目录路径
        progress_callback: 进度回调(stage, message, **kwargs)

    Returns:
        list: [{
            'path': 完整路径,
            'relative_path': 相对路径,
            'size': 文件大小（字节）,
            'sha256': SHA256 哈希值
        }, ...]

    跳过规则：
    - 隐藏文件（. 开头）
    - 临时文件（~ 开头）
    - 已整理目录（照片/、视频/）
    - 回收区目录（.recycle）
    """
    files = []
    source_path = Path(source_dir)

    if not source_path.exists():
        raise FileNotFoundError(f'目录不存在: {source_dir}')

    for root, dirs, filenames in os.walk(source_dir):
        for filename in sorted(filenames):
            if filename.startswith('.') or filename.startswith('~'):
                continue

            ext = Path(filename).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue

            full_path = Path(root) / filename
            relative_path = full_path.relative_to(source_path)

            parts = relative_path.parts
            if parts and parts[0] in ('照片', '视频', '.recycle'):
                continue

            file_hash = sha256_hash(str(full_path))
            if file_hash is None:
                continue

            file_info = {
                'path': str(full_path),
                'relative_path': str(relative_path),
                'size': full_path.stat().st_size,
                'sha256': file_hash
            }
            files.append(file_info)

            if progress_callback:
                progress_callback(
                    'scanning',
                    f'发现: {relative_path}',
                    current_file=str(relative_path),
                    count=len(files), total=0
                )

    return files
```

**Step 5: 实现 compute_phash_all 函数**

```python
def compute_phash_all(files, progress_callback=None):
    """
    为文件列表批量计算 pHash。

    修改传入的文件列表，为每个元素增加 'phash' 字段。
    Python 的列表元素是引用传递，修改会反映到外部。

    Args:
        files: scan_directory 返回的文件列表
        progress_callback: 进度回调

    Returns:
        list: 添加了 'phash' 字段的文件列表
    """
    total = len(files)
    for idx, f in enumerate(files):
        phash = calculate_phash(f['path'])
        f['phash'] = phash
        if progress_callback:
            progress_callback(
                'phashing',
                f'pHASH: {f.get("relative_path", f["path"])}',
                current_file=f.get('relative_path', f['path']),
                count=idx + 1, total=total
            )
    return files
```

**Step 6: 实现 group_duplicates 函数**

```python
def group_duplicates(files):
    """
    按 SHA256 和 pHash 分组，找出重复文件。

    流程：
    1. 先按 SHA256 分组（精确重复）
    2. SHA256 唯一的文件之间，按 pHash 汉明距离分组（视觉相似）

    Args:
        files: 带 'sha256' 和 'phash' 字段的文件列表

    Returns:
        list: [{
            'group_type': 'sha256' | 'phash',
            'description': str（分组说明）,
            'files': [file_info, ...]  # 按 size 降序排列
        }, ...]
        只返回有 2 个及以上文件的组。
    """
    # ═══ 第一步：SHA256 分组 ═══
    sha256_groups = {}
    for f in files:
        h = f.get('sha256')
        if not h:
            continue
        if h not in sha256_groups:
            sha256_groups[h] = []
        sha256_groups[h].append(f)

    # ═══ 分离精确重复和唯一文件 ═══
    result_groups = []
    unique_files = []  # SHA256 唯一的文件，后续做 pHash 对比

    for h, group in sha256_groups.items():
        if len(group) >= 2:
            # 按大小降序排列
            group.sort(key=lambda x: x.get('size', 0), reverse=True)
            result_groups.append({
                'group_type': 'sha256',
                'description': f'SHA256 精确重复 · {len(group)} 个文件',
                'files': group
            })
        else:
            unique_files.append(group[0])

    # ═══ 第二步：pHash 分组 ═══
    # 只对有 pHash 值的文件做对比
    phash_files = [f for f in unique_files if f.get('phash')]
    used = set()
    for i in range(len(phash_files)):
        if i in used:
            continue
        group = [phash_files[i]]
        used.add(i)
        for j in range(i + 1, len(phash_files)):
            if j in used:
                continue
            try:
                # imagehash.hex_to_hash 将十六进制字符串转回 ImageHash 对象
                h1 = imagehash.hex_to_hash(phash_files[i]['phash'])
                h2 = imagehash.hex_to_hash(phash_files[j]['phash'])
                # 汉明距离：两个哈希值不同的位数
                distance = h1 - h2
                if distance <= PHASH_THRESHOLD:
                    group.append(phash_files[j])
                    used.add(j)
            except Exception:
                continue

        if len(group) >= 2:
            group.sort(key=lambda x: x.get('size', 0), reverse=True)
            result_groups.append({
                'group_type': 'phash',
                'description': f'视觉相似 · pHash 距离 ≤{PHASH_THRESHOLD} · {len(group)} 个文件',
                'files': group
            })

    # 按组内最大文件的大小降序排列
    result_groups.sort(key=lambda g: g['files'][0].get('size', 0) if g['files'] else 0,
                       reverse=True)

    return result_groups
```

**Step 7: 实现 get_file_info（获取分辨率）和 delete_files 函数**

```python
def get_image_dimensions(file_path):
    """
    获取图片的分辨率（宽 x 高）。

    用 Pillow 快速读取图片头部信息，不加载完整图片数据。

    Args:
        file_path: 图片文件路径

    Returns:
        str: '宽x高' 格式，如 '4000x3000'，失败返回 ''
    """
    try:
        with Image.open(file_path) as img:
            w, h = img.size
            return f'{w}x{h}'
    except Exception:
        return ''


def delete_files(file_paths, source_dir, progress_callback=None):
    """
    将选中的文件移入回收区，不直接删除。

    回收区路径: 源目录/.recycle/dedup_single_<timestamp>/

    Args:
        file_paths: 待删除文件的完整路径列表
        source_dir: 源目录路径（回收区建在此目录下）
        progress_callback: 进度回调

    Returns:
        dict: {
            'success_count': int,
            'failed_count': int,
            'errors': [{'file': str, 'error': str}, ...],
            'recycle_dir': str
        }
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recycle_dir = Path(source_dir) / '.recycle' / f'dedup_single_{timestamp}'
    success_count = 0
    errors = []

    for idx, file_path in enumerate(file_paths):
        try:
            src = Path(file_path)
            # 在回收区中保留相对路径结构
            rel = src.relative_to(source_dir) if source_dir else src.name
            dest = recycle_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            # 同名冲突处理
            if dest.exists():
                stem = dest.stem
                ext = dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest.parent / f'{stem}_{counter}{ext}'
                    counter += 1

            shutil.move(str(src), str(dest))
            success_count += 1

            if progress_callback:
                progress_callback(
                    'deleting',
                    f'已移入回收区: {rel}',
                    current_file=str(rel),
                    count=idx + 1, total=len(file_paths)
                )

        except (OSError, shutil.Error) as e:
            errors.append({'file': file_path, 'error': str(e)})

    return {
        'success_count': success_count,
        'failed_count': len(errors),
        'errors': errors,
        'recycle_dir': str(recycle_dir)
    }
```

**Step 8: 验证语法**

Run: `python -c "import py_compile; py_compile.compile('dedup_single.py', doraise=True); print('OK')"`

**Step 9: 提交**

```bash
git add dedup_single.py
git commit -m "feat: 实现单目录查重核心逻辑"
```

---

### Task 2: Blueprint 路由 — routes/dedup_single.py

**Files:**
- Create: `routes/dedup_single.py`
- Modify: `main.py`（注册 Blueprint）

**Step 1: 创建 routes/dedup_single.py**

```python
"""
routes/dedup_single.py - 单目录查重模块路由
==============================

路由列表：
  /dedup-single/              GET  → 配置页
  /dedup-single/              POST → 启动后台扫描
  /dedup-single/progress      GET  → AJAX 进度 JSON
  /dedup-single/scanning      GET  → 扫描进度页
  /dedup-single/report        GET  → 对比报告页
  /dedup-single/preview/<path> GET → 缩略图
  /dedup-single/delete        POST → 执行删除
  /dedup-single/result        GET  → 删除结果页
"""

import threading
from flask import Blueprint, render_template, request, jsonify, send_file
from pathlib import Path
import io
import os

from PIL import Image

from dedup_single import (
    scan_directory, compute_phash_all, group_duplicates,
    get_image_dimensions, delete_files
)

dedup_single_bp = Blueprint('dedup_single', __name__, template_folder='../templates')

# ── 全局进度状态 ──
dedup_progress = {
    'status': 'idle',
    'message': '',
    'current_file': '',
    'count': 0,
    'total': 0,
    'log': [],
    'result': None,
    'error': None
}

# 存储扫描结果供报告页使用
dedup_result = {
    'source_dir': '',
    'groups': [],
    'all_files': []
}


@dedup_single_bp.route('/dedup-single/', methods=['GET', 'POST'])
def dedup_single_page():
    """配置页 / 启动扫描。"""
    if request.method == 'POST':
        source_dir = request.form.get('source_dir', '').strip()

        dedup_progress.clear()
        dedup_progress.update({
            'status': 'starting',
            'message': '正在启动扫描...',
            'log': ['正在启动扫描...']
        })

        config = {'source_dir': source_dir}
        thread = threading.Thread(
            target=run_dedup_background,
            args=(config,),
            daemon=True
        )
        thread.start()

        return render_template('dedup_single_scanning.html', title='扫描中...')

    return render_template('dedup_single.html', title='单目录查重')


@dedup_single_bp.route('/dedup-single/progress')
def dedup_progress_api():
    """AJAX 进度接口。"""
    return jsonify(dedup_progress)


@dedup_single_bp.route('/dedup-single/scanning')
def dedup_scanning():
    """扫描进度页面。"""
    return render_template('dedup_single_scanning.html', title='扫描中...')


@dedup_single_bp.route('/dedup-single/report')
def dedup_report():
    """对比报告页面。"""
    return render_template('dedup_single_report.html',
                           result=dedup_result,
                           title='查重报告')


@dedup_single_bp.route('/dedup-single/preview/<path:filename>')
def dedup_preview(filename):
    """
    缩略图路由。

    读取源文件，缩放到最大 300px，返回 JPEG 缩略图。
    这样报告页可以快速加载缩略图，不需要前端 JS 处理。
    """
    try:
        source_dir = dedup_result.get('source_dir', '')
        file_path = Path(source_dir) / filename

        if not file_path.exists():
            return 'File not found', 404

        # 用 PIL 缩放图片
        img = Image.open(str(file_path))
        img.thumbnail((300, 300), Image.LANCZOS)

        # 转为 JPEG 字节流返回
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=85)
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')

    except Exception as e:
        return str(e), 500


@dedup_single_bp.route('/dedup-single/delete', methods=['POST'])
def dedup_delete():
    """执行删除（移入回收区）。"""
    global dedup_result

    # 从表单获取被勾选的文件路径列表
    selected = request.form.getlist('selected_files')
    source_dir = dedup_result.get('source_dir', '')

    if not selected:
        return render_template('dedup_single_report.html',
                               result=dedup_result,
                               error='没有选择任何文件',
                               title='查重报告')

    def update_progress(stage, message, **kwargs):
        log_entry = message
        dedup_progress.update({
            'status': stage,
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0)
        })
        log = dedup_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        dedup_progress['log'] = log

    result = delete_files(selected, source_dir, progress_callback=update_progress)

    return render_template('dedup_single_result.html',
                           result=result,
                           title='删除结果')


@dedup_single_bp.route('/dedup-single/result')
def dedup_result_page():
    """删除结果页面。"""
    return render_template('dedup_single_result.html',
                           result=dedup_progress.get('result', {}),
                           title='删除结果')


def run_dedup_background(config):
    """
    在后台线程中执行扫描 → pHash → 分组 流程。

    与 run_scan_background 模式相同：通过 dedup_progress 全局变量
    向前端报告实时进度。
    """
    global dedup_result, dedup_progress

    def update_progress(stage, message, **kwargs):
        log_entry = message
        dedup_progress.update({
            'status': 'scanning' if stage == 'scanning' else
                      'phashing' if stage == 'phashing' else
                      'grouping' if stage == 'grouping' else
                      dedup_progress.get('status', 'scanning'),
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0),
            'error': None
        })
        log = dedup_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        dedup_progress['log'] = log

    try:
        source_dir = config['source_dir']

        # ═══ 阶段 1：扫描 + SHA256 ═══
        dedup_progress.update({
            'status': 'scanning',
            'message': '正在扫描目录，计算 SHA256...',
            'log': ['[阶段1/3] 扫描目录 —— 遍历文件，计算 SHA256']
        })
        all_files = scan_directory(source_dir, progress_callback=update_progress)

        # ═══ 阶段 2：计算 pHash ═══
        dedup_progress.update({
            'status': 'phashing',
            'message': '正在计算感知哈希（pHash）...',
            'log': dedup_progress.get('log', []) +
                   ['[阶段2/3] 计算感知哈希 —— 逐张解码图片，提取视觉指纹']
        })
        all_files = compute_phash_all(all_files, progress_callback=update_progress)

        # ═══ 阶段 3：分组 ═══
        dedup_progress.update({
            'status': 'grouping',
            'message': '正在分析重复关系...',
            'log': dedup_progress.get('log', []) +
                   ['[阶段3/3] 分组 —— SHA256 精确分组 → pHash 视觉相似分组']
        })
        groups = group_duplicates(all_files)

        # 为每个文件获取分辨率信息
        for group in groups:
            for f in group['files']:
                f['dimensions'] = get_image_dimensions(f['path'])

        # 保存结果
        dedup_result = {
            'source_dir': source_dir,
            'groups': groups,
            'all_files': all_files,
            'summary': {
                'total_files': len(all_files),
                'total_groups': len(groups),
                'total_duplicate_files': sum(len(g['files']) for g in groups)
            }
        }

        dedup_progress.update({
            'status': 'done',
            'message': f'扫描完成！共 {len(all_files)} 个文件，'
                       f'发现 {len(groups)} 组重复（共 {sum(len(g["files"]) for g in groups)} 个文件）',
            'log': dedup_progress.get('log', []) + ['✅ 扫描完成']
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f'扫描出错: {type(e).__name__}: {e}'
        dedup_progress.update({
            'status': 'error',
            'message': error_msg,
            'error': str(e),
            'log': dedup_progress.get('log', []) + [error_msg]
        })
```

**Step 2: 在 main.py 注册 Blueprint**

在文件顶部（`from routes.organize import organize_bp` 附近）添加：

```python
from routes.dedup_single import dedup_single_bp
```

在 `app.register_blueprint(organize_bp)` 之后添加：

```python
app.register_blueprint(dedup_single_bp)
```

**Step 3: 验证**

Run: `python main.py`
Expected: 启动无报错。访问 `http://localhost:5000/dedup-single/` 返回 200。

**Step 4: 提交**

```bash
git add routes/dedup_single.py main.py
git commit -m "feat: 创建单目录查重 Blueprint 和路由"
```

---

### Task 3: 模板 — 配置页 + 进度页 + 报告页 + 结果页

**Files:**
- Create: `templates/dedup_single.html`
- Create: `templates/dedup_single_scanning.html`
- Create: `templates/dedup_single_report.html`
- Create: `templates/dedup_single_result.html`

**Step 1: 创建 templates/dedup_single.html（配置页）**

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
            &#x1F50D; <span>单目录查重</span>
        </div>

        <div class="card">
            <h2>&#x2699;&#xFE0F; 配置</h2>
            <form action="{{ url_for('dedup_single.dedup_single_page') }}" method="POST">
                <div class="form-group">
                    <label>&#x1F4C1; 源目录路径</label>
                    <input type="text" name="source_dir"
                           placeholder="/volume1/photo/我的照片"
                           required>
                    <div class="field-explanation">
                        扫描此目录中的所有图片，找出 SHA256 完全一致 和 视觉相似的照片。
                    </div>
                </div>
                <div class="actions">
                    <button type="submit" class="btn btn-primary" id="scanBtn">
                        &#x1F50D; 开始扫描
                    </button>
                </div>
            </form>
        </div>

        <div class="card">
            <h2>&#x1F4D6; 说明</h2>
            <ul>
                <li><strong>精确重复</strong>：SHA256 完全一致的文件（内容完全相同）</li>
                <li><strong>视觉相似</strong>：内容一样但分辨率/压缩率不同的文件（如原图与压缩版）</li>
                <li>删除的文件不会直接删除，而是移入 <code>.recycle/</code> 目录，可恢复</li>
            </ul>
        </div>
    </div>

    <script>
        document.querySelector('form')?.addEventListener('submit', function() {
            document.getElementById('scanBtn').disabled = true;
            document.getElementById('scanBtn').innerHTML = '&#x23F3; 扫描中...';
        });
    </script>
</body>
</html>
```

**Step 2: 创建 templates/dedup_single_scanning.html（进度页）**

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
            background: var(--bg);
            padding: 10px 14px;
            border-radius: 6px;
            margin: 12px 0;
            font-size: 13px;
            color: var(--text-dim);
            line-height: 1.6;
        }
        .phase-desc .highlight {
            color: var(--accent);
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container">
        {% include 'navigation.html' %}

        <div class="page-title">
            &#x1F504; <span>正在扫描</span>
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
            </div>

            <div id="phase-desc-container" class="phase-desc">
                准备开始...
            </div>

            <div class="card">
                <h2>&#x1F4DD; 扫描日志</h2>
                <div id="log-container" style="max-height:400px;overflow-y:auto;font-size:12px;font-family:monospace;line-height:1.8;">
                </div>
            </div>
        </div>
        {% endraw %}

        <div id="done-section" style="display:none;">
            <div class="card" style="text-align:center;padding:40px;">
                <div style="font-size:48px;margin-bottom:16px;">&#x2705;</div>
                <h2>扫描完成！</h2>
                <div class="actions" style="margin-top:20px;">
                    <a href="{{ url_for('dedup_single.dedup_report') }}" class="btn btn-primary">
                        &#x1F4CA; 查看报告
                    </a>
                    <a href="{{ url_for('dedup_single.dedup_single_page') }}" class="btn btn-secondary">
                        &#x1F519; 返回配置
                    </a>
                </div>
            </div>
        </div>

        <div id="error-section" style="display:none;">
            <div class="card" style="text-align:center;padding:40px;">
                <div style="font-size:48px;margin-bottom:16px;">&#x274C;</div>
                <h2>扫描出错</h2>
                <p id="error-message" style="color:var(--red);"></p>
                <div class="actions" style="margin-top:20px;">
                    <a href="{{ url_for('dedup_single.dedup_single_page') }}" class="btn btn-primary">
                        &#x1F519; 返回重试
                    </a>
                </div>
            </div>
        </div>
    </div>

    <script>
        var pollInterval = setInterval(function() {
            fetch('{{ url_for("dedup_single.dedup_progress_api") }}')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    document.getElementById('status-text').textContent =
                        data.message || '处理中...';
                    document.getElementById('processed-count').textContent =
                        data.count || 0;
                    document.getElementById('total-count').textContent =
                        data.total || 0;

                    var phaseDescs = {
                        'scanning': '🔍 正在扫描目录，计算 SHA256 哈希...',
                        'phashing': '🖼️ 正在计算感知哈希（pHash），逐张解码图片...',
                        'grouping': '📊 正在分组比对：SHA256 精确分组 → pHash 视觉相似分组...',
                        'done': '✅ 扫描完成！'
                    };
                    var phaseEl = document.getElementById('phase-desc-container');
                    if (phaseEl && phaseDescs[data.status]) {
                        phaseEl.innerHTML = '<span class="highlight">' +
                            (data.status === 'scanning' ? '[阶段1/3]' :
                             data.status === 'phashing' ? '[阶段2/3]' :
                             data.status === 'grouping' ? '[阶段3/3]' : '') +
                            '</span> ' + phaseDescs[data.status];
                    }

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

**Step 3: 创建 templates/dedup_single_report.html（对比报告——核心页面）**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <style>
        .group-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 20px;
            margin-bottom: 20px;
        }
        .group-header {
            font-size: 15px;
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }
        .group-header .type-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            margin-left: 8px;
        }
        .type-badge.sha256 {
            background: rgba(63, 185, 80, 0.15);
            color: var(--green);
        }
        .type-badge.phash {
            background: rgba(210, 168, 56, 0.15);
            color: var(--orange);
        }
        .file-grid {
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }
        .file-card {
            flex: 1;
            min-width: 200px;
            max-width: 280px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            text-align: center;
            position: relative;
        }
        .file-card .preview {
            width: 100%;
            height: 180px;
            object-fit: cover;
            border-radius: 4px;
            background: var(--card);
            margin-bottom: 8px;
        }
        .file-card .filename {
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            color: var(--text);
            word-break: break-all;
            margin-bottom: 4px;
        }
        .file-card .meta {
            font-size: 11px;
            color: var(--text-dim);
            margin-bottom: 2px;
        }
        .file-card .keep-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
            background: var(--green);
            color: #fff;
            margin-top: 6px;
        }
        .file-card .checkbox-wrapper {
            margin-top: 8px;
        }
        .file-card .checkbox-wrapper input {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        .file-card .checkbox-wrapper label {
            font-size: 13px;
            cursor: pointer;
            margin-left: 4px;
        }
        .empty-state {
            text-align: center;
            padding: 40px 20px;
        }
        .empty-state .icon {
            font-size: 48px;
            margin-bottom: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        {% include 'navigation.html' %}

        <div class="page-title">
            &#x1F4CA; <span>查重报告</span>
        </div>

        {% if error %}
        <div class="message warning">{{ error }}</div>
        {% endif %}

        {% if not result.groups or result.groups|length == 0 %}
        <div class="empty-state">
            <div class="icon">&#x2705;</div>
            <p>没有发现重复文件，所有文件都是唯一的。</p>
            <div class="actions">
                <a href="{{ url_for('dedup_single.dedup_single_page') }}" class="btn btn-primary">
                    &#x1F504; 重新扫描
                </a>
            </div>
        </div>
        {% else %}

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">总文件数</div>
                <div class="number blue">{{ result.summary.total_files }}</div>
            </div>
            <div class="stat-card">
                <div class="label">重复组</div>
                <div class="number red">{{ result.summary.total_groups }}</div>
            </div>
            <div class="stat-card">
                <div class="label">重复文件</div>
                <div class="number orange">{{ result.summary.total_duplicate_files }}</div>
            </div>
        </div>

        <form action="{{ url_for('dedup_single.dedup_delete') }}" method="POST"
              onsubmit="return confirmDelete();">

            <div style="margin-bottom:16px;font-size:13px;color:var(--text-dim);">
                <label>
                    <input type="checkbox" id="selectAll" onchange="toggleAll(this)">
                    全选（保留每组最大的文件）
                </label>
                <span style="margin-left:12px;">
                    已选 <span id="selectedCount">0</span> 个文件
                </span>
            </div>

            {% for group in result.groups %}
            <div class="group-card">
                <div class="group-header">
                    {{ group.description }}
                    <span class="type-badge {{ 'sha256' if group.group_type == 'sha256' else 'phash' }}">
                        {{ 'SHA256' if group.group_type == 'sha256' else 'pHash' }}
                    </span>
                </div>

                <div class="file-grid">
                    {% for f in group.files %}
                    {% set is_first = loop.first %}
                    <div class="file-card">
                        <img class="preview"
                             src="{{ url_for('dedup_single.dedup_preview', filename=f.relative_path) }}"
                             alt="{{ f.relative_path }}"
                             loading="lazy"
                             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22180%22><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%238b949e%22 font-size=%2214%22>加载失败</text></svg>'">
                        <div class="filename">{{ f.relative_path }}</div>
                        <div class="meta">{{ (f.size / 1024) | round(1) }} KB</div>
                        <div class="meta">{{ f.get('dimensions', '') }}</div>
                        <div class="meta">SHA256: {{ f.get('sha256', '')[:12] }}...</div>

                        {% if is_first %}
                        <span class="keep-badge">保留</span>
                        {% endif %}

                        <div class="checkbox-wrapper">
                            <label>
                                <input type="checkbox" name="selected_files"
                                       value="{{ f.path }}"
                                       {{ 'checked' if not is_first else '' }}
                                       onchange="updateSelected()">
                                {{ '删除' if not is_first else '保留（不删）' }}
                            </label>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}

            <div class="actions">
                <button type="submit" class="btn btn-danger">
                    &#x1F5D1; 删除选中文件
                </button>
                <a href="{{ url_for('dedup_single.dedup_single_page') }}" class="btn btn-secondary">
                    &#x1F519; 重新扫描
                </a>
            </div>
        </form>

        {% endif %}
    </div>

    <script>
        function toggleAll(source) {
            var checkboxes = document.querySelectorAll('input[name="selected_files"]');
            // 全选时仍然保留每组第一个（最大文件）
            var groups = document.querySelectorAll('.group-card');
            checkboxes.forEach(function(cb) {
                cb.checked = source.checked;
            });
            // 如果取消全选，全部取消
            if (!source.checked) {
                // 不做额外操作
            }
            updateSelected();
        }

        function updateSelected() {
            var checkboxes = document.querySelectorAll('input[name="selected_files"]:checked');
            document.getElementById('selectedCount').textContent = checkboxes.length;
        }

        function confirmDelete() {
            var count = document.querySelectorAll('input[name="selected_files"]:checked').length;
            if (count === 0) {
                alert('请至少选择一个文件');
                return false;
            }
            return confirm('确认将 ' + count + ' 个文件移入回收区？\n\n文件不会被直接删除，可在 .recycle 目录中恢复。');
        }

        // 初始化计数
        updateSelected();
    </script>
</body>
</html>
```

**Step 4: 创建 templates/dedup_single_result.html（删除结果页）**

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
            &#x1F4CA; <span>删除结果</span>
        </div>

        {% if not result %}
        <div class="empty-state">
            <div class="icon">&#x2753;</div>
            <p>暂无删除记录。</p>
        </div>
        {% else %}

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">成功移入回收区</div>
                <div class="number green">{{ result.get('success_count', 0) }}</div>
            </div>
            <div class="stat-card">
                <div class="label">失败</div>
                <div class="number red">{{ result.get('failed_count', 0) }}</div>
            </div>
            <div class="stat-card" style="grid-column: span 2;">
                <div class="label">回收区路径</div>
                <div class="path-display" style="margin-top:6px;">{{ result.get('recycle_dir', '') }}</div>
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
            <a href="{{ url_for('dedup_single.dedup_single_page') }}" class="btn btn-primary">
                &#x1F504; 继续扫描
            </a>
            <a href="{{ url_for('dedup_single.dedup_report') }}" class="btn btn-secondary">
                &#x1F4CA; 返回报告
            </a>
        </div>

        {% endif %}
    </div>
</body>
</html>
```

**Step 5: 验证模板渲染**

Run: `python main.py`
访问 `http://localhost:5000/dedup-single/` 显示配置页。

**Step 6: 提交**

```bash
git add templates/dedup_single*.html
git commit -m "feat: 创建单目录查重模板"
```

---

### Task 4: 导航栏 + CSS + main.py 注册

**Files:**
- Modify: `templates/navigation.html`（新增 Tab）
- Modify: `main.py`（注册 Blueprint）

**Step 1: 在 navigation.html 新增 Tab**

在 `照片整理` Tab 后面添加：

```html
    <a href="{{ url_for('dedup_single.dedup_single_page') }}"
       class="nav-item {{ 'active' if request.path.startswith('/dedup-single') }}">
        &#x1F50D; 单目录查重
    </a>
```

navigation.html 完整最终内容：

```html
<div class="nav-bar">
    <a href="{{ url_for('index') }}"
       class="nav-item {{ 'active' if not request.path.startswith('/organize') and not request.path.startswith('/dedup-single') }}">
        &#x1F4F7; 去重合并
    </a>
    <a href="{{ url_for('organize.organize_page') }}"
       class="nav-item {{ 'active' if request.path.startswith('/organize') }}">
        &#x1F4C2; 照片整理
    </a>
    <a href="{{ url_for('dedup_single.dedup_single_page') }}"
       class="nav-item {{ 'active' if request.path.startswith('/dedup-single') }}">
        &#x1F50D; 单目录查重
    </a>
</div>
```

**Step 2: 在 main.py 注册 Blueprint**

```python
from routes.dedup_single import dedup_single_bp
```

在 `app.register_blueprint(organize_bp)` 后面：

```python
app.register_blueprint(dedup_single_bp)
```

**Step 3: 验证**

Run: `python main.py`
访问导航栏三个 Tab，确认高亮正确。

**Step 4: 提交**

```bash
git add templates/navigation.html main.py
git commit -m "feat: 导航栏添加单目录查重 Tab"
```

---

### Task 5: 端到端测试

**Files:**
- Create: `test_dedup_single.py`（测试）

**Step 1: 创建测试脚本**

```python
"""
test_dedup_single.py - 单目录查重端到端测试

测试步骤：
1. 创建测试目录，用 Pillow 生成内容相同但文件大小不同的图片
2. 调用 scan_directory() 扫描
3. 调用 compute_phash_all() 计算 pHash
4. 调用 group_duplicates() 分组
5. 验证分组结果
6. 清理测试文件
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dedup_single import (
    scan_directory, compute_phash_all, group_duplicates,
    get_image_dimensions, delete_files, sha256_hash
)


def create_test_image(filepath, width=100, height=100, color='red', quality=95):
    """创建测试图片。"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color=color)
    img.save(filepath, 'JPEG', quality=quality)
    print(f'  [CREATE] {filepath} ({width}x{height}, quality={quality})')


def test_sha256_exact_duplicates():
    """测试 1：SHA256 精确重复。"""
    test_dir = Path(tempfile.mkdtemp(prefix='dedup_test_'))

    # 创建 3 张完全相同的图片（同一内容保存两次）
    img1 = test_dir / 'photo_a.jpg'
    img2 = test_dir / 'photo_b.jpg'
    img3 = test_dir / 'photo_c.jpg'
    create_test_image(img1, 200, 200, 'blue', 95)
    # 复制完全相同的内容
    with open(img1, 'rb') as src:
        content = src.read()
    with open(img2, 'wb') as dst:
        dst.write(content)
    with open(img3, 'wb') as dst:
        dst.write(content)

    files = scan_directory(str(test_dir))
    assert len(files) == 3, f'expected 3, got {len(files)}'

    # 验证 SHA256 分组
    sha256_set = set(f['sha256'] for f in files)
    assert len(sha256_set) == 1, f'all should have same sha256, got {len(sha256_set)}'
    print(f'  [OK] SHA256 test: 3 files, 1 group')

    # 清理
    import shutil
    shutil.rmtree(test_dir)
    return True


def test_visual_duplicates():
    """测试 2：视觉相似（不同质量压缩但内容相同）。"""
    test_dir = Path(tempfile.mkdtemp(prefix='dedup_test_'))

    # 用同一张图保存为不同质量
    from PIL import Image
    img = Image.new('RGB', (300, 300), 'green')

    high_qual = test_dir / 'high.jpg'
    low_qual = test_dir / 'low.jpg'
    img.save(str(high_qual), 'JPEG', quality=95)
    img.save(str(low_qual), 'JPEG', quality=20)  # 低质量压缩

    files = scan_directory(str(test_dir))
    assert len(files) == 2

    files = compute_phash_all(files)
    groups = group_duplicates(files)

    # 应该被识别为视觉相似（pHash 分组）
    phash_groups = [g for g in groups if g['group_type'] == 'phash']
    assert len(phash_groups) >= 1, 'should find visual duplicates'
    print(f'  [OK] pHash test: 2 files with different quality, grouped as visual duplicates')

    import shutil
    shutil.rmtree(test_dir)
    return True


def test_no_duplicates():
    """测试 3：全部为不同图片，不应分组。"""
    test_dir = Path(tempfile.mkdtemp(prefix='dedup_test_'))

    create_test_image(test_dir / 'img1.jpg', 100, 100, 'red', 95)
    create_test_image(test_dir / 'img2.jpg', 200, 200, 'green', 95)
    create_test_image(test_dir / 'img3.jpg', 300, 300, 'blue', 95)

    files = scan_directory(str(test_dir))
    files = compute_phash_all(files)
    groups = group_duplicates(files)

    assert len(groups) == 0, f'expected 0 groups, got {len(groups)}'
    print(f'  [OK] No-duplicate test: 3 different images, 0 groups')

    import shutil
    shutil.rmtree(test_dir)
    return True


def test_delete_files():
    """测试 4：删除功能（移入回收区）。"""
    test_dir = Path(tempfile.mkdtemp(prefix='dedup_test_'))

    f1 = test_dir / 'delete_me.jpg'
    f2 = test_dir / 'keep_me.jpg'
    create_test_image(f1, 100, 100, 'red', 95)
    create_test_image(f2, 200, 200, 'blue', 95)

    # 执行删除
    result = delete_files([str(f1)], str(test_dir))
    assert result['success_count'] == 1
    assert result['failed_count'] == 0

    # 验证源文件不存在了
    assert not f1.exists(), 'source file should be moved'

    # 验证回收区存在
    recycle_dirs = list(test_dir.glob('.recycle/*'))
    assert len(recycle_dirs) >= 1, 'recycle dir should exist'
    print(f'  [OK] Delete test: file moved to recycle')

    import shutil
    shutil.rmtree(test_dir)
    return True


if __name__ == '__main__':
    print('=' * 50)
    print('[TEST] Single-dir dedup e2e tests')
    print('=' * 50)

    tests = [
        ('SHA256 exact duplicates', test_sha256_exact_duplicates),
        ('Visual duplicates (pHash)', test_visual_duplicates),
        ('No duplicates', test_no_duplicates),
        ('Delete files (recycle)', test_delete_files),
    ]

    passed = 0
    for name, fn in tests:
        print(f'\n  Test: {name}')
        try:
            fn()
            passed += 1
            print(f'  [PASS]')
        except Exception as e:
            print(f'  [FAIL] {e}')
            import traceback
            traceback.print_exc()

    print(f'\n{"=" * 50}')
    print(f'[RESULT] {passed}/{len(tests)} passed')
    print(f'{"=" * 50}')
```

**Step 2: 运行测试**

Run: `python test_dedup_single.py`

**Step 3: 提交**

```bash
git add test_dedup_single.py
git commit -m "test: 单目录查重模块端到端测试"
```

**Step 4: 最终提交 + push**

```bash
git log --oneline -10
git push
```
