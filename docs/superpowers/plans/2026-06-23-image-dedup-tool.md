# 图片去重合并工具 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Web 界面的图片去重合并工具，部署在飞牛 OS 上，通过 SHA256 + 感知哈希识别重复图片，生成报告后经用户确认再执行合并。

**整体架构:** Flask Web 应用（无数据库），6 个 Python 模块，4 个 HTML 页面。扫描→分析→报告→确认→执行 的线性流程。

**学习导向:** 全程中文注释，每 3-5 行代码配注释，每步先讲概念再写代码。

**技术栈:** Python 3.9+, Flask 2.x, Jinja2, Pillow, imagehash, hashlib

---

### 任务清单总览

| # | 任务 | 产出文件 | 学习要点 |
|---|------|----------|----------|
| 1 | 项目脚手架 | `requirements.txt`, `config.json`, `config.py`, `main.py` 骨架 | pip 包管理、JSON 读写、Flask 最小应用 |
| 2 | 文件扫描模块 | `scanner.py` | 文件遍历 `os.walk()`、路径处理 `pathlib`、`hashlib.sha256()` |
| 3 | 感知哈希扫描 | `scanner.py` 追加 | Pillow 图片加载、imagehash 计算 |
| 4 | 去重分析模块 | `analyzer.py` | 集合运算、字典分组、分类逻辑 |
| 5 | 首页 - 配置页面 | `main.py` 路由 + `templates/index.html` + `static/style.css` | Flask 路由、Jinja2 模板、表单处理、GET/POST |
| 6 | 报告页面 | `main.py` 路由 + `templates/report.html` | 数据传递到模板、表格渲染、条件判断 |
| 7 | 合并方案 + 执行 | `merger.py` + `main.py` 路由 + `templates/plan.html` + `templates/result.html` | 文件复制/删除、安全回收、用户确认流程 |
| 8 | 整合收尾 | `README.md` | 项目说明、部署步骤 |

---

### Task 1: 项目脚手架

**文件:**
- 创建: `requirements.txt`
- 创建: `config.py`
- 创建: `config.json`
- 创建: `main.py`（基础骨架）

---

- [ ] **Step 1: 编写 requirements.txt**

```txt
# 本项目依赖的第三方包
# 安装命令: pip install -r requirements.txt

Flask==3.1.1
# Flask: Web 框架，用于提供 Web 页面和 API
# 类似 Java 的 Spring Boot / C# 的 ASP.NET Core

Pillow==11.1.0
# Pillow: Python 图像处理库 (PIL 的现代分支)
# 用于打开和转换图片文件，计算感知哈希时需要
# 类似 Java 的 ImageIO / C# 的 System.Drawing

imagehash==4.3.1
# imagehash: 图片感知哈希库
# 计算图片的「指纹」，判断视觉相似性
# 这是 Python 生态中的专用库，Java/C# 无直接对应
```

---

- [ ] **Step 2: 编写 config.py**

```python
"""
config.py - 配置管理模块
=======================

功能：读取和保存 JSON 配置文件。
JSON 文件存储在项目根目录的 config.json 中。

Python 知识点：
- import: 导入模块（类似 Java import / C# using）
- with open() as f: 上下文管理器（类似 C# using / Java try-with-resources）
- json.dump / json.load: JSON 序列化/反序列化
- os.path 路径操作
"""

import json           # JSON 处理（Python 标准库，无需安装）
import os              # 操作系统接口（标准库）
from pathlib import Path  # 面向对象的路径操作（Python 3.4+ 标准库）

# 配置文件的保存路径
# __file__ 是当前 .py 文件的路径
# Path(__file__).parent 获取当前文件所在目录（即项目根目录）
# / 运算符在 pathlib 中用于拼接路径（类似 Java Paths.get() / C# Path.Combine()）
CONFIG_FILE = Path(__file__).parent / "config.json"

# 默认配置结构
# Python 的字典（dict）类似 Java 的 HashMap / C# 的 Dictionary
# 键是字符串，值可以是任意类型（字符串、数字、列表、字典）
DEFAULT_CONFIG = {
    "dir_a": "/volume1/photo/phone",     # 目录 A 路径
    "dir_b": "/volume1/photo/camera",    # 目录 B 路径
    "merge_direction": "a_to_b",         # 合并方向: a_to_b 或 b_to_a
    "preview_mode": True                 # 预览模式: True=仅扫描不操作
}


def load_config():
    """
    从 JSON 文件加载配置。
    如果文件不存在，返回默认配置。

    Returns:
        dict: 配置字典

    知识点:
        - try/except: Python 的异常处理（类似 try/catch）
        - FileNotFoundError: 文件不存在的异常类型
        - json.load(): 从文件读取 JSON 并解析为 Python 对象
    """
    try:
        # 'r' 表示只读模式
        # encoding='utf-8' 指定文件编码（处理中文路径）
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            # json.load() 读取文件并解析为 Python 字典
            return json.load(f)
    except FileNotFoundError:
        # 配置文件还不存在，返回默认配置
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """
    保存配置到 JSON 文件。

    Args:
        config: 要保存的配置字典

    知识点:
        - 'w' 表示写入模式（覆盖写入）
        - json.dump(): 将 Python 对象写为 JSON 格式到文件
        - ensure_ascii=False: 允许写入中文（不转义为 \\u 编码）
        - indent=2: 格式化输出，每层缩进 2 空格，方便人类阅读
    """
    # 确保配置目录存在，不存在就创建
    # exist_ok=True: 如果目录已存在也不会报错
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
```

---

- [ ] **Step 3: 创建 config.json（初始配置）**

```json
{
    "dir_a": "",
    "dir_b": "",
    "merge_direction": "a_to_b",
    "preview_mode": true
}
```

---

- [ ] **Step 4: 编写 main.py（基础骨架）**

