# AGENTS.md

## 项目概要
Flask 图片工具箱，部署于飞牛OS (fnOS) NAS。3 个模块（去重合并 / 照片整理 / 单目录查重），通过独立 Blueprint 注册。

## 运行命令
- 启动: `python main.py` → http://localhost:5000
- 安装依赖: `pip install -r requirements.txt`
- 运行测试: `python test_organize.py`（仅照片整理模块 e2e 测试）

## 目录与架构
- `main.py` — 入口，注册 Blueprint + 路由（/report /progress /execute 等）
- `routes/organize.py` — 照片整理 Blueprint（前缀 /organize）
- `routes/dedup_single.py` — 单目录查重 Blueprint（前缀 /dedup-single）
- 核心模块：`scanner.py` `analyzer.py` `merger.py` `organizer.py` `dedup_single.py`
- 模板在 `templates/`，导航栏 3 个 Tab (`navigation.html`)
- `image-tools/` — fpk 打包项目（独立于源码，非 git 管理，已在 .gitignore）
- `docs/superpowers/` — 设计文档和实施计划

## 约束
- 所有新代码 **必须带极其详细的中文注释**
- 称用户为 **先生**
- 系统不删除文件：移入 `源目录/.recycle/<模块>_<时间戳>/`
- 查重同时使用 SHA256（精确）+ pHash 阈值 10（视觉相似）
- 新模块用独立 Blueprint，在 `routes/` 中创建，注册到 `main.py`
- 测试环境 Win 控制台 GBK 编码，emoji 打印会乱码（不影响 Linux 部署）
- Flask debug reloader 与后台线程冲突风险（`daemon=True` 缓解）

## fpk 打包（飞牛OS 应用部署）
- `image-tools/` 是 fpk 项目根目录，`fnpack build` 在 NAS 上执行
- fpk 类型：Native（非 Docker），直接跑系统 Python3
- `config/privilege` 用 root 运行（需要读写用户任意目录）
- pip 必须加 `--break-system-packages`（Debian PEP 668）+ 清华源镜像
- 桌面图标路径: `app/ui/config` 中 `port` 硬编码 5000
- 安装时自动 apt 装 ffmpeg + Pillow 构建依赖
- `deploy_fpk.ps1` 一键部署（复制源码 → 升级 patch → SCP 到 NAS）
- NAS SSH: `100.66.1.2`, user: `yangqi`, path: `/home/yangqi/image-tools`
- 安装命令: `appcenter-cli install-fpk image-tools.fpk`
