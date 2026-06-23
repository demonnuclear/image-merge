<<<<<<< HEAD
# 图片去重合并工具 (Image Dedup & Merge Tool)

一个基于 Flask 的 Web 工具，用于扫描和合并两个目录中的重复图片。

## 功能

- **SHA256 精确去重**：通过文件哈希识别完全相同图片
- **感知哈希（pHash）视觉去重**：识别视觉上相似的图片
- **合并方向可选**：A→B 或 B→A
- **预览模式**：默认开启，安全确认后再执行
- **回收区机制**：删除前移到 `.recycle` 目录，可恢复

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 使用

```bash
python main.py
```

打开浏览器访问 `http://localhost:5000`，配置两个目录并开始扫描。

## 部署到 飞牛OS

1. 将项目上传到 NAS（通过 SMB 或 scp）
2. 在 NAS 上安装 Python3 + pip：
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip
   pip3 install -r requirements.txt
   ```
3. 启动服务：
   ```bash
   python3 main.py
   ```
4. 浏览器访问 `http://<NAS_IP>:5000`

建议使用 `screen` 或 `nohup` 保持后台运行：
```bash
nohup python3 main.py > app.log 2>&1 &
```

## 项目结构

```
├── main.py          # 程序入口，Flask 路由
├── config.py        # 配置读写
├── scanner.py       # 目录扫描 + SHA256 + pHash
├── analyzer.py      # 重复分析
├── merger.py        # 合并执行
├── config.json      # 配置文件
├── requirements.txt # Python 依赖
├── static/
│   └── style.css    # 页面样式
└── templates/
    ├── index.html   # 配置页面
    ├── report.html  # 分析报告
    ├── plan.html    # 合并方案
    └── result.html  # 执行结果
```

## 作者

一个 Python 学习项目，适合有 Java/C# 背景的开发者从零开始学 Python。