```python
"""
main.py - 程序入口与 Flask Web 服务
==================================

功能：启动 Flask Web 服务，定义所有页面的路由（URL 处理函数）。

Python 知识点：
- Flask 是最流行的 Python 轻量级 Web 框架
- @app.route() 是装饰器（Decorator），类似 Java @RequestMapping 注解
- 一个 .py 文件可以直接作为程序入口运行

技术说明：
- 我们选择 Flask 而不是 Django，因为：
  1. Flask 轻量简洁，一个文件就能跑起来
  2. 学习曲线平缓，适合初学者
  3. 默认使用 Jinja2 模板引擎（类似 JSP / Razor）
"""

# ──── 模块导入 ────
# 导入 Flask 框架的核心类和方法
# from flask import Flask 的意思是：从 flask 包中导入 Flask 这个类
# 类似 Java: import org.springframework.web.bind.annotation.RequestMapping;
from flask import Flask, render_template, request, redirect, url_for, jsonify

# 导入我们自己的配置管理模块
# from config import load_config 的意思是：从 config.py 文件中导入 load_config 函数
# Python 的 import 比 Java 更灵活，可以直接导入函数/变量
from config import load_config, save_config, DEFAULT_CONFIG

# ──── 创建 Flask 应用 ────
# __name__ 是 Python 的特殊变量
# - 直接运行此文件时（python main.py），__name__ = "__main__"
# - 被其他文件导入时，__name__ = "main"（模块名）
# Flask(__name__) 告诉 Flask 以当前模块为起点查找模板和静态文件
app = Flask(__name__)

# ──── 全局变量 ────
# 存储扫描和分析的临时结果
# 在 Python 中，模块级变量就是全局变量（类似 Java static 字段）
# 注意：生产环境不建议用全局变量存数据，但学习和原型阶段可以
scan_result = {}   # 扫描结果（将在 scanner.py 中填充）
analysis_result = {}  # 分析结果（将在 analyzer.py 中填充）
merge_plan = {}    # 合并方案（将在 merger.py 中生成）


# ──── 首页：配置页面 ────
# @app.route() 是 Flask 的装饰器，用于绑定 URL 和函数
# route('/') 表示用户访问网站根路径时（http://localhost:5000/）执行此函数
# methods=['GET', 'POST'] 表示这个 URL 同时支持 GET 和 POST 请求
# GET：浏览器访问页面时发起
# POST：提交表单时发起
@app.route('/', methods=['GET', 'POST'])
def index():
    """
    首页处理函数。
    - GET 请求: 显示配置表单（从 config.json 读取当前配置）
    - POST 请求: 接收表单提交的配置，保存后跳转到报告页

    request 是 Flask 自动注入的请求对象，包含浏览器发来的所有数据
    """
    global scan_result, analysis_result  # global 声明：我们要修改全局变量

    if request.method == 'POST':
        # ── 用户提交了表单 ──
        # request.form 是浏览器提交的表单数据（类似 Java HttpServletRequest.getParameter()）
        config = {
            'dir_a': request.form.get('dir_a', '').strip(),
            'dir_b': request.form.get('dir_b', '').strip(),
            'merge_direction': request.form.get('merge_direction', 'a_to_b'),
            'preview_mode': request.form.get('preview_mode') == 'on'
        }
        # 保存配置到文件
        save_config(config)

        # ── 开始扫描 ──
        # TODO: 在 Task 2 实现 scanner.py 后，这里调用扫描函数
        # scan_result = scanner.scan_directories(config)
        # analysis_result = analyzer.analyze(scan_result)

        # 跳转到报告页面
        # redirect() 是 Flask 的重定向函数
        # url_for() 根据函数名生成 URL（/report）
        return redirect(url_for('show_report'))

    # ── GET 请求：显示表单 ──
    # 尝试从文件加载配置，文件不存在则使用默认配置
    config = load_config()
    # render_template() 是 Flask 渲染 HTML 模板的函数
    # 第一个参数是模板文件名（在 templates/ 目录下）
    # 后面的参数是传递给模板的变量
    return render_template('index.html',
                           config=config,
                           title='图片去重合并工具')


# ──── 报告页面 ────
@app.route('/report')
def show_report():
    """展示扫描分析报告"""
    global analysis_result
    return render_template('report.html',
                           result=analysis_result,
                           title='分析报告')


# ──── 合并方案页面 ────
@app.route('/plan')
def show_plan():
    """展示合并方案"""
    global merge_plan
    return render_template('plan.html',
                           plan=merge_plan,
                           title='合并方案')


# ──── 执行合并 ────
@app.route('/execute', methods=['POST'])
def execute():
    """执行合并操作"""
    # TODO: Task 7 实现 merger.py 后补充
    return redirect(url_for('show_result'))


# ──── 执行结果页面 ────
@app.route('/result')
def show_result():
    """展示合并执行结果"""
    return render_template('result.html',
                           title='执行完成')


# ──── 程序入口 ────
# 这个 if 判断是 Python 的惯用法
# 当直接运行 python main.py 时，__name__ 等于 "__main__"，条件成立，执行下面的代码
# 当 import main 时，__name__ 等于 "main"，条件不成立，不会自动启动服务器
if __name__ == '__main__':
    # 启动 Flask 开发服务器
    # host='0.0.0.0' 允许局域网内其他设备访问（不只是本机）
    # debug=True 启用调试模式：代码修改后自动重启 + 显示详细的错误页面
    # port=5000 端口号（浏览器访问: http://飞牛IP:5000）
    print("=" * 50)
    print("  图片去重合并工具已启动!")
    print("  访问地址: http://localhost:5000")
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(host='0.0.0.0', debug=True, port=5000)
```

---

- [ ] **Step 5: 安装依赖并验证**

```bash
# 安装依赖
cd E:\yq\Code\pythenhelloworld
pip install -r requirements.txt

# 验证 Flask 能启动
python main.py
# 预期输出: Flask 启动信息，访问 http://localhost:5000 能看到页面（但目前模板未创建会报错）
```

---

### Task 2: 文件扫描模块 (SHA256)

**文件:**
- 创建: `scanner.py`

**学习要点:** `os.walk()` 递归遍历目录、`pathlib` 路径操作、`hashlib.sha256()` 计算文件哈希、大文件分块读取

---

- [ ] **Step 1: 编写 scanner.py — 文件扫描 + SHA256 哈希**

