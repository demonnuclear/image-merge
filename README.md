# 图片工具箱 (Image Toolbox)

基于 Flask 的 Web 图片管理工具，部署于飞牛 OS (fnOS) NAS。

## 功能模块

### 1. 去重合并
扫描两个目录中的图片，找 SHA256 精确重复和 pHash 视觉相似照片，生成合并方案，由你确认后执行。

### 2. 照片整理
按拍摄日期（EXIF）自动重新组织照片目录结构，支持后台异步执行。

### 3. 单目录查重
单目录内部扫描 SHA256 精确重复和 pHash 视觉相似图片，展示对比报告，由你勾选哪些需要删除（移入回收区，非永久删除）。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python main.py
```

浏览器访问 `http://localhost:5000`

## 项目结构

```
├── main.py               # 程序入口，注册 Blueprint
├── config.py             # 配置读写
├── scanner.py            # 目录扫描 + SHA256 + pHash
├── analyzer.py           # 重复分析
├── merger.py             # 合并执行
├── organizer.py          # 照片整理
├── dedup_single.py       # 单目录查重
├── routes/
│   ├── organize.py       # 照片整理 Blueprint（/organize/）
│   └── dedup_single.py   # 单目录查重 Blueprint（/dedup-single/）
├── templates/            # 14 个 HTML 模板
├── static/style.css      # 样式
└── requirements.txt      # Flask, Pillow, imagehash
```

## 部署到飞牛 OS

```bash
pip install -r requirements.txt
nohup python3 main.py > app.log 2>&1 &
```

浏览器访问 `http://<NAS_IP>:5000`

也可打包为 fpk 应用（`image-tools/` 目录），通过飞牛应用中心安装。
