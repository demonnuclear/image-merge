"""
config.py - 配置管理模块
=======================

功能：
从 JSON 文件读取配置 / 保存配置到 JSON 文件。

Python 知识点（先看这里再读代码）：
- import:  导入其他 Python 模块（类似 Java import / C# using）
           不同之处：Python 可以只导入模块中的某个函数或变量
- with open() as f: 上下文管理器（类似 C# 的 using / Java 的 try-with-resources）
           自动管理文件打开和关闭，不需要手动 f.close()
- json.dump / json.load: JSON 序列化和反序列化
           Python 的 json 模块是标准库自带的，不需要额外安装
- Path:    pathlib 模块中的路径处理类（Python 3.4+）
           比传统的 os.path 更现代、更易用（类似 Java 的 Paths / C# 的 Path）
"""

import json              # JSON 处理（Python 标准库，对应 Java 的 Jackson 或 Gson）
import os                # 操作系统接口（标准库，文件路径、环境变量等）
from pathlib import Path # 面向对象的路径操作（标准库，Python 3.4+ 引入）

# ── 常量定义 ──
# Python 中常量通常用全大写命名（约定，并非语法强制）
# CONFIG_FILE 是一个 Path 对象
# __file__ 是 Python 的特殊变量：当前 .py 文件的完整路径
# Path(__file__) 把字符串路径转为 Path 对象
# .parent 表示父目录（类似 Java 的 .getParent() / C# 的 Directory.GetParent()）
CONFIG_FILE = Path(__file__).parent / "config.json"

# 默认配置字典
# Python 的字典（dict）类似 Java 的 HashMap<String, Object> / C# 的 Dictionary<string, object>
# 键是字符串，值可以是任意类型
DEFAULT_CONFIG = {
    "dir_a": "",
    "dir_b": "",
    "merge_direction": "a_to_b",
    "preview_mode": True
}


def load_config():
    """
    从 JSON 文件加载配置。

    如果文件不存在，返回默认配置。
    如果文件存在，读取并解析为 Python 字典。

    Returns:
        dict: 配置字典

    知识点：
        try/except: Python 的异常处理（类似 Java 的 try/catch）
        不同之处：
        - Python 用 except 而不是 catch
        - Python 不需要声明可能抛出的异常（没有受检异常）
        - Python 中异常也是对象，可绑定到变量（as e）
    """
    try:
        # open() 打开文件
        # 'r' = read 只读模式
        # encoding='utf-8' 指定编码（中文路径需要）
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            # json.load() 从文件读取 JSON，自动解析为 Python 字典
            config = json.load(f)
            return config
    except FileNotFoundError:
        # 文件还未创建过，返回默认配置
        # .copy() 创建字典的浅拷贝，避免后续修改影响默认值
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """
    保存配置到 JSON 文件。

    Args:
        config: 要保存的配置字典

    知识点：
        json.dump(): 将 Python 对象写为 JSON 到文件
        ensure_ascii=False: 允许中文等非 ASCII 字符直接写入（而不是转成 \\uXXXX）
        indent=2: 格式化输出，每层缩进 2 空格，方便人类阅读和手动编辑
    """
    # 确保父目录存在
    # parent 是 CONFIG_FILE 的上级目录（即项目根目录）
    # mkdir() 创建目录，parents=True 递归创建，exist_ok=True 已存在不报错
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