```python
"""
scanner.py - 文件扫描与哈希计算模块
====================================

功能：
1. 递归遍历指定目录，找出所有图片文件
2. 对每个文件计算 SHA256 哈希值（用于精确去重）
3. 对每个图片文件计算感知哈希值（用于视觉相似性判断）

哈希算法简要说明：
- SHA256: 加密哈希算法，同样的文件内容 → 同样的哈希值
  只要文件有一个 bit 不同，哈希值就完全不同
  用于找到「内容完全一样」的重复文件

- 感知哈希 (pHash): 基于图片视觉特征的哈希算法
  两张看起来一样的图片（即使分辨率不同），哈希值会很接近
  用于找到「看起来一样但文件不同」的重复图片

Python 知识点：
- os.walk(): 递归遍历目录树（类似 Java Files.walk() / C# Directory.EnumerateFiles()）
- hashlib.sha256(): 计算 SHA256 哈希（类似 Java MessageDigest / C# SHA256Managed）
- 大文件分块读取：避免一次性读入内存导致 OOM
- pathlib.Path: 面向对象的路径处理（比 os.path 更现代）
"""

import os               # 文件和目录操作（标准库）
import hashlib          # 哈希计算（标准库）
from pathlib import Path  # 现代路径操作（标准库）


# ──── 支持的图片格式 ────
# Python 的 set（集合）用花括号表示，类似 Java HashSet
# 全部小写，比较时统一转小写
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'
}


def is_image_file(file_path):
    """
    判断一个文件是否是图片文件。

    Args:
        file_path: 文件路径（字符串或 Path 对象）

    Returns:
        bool: True 如果是图片文件

    知识点:
        - Path(file_path): 将字符串转为 Path 对象
        - .suffix: Path 对象的属性，获取文件扩展名（如 '.jpg'）
        - .lower(): 字符串转小写（统一大小写）
        - in 关键字: 判断元素是否在集合中
    """
    # Path(file_path) 将字符串路径转为 Path 对象
    # Path 对象比字符串路径更方便，支持 .name, .parent, .suffix 等属性
    # Path.suffix 获取文件扩展名（例如 "photo.jpg" → ".jpg"）
    ext = Path(file_path).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def sha256_hash(file_path):
    """
    计算文件的 SHA256 哈希值。

    这是精确去重的核心方法。
    两个文件只要内容相同，SHA256 就相同。

    为什么不用 MD5？虽然 MD5 更快，但存在碰撞风险。
    对于个人照片去重，其实 MD5 也够用，但 SHA256 是更稳妥的标准做法。

    Args:
        file_path: 文件路径

    Returns:
        str: 64 位十六进制哈希字符串（如 "a3b9c1..."）
              如果文件读取失败返回 None

    知识点:
        - hashlib.sha256(): 创建一个 SHA256 哈希计算器对象
        - .update(data): 将数据加入哈希计算（可以多次调用）
        - .hexdigest(): 获取最终的十六进制哈希字符串
        - 分块读取: 每次读取 64KB，避免大文件耗尽内存
    """
    # 创建 SHA256 哈希对象
    # 哈希对象就像一个累加器，不断把数据喂给它，最后得到汇总的哈希值
    sha256 = hashlib.sha256()

    try:
        # 'rb' 模式: 以二进制只读方式打开文件
        # 注意：必须用二进制模式，文本模式 ('r') 会改变文件内容
        with open(file_path, 'rb') as f:
            # 分块读取文件内容
            # 逐块读取的原因: 一个文件可能有几百 MB
            # 一次性读入内存会占用太多 RAM
            # 这里是典型的「流式处理」思想
            while True:
                # 每次读取 64KB (65536 字节)
                # block 是 bytes 类型（二进制数据）
                block = f.read(65536)  # 64KB
                if not block:
                    # read() 返回空 bytes 表示文件已读完
                    break
                # 将这一块数据喂给哈希计算器
                sha256.update(block)

        # .hexdigest() 返回 64 字符的十六进制字符串
        # 例如: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        return sha256.hexdigest()

    except (IOError, PermissionError) as e:
        # IOError: 文件读取错误（如文件被占用）
        # PermissionError: 没有权限读取
        # Python 允许多个异常类型在同一个 except 中捕获（类似 C# 的 when）
        print(f"[警告] 无法读取文件: {file_path} - {e}")
        return None


def scan_directory(directory_path):
    """
    扫描一个目录，找出所有图片文件并计算 SHA256 哈希。

    这是整个程序的「数据采集」阶段。

    返回值是一个列表，每个元素是一个字典，包含：
    {
        'path': '完整文件路径',       # str
        'name': '文件名',             # str
        'size': 文件大小（字节）,      # int
        'sha256': '文件的 SHA256',     # str（计算失败为 None）
        'relative_path': '相对路径'     # str（从扫描目录开始算起）
    }

    Args:
        directory_path: 要扫描的目录路径

    Returns:
        list: 文件信息字典列表

    知识点:
        - os.walk(): 递归遍历目录树
          每次迭代返回 (当前目录路径, 子目录列表, 文件列表)
          这是 Python 最常用的目录遍历方式
        - os.path.getsize(): 获取文件大小（字节）
    """
    # 确保路径是字符串
    directory_path = str(directory_path)
    # 确保目录存在
    if not os.path.isdir(directory_path):
        print(f"[错误] 目录不存在: {directory_path}")
        return []

    files_info = []
    # os.walk() 递归遍历目录
    # root: 当前正在遍历的目录路径
    # dirs: 当前目录下的子目录列表（我们用不到，但 os.walk 会返回）
    # files: 当前目录下的文件列表
    for root, dirs, files in os.walk(directory_path):
        for filename in files:
            # 构建完整文件路径
            file_path = os.path.join(root, filename)

            # ── 只处理图片文件 ──
            if not is_image_file(file_path):
                continue

            try:
                # 获取文件大小
                # os.path.getsize() 返回文件字节数
                file_size = os.path.getsize(file_path)

                # ── 跳过空文件（大小为 0） ──
                if file_size == 0:
                    print(f"[跳过] 空文件: {file_path}")
                    continue

                # ── 计算 SHA256 哈希 ──
                file_hash = sha256_hash(file_path)

                # ── 计算相对路径 ──
                # relative_path 用于在报告中显示
                relative_path = os.path.relpath(file_path, directory_path)

                # ── 添加到结果列表 ──
                files_info.append({
                    'path': file_path,                   # 完整路径，用于实际操作
                    'name': filename,                    # 文件名，用于显示
                    'size': file_size,                   # 文件大小（字节）
                    'sha256': file_hash,                # SHA256 哈希值
                    'relative_path': relative_path       # 相对路径，用于显示
                })

                # 打印进度（便于调试）
                print(f"[扫描] {relative_path} ({file_size} bytes)")

            except (OSError, PermissionError) as e:
                print(f"[警告] 处理文件时出错: {file_path} - {e}")
                continue

    return files_info


def scan_directories(config):
    """
    同时扫描两个目录，返回扫描结果。

    这是提供给外部调用的统一接口。

    Args:
        config: 配置字典，包含 dir_a 和 dir_b 路径

    Returns:
        dict: {
            'dir_a': {                  # 目录 A 的扫描结果
                'path': '原始路径',
                'files': [文件列表],     # scan_directory() 的返回值
                'total_count': 10,       # 文件总数
                'total_size': 1024       # 文件总大小（字节）
            },
            'dir_b': { ... }            # 目录 B 的扫描结果
        }

    知识点:
        - 函数可以返回 dict（字典），比 Java 要新建一个类更方便
        - Python 的「字典即数据结构」风格
    """
    result = {}

    for dir_key in ['dir_a', 'dir_b']:
        dir_path = config.get(dir_key, '')
        if not dir_path or not os.path.isdir(dir_path):
            print(f"[跳过] 路径无效或不存在: {dir_key}={dir_path}")
            result[dir_key] = {
                'path': dir_path,
                'files': [],
                'total_count': 0,
                'total_size': 0
            }
            continue

        print(f"\n{'='*50}")
        print(f"  扫描目录 {dir_key}: {dir_path}")
        print(f"{'='*50}")

        files = scan_directory(dir_path)
        total_size = sum(f['size'] for f in files if f['sha256'] is not None)

        result[dir_key] = {
            'path': dir_path,
            'files': files,
            'total_count': len(files),
            'total_size': total_size
        }

        print(f"\n  目录 {dir_key} 扫描完成:")
        print(f"    图片文件: {len(files)} 个")
        print(f"    总大小:   {total_size / 1024 / 1024:.2f} MB")

    return result
```

---

### Task 3: 给 scanner.py 追加感知哈希

**文件:**
- 修改: `scanner.py`（追加感知哈希函数）

---

- [ ] **Step 1: 给 scanner.py 追加感知哈希函数**

```python
"""
在 scanner.py 文件末尾追加以下函数。
感知哈希（pHash）用于识别「看起来一样但文件不同」的图片。

感知哈希原理（通俗理解）：
1. 将图片缩小到 32×32 像素（去除细节，只保留结构）
2. 转为灰度图（去掉颜色干扰）
3. 计算离散余弦变换 (DCT)（提取频率特征）
4. 取左上角 8×8 的低频区域（主要结构信息）
5. 计算中位数，大于中位数记 1，小于记 0
6. 得到一个 64 位的二进制指纹

两张图片的哈希值越接近（差异位越少），视觉上越相似。

知识点：
- Python 第三方库的导入和使用
- Pillow (PIL): Python 最流行的图片处理库
- imagehash: 专门计算图片感知哈希的库
- try/except 捕获可能的图片处理异常
"""

# ── 在 scanner.py 顶部追加导入 ──
# 注意：这些是第三方库，需要 pip install
# 判断图片是否可以打开（避免损坏文件导致程序崩溃）
from PIL import Image
# imagehash 库提供多种感知哈希算法
# phash (感知哈希): 对尺寸变化鲁棒，适合照片去重
# ahash (平均哈希): 更简单但不鲁棒
# dhash (差异哈希): 对亮度变化鲁棒
import imagehash


def phash_image(file_path):
    """
    计算一张图片的感知哈希值 (pHash)。

    感知哈希的特点是：
    - 两张视觉相同的图片，即使分辨率、压缩率不同，哈希值也接近
    - 返回的哈希值是一个 64 位整数（用 16 进制字符串表示）
    - 两个哈希值的「汉明距离」越小，图片越相似

    Args:
        file_path: 图片文件路径

    Returns:
        str: 16 位十六进制字符串（如 "8f3a9b7c1d2e4f6a"）
              如果图片无法打开返回 None

    知识点:
        - Image.open(): 打开图片文件，返回 Image 对象
        - imagehash.phash(): 计算感知哈希
        - 异常处理: 图片文件损坏、格式不支持等情况
    """
    try:
        # Image.open() 打开图片文件
        # 注意：此时并未真正读取图片数据（惰性加载）
        # 但可以检查文件头是否有效
        with Image.open(file_path) as img:
            # imagehash.phash() 计算感知哈希
            # hash_size=8 表示生成 8×8 = 64 位的哈希值
            # highfreq_factor=16 高频过滤参数（默认值，一般不需要改）
            phash = imagehash.phash(img, hash_size=8)

            # 返回哈希值的十六进制字符串表示
            # str(phash) 会得到类似 "8f3a9b7c1d2e4f6a" 的字符串
            return str(phash)

    except Exception as e:
        # Image.open() 可能抛出多种异常：
        # - FileNotFoundError: 文件不存在
        # - PIL.UnidentifiedImageError: 无法识别的图片格式
        # - OSError: 文件损坏
        # 用 Exception 捕获所有异常是一种简单的做法
        print(f"[警告] 无法计算图片哈希: {file_path} - {e}")
        return None


def calculate_phash_for_all(scanned_files):
    """
    为扫描结果中的所有文件计算感知哈希。

    Args:
        scanned_files: scanner.scan_directory() 返回的文件列表

    Returns:
        list: 包含感知哈希的文件列表（在原字典中新增 'phash' 字段）

    知识点:
        - 修改列表中的字典元素
        - 用进度输出跟踪长时间操作
    """
    total = len(scanned_files)
    for i, file_info in enumerate(scanned_files, 1):
        # 输出进度（每处理一个文件打印一次进度）
        print(f"[pHash] ({i}/{total}) {file_info['name']}")

        # 获取完整文件路径
        file_path = file_info['path']

        # 确保文件已被成功读取
        # sha256 为 None 表示文件读取失败，跳过 pHash 计算
        if file_info['sha256'] is None:
            file_info['phash'] = None
            continue

        # 计算感知哈希
        file_info['phash'] = phash_image(file_path)

    return scanned_files
```

