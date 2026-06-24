# 照片整理模块 — 按日期目录整理 设计文档

## 1. 概述

在现有的图片去重合并工具中新增一个独立模块「照片整理」。
第一个功能：按拍照日期将照片和视频自动归类到日期命名的目录中。

### 用户故事

作为 NAS 用户，我有大量散落在各处的照片和视频文件，希望按拍摄日期自动整理到目录中，方便按时间浏览和管理。

## 2. 操作规则

| 项目 | 决定 |
|------|------|
| 操作方式 | **移动**（原文件移到日期目录） |
| 目标位置 | **就地整理**（源目录下创建 `照片/` 和 `视频/` 子目录） |
| 目录结构 | **按年分组**：`年份/日期/`，如 `2025/2025-06-24/`（按天）或 `2025/2025-06/`（按月） |
| 模式切换 | 页面单选「按天」或「按月」，一次选一种 |
| 冲突处理 | **自动重命名**（追加 `_1`, `_2`... 或时间戳） |
| 文件分类 | 按扩展名区分图片和视频 |

### 图片 vs 视频分离

```
源目录/
  ├─ 照片/
  │   ├─ 2025/
  │   │   ├─ 2025-06-24/      ← 按天模式
  │   │   │   ├─ IMG_001.jpg
  │   │   │   └─ IMG_002.png
  │   │   └─ 2025-06-25/
  │   └─ 2026/
  │       └─ 2026-01-15/
  └─ 视频/
      └─ 2025/
          ├─ 2025-06-24/
          │   └─ VID_001.mp4
          └─ 2025-07/         ← 按月模式
              └─ VID_002.mp4
```

## 3. 架构

### 文件结构

```
routes/
  __init__.py          ← 空文件，标记为 Python 包
  dedup.py             ← 去重合并全部路由（从 main.py 移过来）
  organize.py          ← 照片整理全部路由

organizer.py           ← 整理核心逻辑
templates/
  navigation.html      ← 共用导航栏
  organize.html        ← 整理配置页
  organizing.html      ← 整理进度页
  organize_result.html ← 整理结果页

main.py                ← 创建 app → 注册蓝图 → 启动（大幅瘦身）
static/style.css       ← 新增导航栏样式
```

### Blueprint（蓝图）设计

Flask 的 Blueprint 机制将路由分组到独立文件中。

**`routes/dedup.py`** — Blueprint 名称 `dedup`，URL 前缀 `/`

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET/POST | 配置页 + 提交扫描 |
| `/scanning` | GET | 异步扫描进度页 |
| `/progress` | GET | AJAX 进度 JSON 端点 |
| `/report` | GET | 分析报告 |
| `/plan` | GET | 合并方案 |
| `/execute` | POST | 执行合并 |
| `/result` | GET | 执行结果 |

**`routes/organize.py`** — Blueprint 名称 `organize`，URL 前缀 `/organize`

| 路由 | 方法 | 说明 |
|------|------|------|
| `/organize/` | GET/POST | 整理配置页 + 提交整理 |
| `/organize/progress` | GET | AJAX 进度 JSON 端点 |
| `/organize/scanning` | GET | 整理进度页 |
| `/organize/result` | GET | 整理结果页 |

### 全局状态变量

各自独立，互不干扰：

```python
# routes/dedup.py
dedup_progress = { 'status': 'idle', 'message': '', 'log': [] }

# routes/organize.py
organize_progress = { 'status': 'idle', 'message': '', 'log': [] }
```

## 4. organizer.py 核心逻辑

### 流程

```
阶段 1：扫描文件
  ├─ 递归遍历目录
  ├─ 按扩展名分类（图片 vs 视频）
  └─ 记录路径 + 大小 + 扩展名 → 进度回调

阶段 2：提取日期
  ├─ 图片：PIL Image.open() → _getexif() → DateTimeOriginal (0x9003)
  │   └─ 失败 → os.path.getmtime()
  ├─ 视频：subprocess.run(['ffprobe', ...]) → creation_time
  │   └─ 失败 → os.path.getmtime()
  └─ 按天(yyyy-MM-dd)或按月(yyyy-MM)格式化 → 进度回调

阶段 3：移动文件
  ├─ 计算目标路径：源目录/照片|视频/年份/日期/文件名
  ├─ 检查冲突 → 自动重命名
  ├─ os.makedirs() 创建目录
  ├─ shutil.move() 执行移动
  └─ 记录成功/失败 → 进度回调
```

### 日期提取优先级

```
图片：EXIF DateTimeOriginal (36867) → 文件修改时间
视频：ffprobe 输出中的 creation_time → 文件修改时间
```

