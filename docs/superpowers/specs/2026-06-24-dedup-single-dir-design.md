# 单目录查重模块 — 设计文档

## 背景

在现有图片去重合并工具的基础上，新增一个独立模块：在单个目录中找出完全重复
（SHA256 一致）和视觉相似（pHash 汉明距离小于阈值）的照片，让用户对比后选择
保留哪些、删除哪些。

## 需求

1. 用户选择一个目录
2. 工具扫描该目录下所有图片文件
3. 按 SHA256 + pHash 找出重复组
4. 报告页展示每个重复组的缩略图、文件属性（大小、分辨率、修改时间等）
5. 用户勾选要删除的文件（默认保留最大的文件）
6. 选中文件移入 `.recycle/` 目录（安全删除，可恢复）
7. 展示删除结果

## 架构

与照片整理模块相同，使用独立 Blueprint：

```
routes/dedup_single.py      路由（Blueprint）
dedup_single.py             核心逻辑（扫描、分组、文件信息、删除）
templates/
  ├── dedup_single.html          配置页
  ├── dedup_single_scanning.html  扫描进度页
  ├── dedup_single_report.html    对比报告（核心页面）
  └── dedup_single_result.html    删除结果页
static/style.css           追加对比报告样式
templates/navigation.html   新增 Tab
main.py                     注册 Blueprint
```

## 数据流

```
配置页 → POST /dedup-single/ → 后台线程扫描+分组 → /dedup-single/report
                                                           ↓
                                                    用户勾选文件 → POST /dedup-single/delete
                                                                          ↓
                                                                  /dedup-single/result
```

## 核心逻辑（dedup_single.py）

### scan_directory(path, progress_callback)
- 递归遍历目录
- 跳过 `照片/`、`视频/`、`.recycle/` 目录
- 跳过隐藏文件和临时文件
- 识别图片扩展名：jpg/jpeg/png/gif/bmp/webp/tiff/tif/heic/heif
- 对每个文件计算 SHA256
- 返回文件列表

### compute_phash_for_all(files, progress_callback)
- 对每个文件计算 pHash（复用 scanner.py 的 phash 计算）
- 返回带 pHash 的文件列表

### group_duplicates(files, phash_threshold=10)
- **SHA256 分组**：按 SHA256 完全一致分组
- **pHash 分组**：SHA256 唯一的文件之间，两两比较 pHash 汉明距离
  - 汉明距离 < threshold（默认 10）归为一组
- 返回分组列表，每组包含类型标识（'sha256' / 'phash'）和文件列表

### get_file_info(file_path)
- 返回：文件名、大小、分辨率（PIL Image.size）、修改时间

### delete_files(file_paths, source_dir)
- 创建 `.recycle/dedup_single_<timestamp>/`
- 移动选中文件到回收区，保留相对路径结构
- 返回删除统计

## 路由（routes/dedup_single.py）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dedup-single/` | 配置页 |
| POST | `/dedup-single/` | 启动后台扫描 |
| GET | `/dedup-single/progress` | AJAX 进度 |
| GET | `/dedup-single/scanning` | 扫描进度页 |
| GET | `/dedup-single/report` | 对比报告 |
| GET | `/dedup-single/preview/<path:filename>` | 缩略图（PIL resize） |
| POST | `/dedup-single/delete` | 执行删除 |
| GET | `/dedup-single/result` | 删除结果 |

### 预览图路由
`/dedup-single/preview/<path:filename>` 读取原图，用 PIL 缩放到最大 300px 宽，
返回缩略图。这样报告页可以快速加载缩略图，不需要前端额外处理。

## 报告页面设计

报告按分组展示，每组一行：

```
┌─────────────────────────────────────────────────────────┐
│ 精确重复 · SHA256 一致 · 3 个文件                       │
│ ┌──────┐  ┌──────┐  ┌──────┐                           │
│ │ 预览 │  │ 预览 │  │ 预览 │  ← 300px 缩略图            │
│ ├──────┤  ├──────┤  ├──────┤                           │
│ │IMG001│  │IMG002│  │IMG003│  ← 文件名                  │
│ │1.2MB │  │1.5MB │  │856KB │  ← 文件大小                │
│ │4000×3│  │4000×3│  │2000×│  ← 分辨率                   │
│ │000   │  │000   │  │1500  │                           │
│ │2024/ │  │2024/ │  │2025/ │  ← 修改时间                 │
│ │06/15 │  │06/15 │  │01/01 │                           │
│ │[保留]│  │☑ 删  │  │☐     │  ← 默认保留最大文件         │
│ └──────┘  └──────┘  └──────┘                           │
│                                                         │
│ 视觉相似 · pHash 距离 5 · 2 个文件                      │
│ ┌──────┐  ┌──────┐                                     │
│ │ ...   │  │ ...  │                                     │
│ └──────┘  └──────┘                                     │
│                                                         │
│ [☐ 全选]  [执行删除选中文件 (3 个)]                      │
└─────────────────────────────────────────────────────────┘
```

### 默认选择逻辑
- 每个组中按文件大小降序排列
- **保留**最大的文件（默认不勾选）
- 其他文件默认勾选
- 用户可以自由取消/勾选

### 全选按钮
- 页面顶部和底部各有一个「全选」复选框
- 全选时跳过大文件（即保留最大的，其他全选）

## 安全策略

- 删除不是永久删除，文件移入 `.recycle/dedup_single_<timestamp>/`
- 回收区在源目录下（同磁盘，不额外占空间）
- 用户可手动从回收区恢复

## 与现有模块关系

| 模块 | 关系 |
|------|------|
| scanner.py | 复用 `calculate_phash` 函数（单文件 pHash 计算）、`IMAGE_EXTENSIONS` |
| routes/organize.py | 独立，不依赖 |
| main.py | 只注册 Blueprint |
| navigation.html | 新增第三个 Tab「单目录查重」|