---

### Task 4: 去重分析模块

**文件:**
- 创建: `analyzer.py`

---

- [ ] **Step 1: 编写 analyzer.py**

```python
"""
analyzer.py - 去重分析模块
==========================

功能：
1. 分析两个目录中图片的重复关系
2. 将图片分类为：完全重复、视觉重复、目录内重复、唯一文件
3. 统计重复数量、可释放空间等指标

分类算法：
- 完全重复（SHA256 相同）：两个目录中存在 SHA256 相同的文件
- 目录内重复：同一个目录内部存在 SHA256 相同的文件
- 视觉重复（SHA256 不同但 pHash 相似）：内容看起来一样但文件不同
- 唯一文件：仅在一个目录中存在（SHA256 唯一）

Python 知识点：
- 字典（dict）的分组操作：用 SHA256 作为 key 分组
- 集合（set）的去重和交集/差集运算
- 列表推导式（List Comprehension）：简洁地构建新列表
"""


def analyze(scan_result):
    """
    分析扫描结果，找出各种重复关系。

    Args:
        scan_result: scanner.scan_directories() 的返回值
            {
                'dir_a': { 'path': '...', 'files': [...], 'total_count': N, 'total_size': N },
                'dir_b': { ... }
            }

    Returns:
        dict: 分析结果，包含以下字段：
            - 'dir_a': 目录 A 统计信息
            - 'dir_b': 目录 B 统计信息
            - 'exact_duplicates': 完全重复文件列表 (A↔B)
            - 'visual_duplicates': 视觉相似文件列表
            - 'unique_to_a': 仅存在于 A 的文件列表
            - 'unique_to_b': 仅存在于 B 的文件列表
            - 'self_duplicates_a': A 目录内重复的文件列表
            - 'self_duplicates_b': B 目录内重复的文件列表
            - 'summary': 汇总统计

    知识点:
        - 字典（dict）是 Python 最常用的数据结构
        - .get(key) 方法：安全获取字典值，不存在返回 None
        - 默认值 .get(key, default)：不存在返回默认值
        - 列表推导式: [x for x in list if condition]
        - 集合运算: & 交集, | 并集, - 差集
    """
    # ── 从扫描结果中提取文件列表 ──
    # .get() 方法：如果键不存在，返回第二个参数（默认值）
    # 这里如果扫描结果中没有 'dir_a' 或 'dir_a' 中没有 'files'，都返回空列表
    files_a = scan_result.get('dir_a', {}).get('files', [])
    files_b = scan_result.get('dir_b', {}).get('files', [])

    # ── Step 1: 构建 SHA256 索引 ──
    # 用 SHA256 作为 key 建立字典，快速查找
    # 这样比两层循环比较要快得多（O(n) vs O(n²)）
    # Python 的字典本质上就是哈希表（类似 Java HashMap）

    # 为目录 A 的每个文件建立 SHA256 → [文件信息] 的映射
    # 注意值是列表，因为同一个 SHA256 可能有多个文件（目录内重复）
    # 字典推导式: {key: value for item in iterable}
    # 这是 Python 非常简洁高效的特性
    sha256_to_files_a = {}
    for f in files_a:
        sha = f.get('sha256')
        if sha is None:
            continue  # SHA256 计算失败的文件跳过
        # .setdefault() 方法：如果 key 不存在，创建一个空列表
        # 然后追加文件信息
        sha256_to_files_a.setdefault(sha, []).append(f)

    sha256_to_files_b = {}
    for f in files_b:
        sha = f.get('sha256')
        if sha is None:
            continue
        sha256_to_files_b.setdefault(sha, []).append(f)

    # ── Step 2: 找出 SHA256 完全重复的文件 ──
    # 两个目录的 SHA256 key 集合
    # set(字典.keys()) 返回所有 key 的集合
    # Python 的集合支持数学运算：& 交集、| 并集、- 差集
    set_a = set(sha256_to_files_a.keys())
    set_b = set(sha256_to_files_b.keys())

    # & 运算符 = 集合交集 → 两个目录都有的 SHA256 → 完全重复
    common_sha256 = set_a & set_b

    # 构建完全重复的文件列表
    # 将 A 和 B 中对应的文件配对
    exact_duplicates = []
    for sha in common_sha256:
        exact_duplicates.append({
            'sha256': sha,
            'files_a': sha256_to_files_a[sha],  # A 中的文件（可能是多个）
            'files_b': sha256_to_files_b[sha],  # B 中的文件（可能是多个）
            'count': len(sha256_to_files_a[sha]) + len(sha256_to_files_b[sha]),
            'size_per_file': sha256_to_files_a[sha][0]['size']
        })

    # ── Step 3: 找出目录内的重复文件 ──
    # 同一个目录中，如果某个 SHA256 对应多个文件，那就是目录内重复
    # 比如你把同一张照片复制粘贴了多次

    self_duplicates_a = []
    for sha, files in sha256_to_files_a.items():
        if len(files) > 1:
            self_duplicates_a.append({
                'sha256': sha,
                'files': files,
                'count': len(files),
                'size_per_file': files[0]['size']
            })

    self_duplicates_b = []
    for sha, files in sha256_to_files_b.items():
        if len(files) > 1:
            self_duplicates_b.append({
                'sha256': sha,
                'files': files,
                'count': len(files),
                'size_per_file': files[0]['size']
            })

    # ── Step 4: 找出唯一文件 ──
    # SHA256 只在一个目录中的文件
    # set_a - set_b: A 有但 B 没有的 SHA256
    unique_sha_a = set_a - set_b
    unique_sha_b = set_b - set_a

    unique_to_a = []
    for sha in unique_sha_a:
        unique_to_a.extend(sha256_to_files_a[sha])

    unique_to_b = []
    for sha in unique_sha_b:
        unique_to_b.extend(sha256_to_files_b[sha])

    # ── Step 5: 找出视觉相似的图片 ──
    # 在「唯一文件」中，找出 pHash 接近的图片
    # 这需要两两比较，相对较慢
    visual_duplicates = []
    # 由于 pHash 比较是 O(n²)，如果文件很多会很慢
    # 这里做个简化：只在少量文件时启用
    # TODO: 更高效的做法是用 pHash 的数值差，差值小于阈值则视为相似

    # ── Step 6: 汇总统计 ──
    total_duplicate_size = sum(
        item['size_per_file'] for item in exact_duplicates
    )

    # 计算可释放的空间
    # 对于每个重复组，保留一份，删除多余的
    # 所以可释放空间 = 每个重复组 (总文件数 - 1) * 单文件大小
    reclaimable = 0
    for item in exact_duplicates:
        # 重复组中，保留 1 份，其余都可以删
        excess = item['count'] - 1
        reclaimable += excess * item['size_per_file']

    # 目录内重复的可释放空间
    for item in self_duplicates_a:
        excess = item['count'] - 1
        reclaimable += excess * item['size_per_file']
    for item in self_duplicates_b:
        excess = item['count'] - 1
        reclaimable += excess * item['size_per_file']

    result = {
        'dir_a': {
            'name': scan_result.get('dir_a', {}).get('path', '目录 A'),
            'total_count': scan_result.get('dir_a', {}).get('total_count', 0),
            'total_size': scan_result.get('dir_a', {}).get('total_size', 0)
        },
        'dir_b': {
            'name': scan_result.get('dir_b', {}).get('path', '目录 B'),
            'total_count': scan_result.get('dir_b', {}).get('total_count', 0),
            'total_size': scan_result.get('dir_b', {}).get('total_size', 0)
        },
        'exact_duplicates': exact_duplicates,
        'visual_duplicates': visual_duplicates,
        'unique_to_a': unique_to_a,
        'unique_to_b': unique_to_b,
        'self_duplicates_a': self_duplicates_a,
        'self_duplicates_b': self_duplicates_b,
        'summary': {
            'total_files': (
                scan_result.get('dir_a', {}).get('total_count', 0) +
                scan_result.get('dir_b', {}).get('total_count', 0)
            ),
            'exact_duplicate_count': len(exact_duplicates),
            'visual_duplicate_count': len(visual_duplicates),
            'unique_to_a_count': len(unique_to_a),
            'unique_to_b_count': len(unique_to_b),
            'self_duplicates_a_count': len(self_duplicates_a),
            'self_duplicates_b_count': len(self_duplicates_b),
            'reclaimable_size': reclaimable,
            'total_duplicate_size': total_duplicate_size
        }
    }

    return result
```