### 图片扩展名识别

```
图片: .jpg .jpeg .png .gif .bmp .webp .tiff .tif .heic .heif
视频: .mp4 .mov .avi .mkv .wmv .flv .m4v
```

小写比较，不区分大小写。

### 冲突处理逻辑

```python
dest_path = base_dir / "照片" / year_str / date_str / filename
if not dest_path.exists():
    shutil.move(src, dest_path)
else:
    name, ext = os.path.splitext(filename)
    counter = 1
    while dest_path.exists():
        dest_path = base_dir / "照片" / year_str / date_str / f"{name}_{counter}{ext}"
        counter += 1
    shutil.move(src, dest_path)
```

### 接口设计

```python
def organize_by_date(
    source_dir: str,
    mode: str,          # 'day' 或 'month'
    progress_callback: callable
) -> dict:
    """
    按日期整理照片和视频。

    Returns:
        {
            'total_photos': N,
            'total_videos': N,
            'moved': N,
            'errors': [{'file': path, 'error': msg}, ...],
            'no_exif': N,
            'no_exif_files': [path, ...]
        }
    """
```

## 5. 进度上报

复用与去重模块相同的 AJAX 轮询模式：

- `organize_progress` 全局变量每处理一个文件就更新一次
- 前端每秒用 `setInterval` 请求 `/organize/progress`
- 日志最多 300 条，达到后丢弃最早的

### 阶段描述

| 阶段 | 说明 |
|------|------|
| `scanning` | 正在扫描文件：遍历所有子目录，识别图片和视频文件... |
| `extracting` | 正在提取拍摄日期：读取照片 EXIF 和视频元数据... |
| `organizing` | 正在移动文件：将文件按日期移动到目标目录... |
| `done` | 整理完成 |
| `error` | 出错 |

## 6. 模板设计

### 公共导航栏（templates/navigation.html）

所有页面顶部显示两个 Tab，用 `<a>` 实现，当前 Tab 高亮：

```
[ 📷 去重合并 ]  [ 📂 照片整理 ]
```

通过 `request.endpoint` 判断当前路由属于哪个 Blueprint 来高亮。

### organize.html（配置页）

```
卡片 1：目录配置
  ┌─────────────────────────────┐
  │  整理目录路径  [input]       │
  │  (源目录，就地整理)           │
  └─────────────────────────────┘

卡片 2：整理模式
  ┌─────────────────────────────┐
  │  ◎ 按天（yyyy-MM-dd）        │
  │  ○ 按月（yyyy-MM）           │
  └─────────────────────────────┘

卡片 3：文件类型
  ┌─────────────────────────────┐
  │  ☑ 整理照片                  │
  │  ☑ 整理视频                  │
  │  图片格式: jpg png gif ...   │
  │  视频格式: mp4 mov avi ...   │
  └─────────────────────────────┘

  [ 🔄 开始整理 ]
```

### organizing.html（进度页）

与 `scanning.html` 结构一致，修改阶段描述文字。

### organize_result.html（结果页）

```
┌─────────────────────────────┐
│  整理完成！                   │
│                              │
│  照片: 120 个文件  →  照片/   │
│  视频: 30 个文件   →  视频/   │
│  无 EXIF（使用修改时间）: 5 个  │
│  失败: 0 个                   │
└─────────────────────────────┘

┌── 详细操作清单 ──────────────┐
│  移: 2025-06-24/IMG_001.jpg  │
│  移: 2025-06-24/IMG_002.jpg  │
│  ...                         │
└──────────────────────────────┘

[ 📂 返回整理页面 ]
```

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 图片无法打开读取 EXIF | 记录日志，使用文件修改时间作为备选 |
| 视频无法用 ffprobe 读取 | 记录日志，使用文件修改时间作为备选 |
| ffprobe 未安装 | 捕获 CalledProcessError，所有视频用修改时间，记录警告 |
| 移动时权限不足 | 记录错误，文件保持原位，计入失败列表 |
| 目标目录创建失败 | 记录错误，文件保持原位，计入失败列表 |
| 文件名为空或不合法 | 记录警告，跳过该文件 |
| 路径过长（Windows） | 记录错误，跳过（Linux 上极少发生） |

## 8. 未涉及的功能（以后可扩展）

- 按其他维度整理（按相机型号、按地点 GPS）
- 整理前预览（展示将移动的文件列表，确认后执行）
- 软链接模式（移动后原位置留链接）
- 同时选择多个源目录
- 自定义日期格式
- 自定义目标目录结构（如 `年/月/日` 嵌套式）