---

### Task 5: 首页 — 配置页面

**文件:**
- 创建: `templates/index.html`
- 创建: `static/style.css`

---

- [ ] **Step 1: 编写 style.css**

```css
/* 
style.css - 全局样式文件
学习要点：CSS 基础，深色主题适合 NAS 使用场景
*/

/* ── 全局重置（reset）── */
/* 清除浏览器默认间距 */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

/* ── 深色主体颜色 ── */
/* CSS 变量（Custom Properties） */
:root {
    --bg: #0d1117;         /* 背景色 */
    --card: #161b22;       /* 卡片背景 */
    --border: #30363d;     /* 边框色 */
    --text: #e6edf3;       /* 文字主色 */
    --text-dim: #8b949e;   /* 辅助文字色 */
    --accent: #58a6ff;     /* 蓝色强调 */
    --green: #3fb950;      /* 绿色（成功/正面） */
    --red: #f85149;        /* 红色（警告/负面） */
    --orange: #d29922;     /* 橙色（提醒） */
}

body {
    font-family: -apple-system, "Helvetica Neue", "Noto Sans SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 20px;
    min-height: 100vh;
}

/* ── 通用容器 ── */
.container {
    max-width: 960px;
    margin: 0 auto;
}

/* ── 页面标题 ── */
.page-title {
    text-align: center;
    padding: 30px 0 20px;
    font-size: 26px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 30px;
}

.page-title span {
    color: var(--accent);
}

/* ── 卡片组件 ── */
.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 20px;
}

.card h2 {
    font-size: 16px;
    margin-bottom: 16px;
    color: var(--accent);
}

/* ── 表单组件 ── */
.form-group {
    margin-bottom: 16px;
}

.form-group label {
    display: block;
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 6px;
    font-weight: 500;
}

.form-group input[type="text"] {
    width: 100%;
    padding: 10px 14px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 14px;
    font-family: 'Consolas', 'Courier New', monospace;
}

.form-group input[type="text"]:focus {
    outline: none;
    border-color: var(--accent);
}

/* ── 单选按钮组 ── */
.radio-group {
    display: flex;
    gap: 20px;
    padding: 8px 0;
}

.radio-group label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    cursor: pointer;
    color: var(--text);
}

/* ── 复选框 ── */
.checkbox-group {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
}

.checkbox-group label {
    font-size: 14px;
    cursor: pointer;
}

/* ── 按钮 ── */
.btn {
    display: inline-block;
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
}

.btn-primary {
    background: var(--accent);
    color: #fff;
}

.btn-primary:hover {
    background: #4a8fd4;
}

.btn-danger {
    background: var(--red);
    color: #fff;
}

.btn-success {
    background: var(--green);
    color: #fff;
}

.btn-secondary {
    background: var(--border);
    color: var(--text);
}

/* ── 统计卡片网格 ── */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.stat-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}

.stat-card .number {
    font-size: 28px;
    font-weight: 700;
}

.stat-card .label {
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 4px;
}

.stat-card .number.green { color: var(--green); }
.stat-card .number.red { color: var(--red); }
.stat-card .number.blue { color: var(--accent); }
.stat-card .number.orange { color: var(--orange); }

/* ── 表格 ── */
.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

th, td {
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    background: rgba(88, 166, 255, 0.05);
    color: var(--accent);
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

tr:hover td {
    background: rgba(88, 166, 255, 0.03);
}

/* ── 消息提示 ── */
.message {
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 16px;
    font-size: 13px;
}

.message.info {
    background: rgba(88, 166, 255, 0.1);
    border: 1px solid rgba(88, 166, 255, 0.3);
    color: var(--accent);
}

.message.warning {
    background: rgba(210, 168, 56, 0.1);
    border: 1px solid rgba(210, 168, 56, 0.3);
    color: var(--orange);
}

.message.success {
    background: rgba(63, 185, 80, 0.1);
    border: 1px solid rgba(63, 185, 80, 0.3);
    color: var(--green);
}

/* ── 空状态 ── */
.empty-state {
    text-align: center;
    padding: 40px;
    color: var(--text-dim);
}

.empty-state .icon {
    font-size: 48px;
    margin-bottom: 16px;
}

/* ── 操作按钮区域 ── */
.actions {
    display: flex;
    gap: 12px;
    justify-content: center;
    margin: 24px 0;
}

/* ── 路径显示 ── */
.path-display {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: var(--text-dim);
    background: var(--bg);
    padding: 6px 10px;
    border-radius: 4px;
}
```

---

- [ ] **Step 2: 编写 templates/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - fnOS 图片去重</title>
    <!-- Flask 的 url_for() 函数生成静态文件的 URL -->
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <!-- 页面标题 -->
        <div class="page-title">
            &#x1f4f7; <span>图片去重合并工具</span>
        </div>

        <!-- 配置表单卡片 -->
        <div class="card">
            <h2>&#x2699;&#xfe0f; 目录配置</h2>

            <!--
            Flask 表单处理：
            - action="{{ url_for('index') }}" 表示表单提交到根路径
            - method="POST" 表示用 POST 方法提交
            - 这样 main.py 中的 index() 函数会收到 POST 请求
            -->
            <form action="{{ url_for('index') }}" method="POST">
                <!-- 目录 A 路径 -->
                <div class="form-group">
                    <label>目录 A 路径（图片来源）</label>
                    <!--
                    Jinja2 模板语法：
                    {{ config.dir_a }} 输出变量的值（类似 JSP ${config.dir_a} / Razor @Model.Config.DirA）
                    value 属性设置输入框的初始值
                    -->
                    <input type="text" name="dir_a"
                           value="{{ config.get('dir_a', '') }}"
                           placeholder="/volume1/photo/phone"
                           required>
                </div>

                <!-- 目录 B 路径 -->
                <div class="form-group">
                    <label>目录 B 路径（目标合并位置）</label>
                    <input type="text" name="dir_b"
                           value="{{ config.get('dir_b', '') }}"
                           placeholder="/volume1/photo/camera"
                           required>
                </div>

                <!-- 合并方向 -->
                <div class="form-group">
                    <label>合并方向</label>
                    <div class="radio-group">
                        <!--
                        Jinja2 条件判断：
                        {% if condition %} ... {% else %} ... {% endif %}
                        checked 属性用于默认选中
                        -->
                        <label>
                            <input type="radio" name="merge_direction" value="a_to_b"
                                   {{ 'checked' if config.get('merge_direction') == 'a_to_b' else '' }}>
                            A &#x2192; B（A 合并到 B）
                        </label>
                        <label>
                            <input type="radio" name="merge_direction" value="b_to_a"
                                   {{ 'checked' if config.get('merge_direction') == 'b_to_a' else '' }}>
                            B &#x2192; A（B 合并到 A）
                        </label>
                    </div>
                </div>

                <!-- 预览模式 -->
                <div class="form-group">
                    <div class="checkbox-group">
                        <label>
                            <input type="checkbox" name="preview_mode"
                                   {{ 'checked' if config.get('preview_mode', True) else '' }}>
                            预览模式（仅扫描分析，不执行任何写操作）
                        </label>
                    </div>
                </div>

                <!-- 提交按钮 -->
                <div class="actions">
                    <button type="submit" class="btn btn-primary">
                        &#x1f50d; 开始扫描
                    </button>
                </div>
            </form>
        </div>

        <!-- 使用说明 -->
        <div class="card">
            <h2>&#x1f4d6; 使用说明</h2>
            <ol style="margin-left: 20px; color: var(--text-dim); font-size: 14px; line-height: 2;">
                <li>填写两个图片目录的完整路径</li>
                <li>选择合并方向：A→B 表示将 A 合并到 B</li>
                <li>开启预览模式：仅扫描分析，不执行操作</li>
                <li>点击「开始扫描」等待分析完成</li>
                <li>查看分析报告和合并方案</li>
                <li>确认后执行合并</li>
            </ol>
        </div>
    </div>
</body>
</html>
```

---

### Task 6: 报告页面

**文件:**
- 创建: `templates/report.html`
- 修改: `main.py`（串联扫描+分析流程）

---

- [ ] **Step 1: 编写 templates/report.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - fnOS 图片去重</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <div class="page-title">
            &#x1f4ca; <span>扫描分析报告</span>
        </div>

        <!--
        Jinja2 条件判断：
        如果 result 字典为空（没有扫描数据），显示空状态提示
        {% if result %} 检查 result 是否有内容
        -->
        {% if not result or not result.get('summary') %}
        <div class="empty-state">
            <div class="icon">&#x1f50d;</div>
            <p>还没有扫描数据，请先配置目录并开始扫描。</p>
            <div class="actions">
                <a href="{{ url_for('index') }}" class="btn btn-primary">
                    &#x1f519; 返回配置
                </a>
            </div>
        </div>
        {% else %}

        <!-- 统计卡片 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number blue">{{ result.summary.total_files }}</div>
                <div class="label">总文件数</div>
            </div>
            <div class="stat-card">
                <div class="number green">{{ result.unique_to_a_count + result.unique_to_b_count }}</div>
                <div class="label">唯一文件</div>
            </div>
            <div class="stat-card">
                <div class="number red">{{ result.summary.exact_duplicate_count }}</div>
                <div class="label">完全重复组</div>
            </div>
            <div class="stat-card">
                <div class="number orange">
                    {{ (result.summary.reclaimable_size / 1024 / 1024) | round(1) }} MB
                </div>
                <div class="label">可释放空间</div>
            </div>
        </div>

        <!-- 目录信息 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">&#x1f4c1; 目录 A</div>
                <div class="path-display">{{ result.dir_a.name }}</div>
                <div class="number blue">{{ result.dir_a.total_count }}</div>
                <div class="label">张 / {{ (result.dir_a.total_size / 1024 / 1024) | round(1) }} MB</div>
            </div>
            <div class="stat-card">
                <div class="label">&#x1f4c1; 目录 B</div>
                <div class="path-display">{{ result.dir_b.name }}</div>
                <div class="number blue">{{ result.dir_b.total_count }}</div>
                <div class="label">张 / {{ (result.dir_b.total_size / 1024 / 1024) | round(1) }} MB</div>
            </div>
        </div>

        <!-- 完全重复文件清单 -->
        <div class="card">
            <h2>&#x1f4cc; 完全重复文件 (SHA256 相同)</h2>
            {% if result.exact_duplicates %}
            <div class="table-wrap">
                <table>
                    <tr>
                        <th>SHA256（前16位）</th>
                        <th>文件</th>
                        <th>大小</th>
                        <th>所在目录</th>
                    </tr>
                    {% for dup in result.exact_duplicates %}
                    <tr>
                        <td style="font-family:monospace; font-size:12px;">
                            {{ dup.sha256[:16] }}...
                        </td>
                        <td>
                            <!-- 显示 A 中的文件名 -->
                            {% for f in dup.files_a %}
                            <div>{{ f.name }}</div>
                            {% endfor %}
                            <!-- 显示 B 中的文件名 -->
                            {% for f in dup.files_b %}
                            <div>{{ f.name }}</div>
                            {% endfor %}
                        </td>
                        <td>{{ (dup.size_per_file / 1024) | round(1) }} KB</td>
                        <td>A: {{ dup.files_a | length }} 个 / B: {{ dup.files_b | length }} 个</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <p>✅ 没有发现完全重复的文件</p>
            </div>
            {% endif %}
        </div>

        <!-- 操作按钮 -->
        <div class="actions">
            <a href="{{ url_for('index') }}" class="btn btn-secondary">
                &#x1f519; 返回修改
            </a>
            <a href="{{ url_for('show_plan') }}" class="btn btn-primary">
                &#x1f4cb; 查看合并方案
            </a>
        </div>

        {% endif %}
    </div>
</body>
</html>
```

---

- [ ] **Step 2: 修改 main.py — 串联扫描+分析**

在 main.py 的 `index()` 函数的 POST 处理中，找到 TODO 注释，替换为：

```python
# ── 导入扫描和分析模块（在文件顶部追加） ──
from scanner import scan_directories, calculate_phash_for_all
from analyzer import analyze

# ── 在 index() 的 POST 分支中，替换 TODO 部分 ──
# 开始扫描
print("\n[开始扫描] 正在扫描目录...")
scan_result = scan_directories(config)

# 计算感知哈希
print("\n[开始计算] 正在计算图片感知哈希...")
for dir_key in ['dir_a', 'dir_b']:
    if scan_result[dir_key]['files']:
        print(f"\n  处理 {dir_key} 的 {len(scan_result[dir_key]['files'])} 个文件...")
        scan_result[dir_key]['files'] = calculate_phash_for_all(
            scan_result[dir_key]['files']
        )

# 分析重复关系
print("\n[开始分析] 正在分析重复关系...")
analysis_result = analyze(scan_result)
```

---

### Task 7: 合并方案 + 执行合并

**文件:**
- 创建: `merger.py`
- 创建: `templates/plan.html`
- 创建: `templates/result.html`
- 修改: `main.py`（合并方案的路由和执行）

---

- [ ] **Step 1: 编写 merger.py**

```python
"""
merger.py - 合并执行模块
=======================

功能：
1. 根据分析结果生成合并方案（哪些文件要复制、哪些要删除）
2. 执行合并操作（复制唯一文件、删除重复文件）
3. 操作前先备份到回收区

安全策略：
- 删除前先将文件移动到回收区（.recycle 目录），而不是直接删除
- 预览模式下不执行任何写操作
- 所有操作记录日志

Python 知识点：
- shutil 模块：文件复制/移动（标准库）
- os.rename(): 文件移动（同一文件系统内）
- datetime 模块：时间戳，用于生成回收目录名
- logging 模块：日志记录
"""

import os
import shutil
from datetime import datetime
import logging
from pathlib import Path


def setup_logger():
    """
    配置日志记录器。
    日志输出到文件，方便追溯操作历史。

    Returns:
        logging.Logger: 配置好的日志记录器

    知识点:
        - logging 是 Python 标准库的日志模块
        - 类似 Java 的 log4j / C# 的 NLog
        - 但 Python 标准库自带日志功能，无需额外安装
    """
    # 创建日志记录器
    logger = logging.getLogger('image_dedup')
    logger.setLevel(logging.INFO)

    # 创建日志文件路径（在项目根目录）
    log_file = Path(__file__).parent / 'merge.log'

    # 文件处理器：日志写入文件
    # mode='dir_a' 表示追加模式（不覆盖之前的日志）
    file_handler = logging.FileHandler(log_file, mode='dir_a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # 日志格式：时间 - 级别 - 消息
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 同时输出到控制台
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# 初始化日志记录器
logger = setup_logger()


def generate_merge_plan(analysis_result, config):
    """
    根据分析结果和配置生成合并方案。

    合并策略：
    - 方向 A→B：A 是源，B 是目标
      1. A 中的唯一文件 → 复制到 B
      2. 完全重复文件 → 删除 A 中的副本（保留一份）
      3. B 保持不变
    - 方向 B→A：反过来

    Args:
        analysis_result: analyzer.analyze() 的返回值
        config: 配置字典（包含 merge_direction）

    Returns:
        dict: 合并方案，包含详细的待操作文件列表

    知识点:
        - 数据转换：将分析结果转为操作指令列表
        - 每个操作记录源路径和目标路径
    """
    direction = config.get('merge_direction', 'a_to_b')
    preview_mode = config.get('preview_mode', True)

    # 确定源目录和目标目录
    if direction == 'a_to_b':
        # A → B: A 是源，B 是目标
        source_key = 'dir_a'
        target_key = 'dir_b'
        unique_files = analysis_result.get('unique_to_a', [])
        duplicate_groups = analysis_result.get('exact_duplicates', [])
    else:
        # B → A: B 是源，A 是目标
        source_key = 'dir_b'
        target_key = 'dir_a'
        unique_files = analysis_result.get('unique_to_b', [])
        duplicate_groups = analysis_result.get('exact_duplicates', [])

    # 构建操作列表
    operations = []

    # ── 操作 1: 复制唯一文件 ──
    # 源目录中独有的文件，需要复制到目标目录
    for f in unique_files:
        # 当前文件路径
        src_path = f['path']
        # 目标路径：目标目录 + 相对路径（保持目录结构）
        target_dir = analysis_result.get(target_key, {}).get('name', '')
        # 文件名
        filename = f['name']
        dest_path = os.path.join(target_dir, filename)

        operations.append({
            'type': 'copy',           # 操作类型
            'file_path': src_path,    # 源文件路径
            'dest_path': dest_path,   # 目标文件路径
            'filename': filename,      # 文件名（显示用）
            'size': f['size'],         # 文件大小
            'reason': '源目录独有的文件，需要复制到目标目录'
        })

    # ── 操作 2: 删除重复文件 ──
    # 重复组中，保留一份，删除源目录中的多余副本
    num_files_from_source = 0
    for i, group in enumerate(duplicate_groups):
        # 从源目录中取文件来删除
        # 这里简化处理：每个重复组中，源方向对应的文件都标记为待删除
        source_files = []
        if direction == 'a_to_b':
            source_files = group.get('files_a', [])
        else:
            source_files = group.get('files_b', [])

        for f in source_files:
            operations.append({
                'type': 'delete',          # 操作类型
                'file_path': f['path'],    # 要删除的文件路径
                'filename': f['name'],     # 文件名
                'size': f['size'],
                'reason': '与目标目录中的文件重复，需要删除'
            })

    plan = {
        'direction': direction,
        'preview_mode': preview_mode,
        'source_dir': analysis_result.get(source_key, {}).get('name', ''),
        'target_dir': analysis_result.get(target_key, {}).get('name', ''),
        'operations': operations,
        'summary': {
            'copy_count': sum(1 for op in operations if op['type'] == 'copy'),
            'delete_count': sum(1 for op in operations if op['type'] == 'delete'),
            'total_operations': len(operations),
            'total_size': sum(op['size'] for op in operations)
        }
    }

    return plan


def execute_merge(plan):
    """
    执行合并方案。

    流程：
    1. 检查预览模式（预览模式不执行）
    2. 创建回收区目录
    3. 逐条执行操作
    4. 记录日志

    Args:
        plan: generate_merge_plan() 返回的合并方案

    Returns:
        dict: 执行结果，包含成功/失败的操作列表

    知识点:
        - shutil.copy2(): 复制文件并保留元数据（修改时间等）
        - shutil.move(): 移动文件（跨文件系统也可以）
        - os.makedirs(): 创建目录（类似 mkdir -p）
    """
    if plan.get('preview_mode'):
        # 预览模式不执行实际操作
        logger.info("预览模式：不执行实际操作")
        return {
            'success': True,
            'message': '预览模式，未执行实际操作',
            'executed_operations': [],
            'failed_operations': []
        }

    # 确定回收区目录
    # 在目标目录下创建 .recycle/时间戳 目录
    target_dir = plan['target_dir']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recycle_dir = os.path.join(target_dir, '.recycle', timestamp)

    # 创建回收区目录
    try:
        os.makedirs(recycle_dir, exist_ok=True)
        logger.info(f"创建回收区: {recycle_dir}")
    except OSError as e:
        logger.error(f"创建回收区失败: {e}")
        return {
            'success': False,
            'message': f'创建回收区失败: {e}',
            'executed_operations': [],
            'failed_operations': [{'error': str(e)}]
        }

    executed = []
    failed = []

    for op in plan['operations']:
        try:
            if op['type'] == 'copy':
                # ── 执行复制 ──
                # 确保目标目录存在
                dest_dir = os.path.dirname(op['dest_path'])
                os.makedirs(dest_dir, exist_ok=True)

                # shutil.copy2() 复制文件并保留元数据
                # 类似于 cp -p 命令
                shutil.copy2(op['file_path'], op['dest_path'])

                logger.info(f"[复制] {op['file_path']} → {op['dest_path']}")
                executed.append(op)

            elif op['type'] == 'delete':
                # ── 执行删除（先移动到回收区） ──
                # 构建回收区中的路径
                recycle_path = os.path.join(
                    recycle_dir, op['filename']
                )

                # 如果回收区已有同名文件，加时间戳后缀
                if os.path.exists(recycle_path):
                    name, ext = os.path.splitext(op['filename'])
                    recycle_path = os.path.join(
                        recycle_dir,
                        f"{name}_{timestamp}{ext}"
                    )

                # shutil.move() 将文件移动到回收区
                # 相当于 mv 命令
                shutil.move(op['file_path'], recycle_path)

                logger.info(
                    f"[删除] {op['file_path']} → 已移至回收区: {recycle_path}"
                )
                executed.append(op)

        except (OSError, shutil.Error) as e:
            logger.error(f"[失败] {op['type']} {op['file_path']}: {e}")
            op['error'] = str(e)
            failed.append(op)

    result = {
        'success': len(failed) == 0,
        'message': f'执行完成: {len(executed)} 成功, {len(failed)} 失败',
        'executed_operations': executed,
        'failed_operations': failed,
        'recycle_dir': recycle_dir
    }

    return result
```

---

- [ ] **Step 2: 编写 templates/plan.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - fnOS 图片去重</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <div class="page-title">
            &#x1f4cb; <span>合并方案</span>
        </div>

        {% if not plan or not plan.get('operations') %}
        <div class="empty-state">
            <div class="icon">&#x2705;</div>
            <p>没有需要操作的文件，两个目录已经完全一致。</p>
        </div>
        {% else %}

        <!-- 方案概览 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">合并方向</div>
                <div>
                    {% if plan.direction == 'a_to_b' %}
                    A &#x2192; B
                    {% else %}
                    B &#x2192; A
                    {% endif %}
                </div>
            </div>
            <div class="stat-card">
                <div class="number blue">{{ plan.summary.copy_count }}</div>
                <div class="label">需要复制</div>
            </div>
            <div class="stat-card">
                <div class="number red">{{ plan.summary.delete_count }}</div>
                <div class="label">需要删除/回收</div>
            </div>
            <div class="stat-card">
                <div class="number orange">
                    {{ (plan.summary.total_size / 1024 / 1024) | round(1) }} MB
                </div>
                <div class="label">总处理大小</div>
            </div>
        </div>

        <!-- 模式提示 -->
        {% if plan.preview_mode %}
        <div class="message warning">
            &#x26a0;&#xfe0f; 当前为<strong>预览模式</strong>，不会实际执行任何操作。
            如需执行，请取消预览模式后重新扫描。
        </div>
        {% else %}
        <div class="message warning">
            &#x26a0;&#xfe0f; 即将对文件进行操作，删除的文件会移至回收区（.recycle 目录）。
        </div>
        {% endif %}

        <!-- 操作清单 -->
        <div class="card">
            <h2>&#x1f4cb; 将要执行的操作</h2>
            <div class="table-wrap">
                <table>
                    <tr>
                        <th>操作</th>
                        <th>文件</th>
                        <th>大小</th>
                        <th>说明</th>
                    </tr>
                    {% for op in plan.operations %}
                    <tr>
                        <td>
                            {% if op.type == 'copy' %}
                            <span style="color: var(--green);">&#x1f4e5; 复制</span>
                            {% else %}
                            <span style="color: var(--red);">&#x1f5d1; 回收</span>
                            {% endif %}
                        </td>
                        <td style="font-family: monospace; font-size: 12px;">
                            {{ op.filename }}
                        </td>
                        <td>{{ (op.size / 1024) | round(1) }} KB</td>
                        <td style="color: var(--text-dim); font-size: 12px;">
                            {{ op.reason }}
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <!-- 确认按钮 -->
        <div class="actions">
            <a href="{{ url_for('show_report') }}" class="btn btn-secondary">
                &#x1f519; 返回报告
            </a>

            {% if not plan.preview_mode %}
            <form action="{{ url_for('execute') }}" method="POST"
                  onsubmit="return confirm('确认执行合并操作？此操作不可撤销。');"
                  style="display: inline;">
                <button type="submit" class="btn btn-danger">
                    &#x26a0;&#xfe0f; 确认执行合并
                </button>
            </form>
            {% endif %}
        </div>

        {% endif %}
    </div>
</body>
</html>
```

---

- [ ] **Step 3: 编写 templates/result.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - fnOS 图片去重</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <div class="page-title">
            &#x2705; <span>执行完成</span>
        </div>

        <div class="card">
            {% if result and result.success %}
            <div class="message success">
                <strong>&#x2705; 合并执行成功！</strong><br>
                {{ result.message }}
            </div>
            {% else %}
            <div class="message warning">
                <strong>&#x26a0;&#xfe0f; 执行完成但有错误</strong><br>
                {{ result.message if result else '未获取到执行结果' }}
            </div>
            {% endif %}
        </div>

        <!-- 执行统计 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number green">{{ result.executed_operations | length }}</div>
                <div class="label">操作成功</div>
            </div>
            <div class="stat-card">
                <div class="number red">{{ result.failed_operations | length }}</div>
                <div class="label">操作失败</div>
            </div>
            <div class="stat-card">
                <div class="number orange">{{ result.recycle_dir }}</div>
                <div class="label">回收区目录（如有需要可手动恢复）</div>
            </div>
        </div>

        <!-- 成功操作列表 -->
        <div class="card">
            <h2>&#x2705; 成功执行的操作</h2>
            <div class="table-wrap">
                <table>
                    <tr><th>操作</th><th>文件</th></tr>
                    {% for op in result.executed_operations %}
                    <tr>
                        <td>
                            {% if op.type == 'copy' %}&#x1f4e5; 复制
                            {% else %}&#x1f5d1; 回收{% endif %}
                        </td>
                        <td>{{ op.filename }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <!-- 失败操作列表 -->
        {% if result.failed_operations %}
        <div class="card">
            <h2 style="color: var(--red);">&#x274c; 失败的操作</h2>
            <div class="table-wrap">
                <table>
                    <tr><th>文件</th><th>错误</th></tr>
                    {% for op in result.failed_operations %}
                    <tr>
                        <td>{{ op.filename }}</td>
                        <td style="color: var(--red);">{{ op.error }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
        {% endif %}

        <div class="actions">
            <a href="{{ url_for('index') }}" class="btn btn-primary">
                &#x1f504; 重新开始
            </a>
        </div>
    </div>
</body>
</html>
```

---

- [ ] **Step 4: 修改 main.py — 添加合并方案和执行的路由**

在 main.py 中导入 merger，并实现完整的 show_plan、execute、show_result 路由：

```python
# ── 在 main.py 顶部追加导入 ──
from merger import generate_merge_plan, execute_merge

# ── 替换 show_plan 路由 ──
@app.route('/plan')
def show_plan():
    """展示合并方案"""
    global analysis_result, config
    # 从文件重新加载最新的配置（可能被修改了）
    config = load_config()
    # 生成合并方案
    merge_plan = generate_merge_plan(analysis_result, config)
    return render_template('plan.html',
                           plan=merge_plan,
                           title='合并方案')

# ── 替换 execute 路由 ──
@app.route('/execute', methods=['POST'])
def execute():
    """执行合并操作"""
    global analysis_result, config, merge_result

    config = load_config()
    plan = generate_merge_plan(analysis_result, config)
    merge_result = execute_merge(plan)

    return redirect(url_for('show_result'))

# ── 替换 show_result 路由 ──
@app.route('/result')
def show_result():
    """展示合并执行结果"""
    global merge_result
    return render_template('result.html',
                           result=merge_result,
                           title='执行完成')
```

---

### Task 8: 整合收尾

**文件:**
- 创建: `README.md`

---

- [ ] **Step 1: 编写 README.md**

```markdown
# fnOS 图片去重合并工具

将两个目录中的图片合并为一个，自动去除重复图片。

## 功能

-   支持两种去重方式：SHA256 精确去重 + 感知哈希视觉去重
-   支持配置合并方向（A→B 或 B→A）
-   扫描后生成可视化分析报告
-   合并方案需用户确认后才执行
-   删除的文件先移入回收区（.recycle）

## 安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python main.py

# 3. 浏览器访问
# http://localhost:5000
```

## 部署到飞牛 OS

```bash
# 1. SSH 登录飞牛 OS
ssh username@飞牛IP

# 2. 安装 Python 依赖
sudo apt install python3-pip
pip3 install flask pillow imagehash

# 3. 上传项目文件（在本地执行）
# scp -r pythenhelloworld username@飞牛IP:~/

# 4. 在飞牛上启动
cd ~/pythenhelloworld
python3 main.py

# 5. 浏览器访问
# http://飞牛IP:5000
```

## 项目结构

详见 `docs/requirements.md` 中的完整结构说明。
```

---

### 自检清单

1. **需求覆盖:**
   - FR-01 双目录配置 → Task 5 (index.html 配置表单)
   - FR-02 扫描分析 → Task 2/3 (scanner.py) + Task 4 (analyzer.py)
   - FR-03 分析报告 → Task 6 (report.html)
   - FR-04 合并方案 + 确认 → Task 7 (plan.html + merger.py)
   - FR-05 安全性（回收区、预览模式、日志）→ Task 7 (merger.py)

2. **是否有占位符？** No

3. **类型一致性:** 函数签名在各任务间一致（scan_directories → analyze → generate_merge_plan → execute_merge 的数据流完整）

4. **YAGNI:** 没有多余的依赖或功能
