"""
scanner.py - 文件扫描与哈希计算模块
==================================

功能：
1. 递归遍历目录，找出所有图片文件
2. 计算每个文件的 SHA256 哈希（精确去重用）
3. 对每个图片文件计算感知哈希 pHash（视觉去重用，见 Task 3）

两个哈希的区别（面试常问）：
- SHA256:   文件内容不同 → 哈希值完全不同（雪崩效应）
            哪怕只改了一个 bit，哈希值也完全不同
            用于精确去重：内容相同的文件一定得到相同 SHA256

- 感知哈希: 图片视觉相似 → 哈希值也相似（汉明距离小）
            即使分辨率、格式、压缩率不同，只要视觉内容相同
            两张图片的 pHash 差值就很小
            用于视觉去重：看起来一样的图片能识别出来

Python 知识点：
- os.walk():    递归遍历目录
- hashlib:      哈希计算模块（标准库）
- Path:         面向对象路径处理（标准库）
"""

import os
import hashlib
from pathlib import Path

# ── 第三方库导入 ──
# Pillow：Python 最流行的图片处理库
# Image.open() 可以打开和识别几十种图片格式
from PIL import Image

# imagehash：专门计算图片感知哈希的库
# 支持 phash（感知哈希）、ahash（平均哈希）、dhash（差异哈希）等
import imagehash


# ── 支持的文件扩展名 ──
# set（集合）用花括号表示，特点是元素不重复、查找速度快
# set 类似 Java 的 HashSet，查找时间复杂度 O(1)
# 全部小写，比较时统一转小写
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'
}


def is_image_file(file_path):
    """
    判断文件后缀是否是图片格式。

    Args:
        file_path: 文件路径（字符串或 Path 对象）

    Returns:
        True 如果是图片文件

    讲解：
        Path(file_path) 将字符串转为 Path 对象
        .suffix 获取扩展名（如 ".jpg"）
        .lower() 转小写（统一大小写，避免 .JPG 和 .jpg 被视为不同格式）
        in 关键字检查元素是否在集合中
    """
    # Path 对象比字符串方便得多，可以直接 .suffix、.name、.parent
    ext = Path(file_path).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def sha256_hash(file_path):
    """
    计算文件的 SHA256 哈希值。

    返回值是一个 64 位的十六进制字符串，例如：
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    （这是空字符串的 SHA256，你的文件不会是这个值）

    Args:
        file_path: 文件路径

    Returns:
        str: 64 位十六进制哈希值
        如果文件读取失败则返回 None

    讲解：
        这里展示了一个重要的编程模式：分块读取
        为什么不分块？假设你有一张 500MB 的 RAW 照片：
        - 不分块：一次读入 500MB 到内存 → 内存暴涨甚至 OOM
        - 分块：每次只读 64KB，用完丢弃 → 不管文件多大，内存占用恒定

        hashlib.sha256() 创建哈希计算器对象
        .update(data) 不断把数据块喂给计算器
        .hexdigest() 最后得到完整的哈希值
    """
    # 创建 SHA256 哈希对象
    sha256 = hashlib.sha256()

    try:
        # 'rb' 表示二进制只读模式
        # 注意：文本文件用 'r'，二进制文件（图片）用 'rb'
        with open(file_path, 'rb') as f:
            while True:
                # 每次读取 64KB
                # chunk 是 bytes 类型（二进制数据）
                chunk = f.read(65536)  # 65536 字节 = 64KB
                if not chunk:
                    # chunk 为空表示文件读完了
                    break
                # 把这一块数据喂给哈希计算器
                sha256.update(chunk)

        # 返回十六进制哈希字符串
        return sha256.hexdigest()

    except (IOError, PermissionError) as e:
        # IOError: 文件读取错误
        # PermissionError: 没有权限
        # 一个 except 可以同时捕获多个异常类型
        print(f"[警告] 无法读取文件: {file_path}")
        print(f"       原因: {e}")
        return None


def scan_directory(directory_path, progress_callback=None, dir_label=''):
    """
    扫描一个目录，找出所有图片文件并计算 SHA256。

    返回值是一个字典列表，每个字典代表一个文件：
    [
        {
            'path': '完整路径',        # 用于代码操作
            'name': '文件名',          # 用于显示
            'size': 文件大小（字节）,    # 用于统计
            'sha256': '哈希值',         # 用于去重
            'relative_path': '相对路径'  # 用于显示
        },
        ...
    ]

    Args:
        directory_path: 要扫描的目录路径
        progress_callback: 进度回调函数
            def callback(stage, message, **kwargs):
                stage 取值: 'dir_scan' 扫描目录中 / 'file_found' 找到文件
                message: 描述文本
                kwargs 可包含: dir_key, current_file, count, total
        dir_label: 目录标识名（如"源目录"、"目标目录"），用于日志显示

    Returns:
        list: 文件信息字典列表

    讲解：
        os.walk() 是 Python 遍历目录的利器
        每次迭代返回三个值：
        - root:   当前目录路径（字符串）
        - dirs:   当前目录下的子目录名列表（我们可以忽略）
        - files:  当前目录下的文件名列表
        os.walk() 会自动递归进入子目录

        progress_callback 参数是「高阶函数」的用法
        把一个函数当作参数传给另一个函数
        这是 Python 非常灵活的特性
        等价的 Java 写法：Consumer<ProgressInfo> callback
        等价的 C# 写法：Action<ProgressInfo> callback
    """
    directory_path = str(directory_path)

    # 检查目录是否存在
    if not os.path.isdir(directory_path):
        print(f"[错误] 目录不存在: {directory_path}")
        return []

    files_info = []

    # 遍历前通知回调
    if progress_callback:
        progress_callback('dir_scan', f'[{dir_label}] 正在遍历目录树: {directory_path}',
                          dir_key='', count=0, total=0)

    # os.walk() 递归遍历目录树
    # 它会自动进入每一层子目录
    for root, dirs, files in os.walk(directory_path):
        for filename in files:
            # os.path.join() 拼接路径（自动处理 / 和 \ 的差异）
            file_path = os.path.join(root, filename)

            # 跳过非图片文件
            if not is_image_file(file_path):
                continue

            try:
                # os.path.getsize() 获取文件大小（字节）
                file_size = os.path.getsize(file_path)

                # 跳过空文件（大小为 0 的图片没有意义）
                if file_size == 0:
                    print(f"[跳过] 空文件: {file_path}")
                    continue

                # 计算 SHA256 哈希
                file_hash = sha256_hash(file_path)

                # 计算相对路径（从扫描目录算起，用于显示）
                # os.path.relpath() 计算相对路径
                relative_path = os.path.relpath(file_path, directory_path)

                # append() 向列表末尾追加一个元素
                files_info.append({
                    'path': file_path,            # 完整路径
                    'name': filename,             # 文件名
                    'size': file_size,            # 大小
                    'sha256': file_hash,          # SHA256
                    'relative_path': relative_path # 相对路径
                })

                # 通知回调：找到新文件
                if progress_callback:
                    progress_callback('file_found', f'📄 [{dir_label}] 提取文件信息: {relative_path} （已从{dir_label}找到 {len(files_info)} 个图片文件）',
                                      current_file=relative_path,
                                      count=len(files_info),
                                      total=0)

                # 打印扫描进度（方便调试）
                print(f"  [扫描] {relative_path} ({file_size:,} bytes)")

            except (OSError, PermissionError) as e:
                print(f"[警告] 处理文件时出错: {file_path}")
                print(f"       原因: {e}")
                continue

    return files_info


def scan_directories(config, progress_callback=None):
    """
    同时扫描两个目录，返回统一的结果结构。

    这是 scannner.py 对外暴露的统一接口。
    其他地方只需要调用这一个函数即可。

    Args:
        config: 配置字典，包含 dir_a 和 dir_b
        progress_callback: 进度回调函数，传给 scan_directory

    Returns:
        dict: {
            'dir_a': { ... },
            'dir_b': { ... }
        }

    讲解：
        Python 的 f-string 是字符串格式化的最佳方式
        f"...{变量}..." 可以直接在字符串中嵌入变量
        等价的 Java 写法: String.format("...%s...", 变量)
        等价的 C# 写法: $"...{变量}..."
    """
    result = {}

    # for 循环遍历两个目录
    # dir_key 依次取值 'dir_a'、'dir_b'
    for dir_key in ['dir_a', 'dir_b']:
        dir_path = config.get(dir_key, '')
        if not dir_path or not os.path.isdir(dir_path):
            print(f"[跳过] 路径无效: {dir_key} = {dir_path}")
            result[dir_key] = {
                'path': dir_path,
                'files': [],
                'total_count': 0,
                'total_size': 0
            }
            continue

        # ── 扫描目录 ──
        print(f"\n{'=' * 50}")
        print(f"  开始扫描 {dir_key}: {dir_path}")
        print(f"{'=' * 50}")

        # 设置目录显示名：dir_a 是主目录（合并目的地），dir_b 是合并目录（来源）
        # 主目录 = 你要保留照片的核心目录，所有文件不动，只接收合并过来的文件
        # 合并目录 = 你要整理进来的目录，不重复的复制到主目录，重复的移入回收区
        if dir_key == 'dir_a':
            dir_label = '主目录'
        else:
            dir_label = '合并目录'

        # 通知回调：开始扫描该目录
        if progress_callback:
            progress_callback('phase_change', f'正在扫描 {dir_label} ({dir_key})...',
                              dir_key=dir_key, phase='scan')

        # 传入回调，让 scan_directory 上报文件级进度
        # dir_label 用于在日志中标识文件来自源目录还是目标目录
        files = scan_directory(dir_path, progress_callback, dir_label=dir_label)

        # 计算总大小
        total_size = sum(f['size'] for f in files if f['sha256'])

        result[dir_key] = {
            'path': dir_path,
            'files': files,
            'total_count': len(files),
            'total_size': total_size
        }

        # f-string 格式化输出
        print(f"\n  {dir_key} 扫描完成:")
        print(f"    图片文件: {len(files)} 个")
        print(f"    总大小:   {total_size / 1024 / 1024:.2f} MB")

    return result


# ═══════════════════════════════════════════════════════════
#
#  以下为 Task 3 追加的感知哈希相关函数
#
# ═══════════════════════════════════════════════════════════


def phash_image(file_path):
    """
    计算一张图片的感知哈希（pHash）。

    感知哈希的原理（通俗版）：
    1. 把图片缩小到 32×32 像素（去掉细节，保留大致结构）
    2. 转为灰度图（去掉颜色干扰）
    3. 对 32×32 的像素矩阵做离散余弦变换 (DCT)
       DCT 把图片信息从「像素域」转换到「频率域」
       左上角是低频信息（图片的大致结构），右下角是高频信息（细节/噪点）
    4. 取左上角 8×8 的低频区域（只保留最主要的视觉结构）
    5. 计算这 64 个数的中位数
    6. 每个数大于中位数记 1，小于等于记 0 → 得到一个 64 位的二进制指纹

    两张图片的 pHash 差值（汉明距离）越小，视觉上越相似：
    - 距离 = 0:  同一张图片（或完全相同的图片）
    - 距离 ≤ 10: 视觉上非常相似（可能是同一张图的不同分辨率/压缩率）
    - 距离 > 25:  视觉上不同的图片

    Args:
        file_path: 图片文件路径

    Returns:
        str: 16 位十六进制字符串（如 "8f3a9b7c1d2e4f6a"）
        如果图片无法打开或处理失败则返回 None

    讲解：
        Pillow 的 Image.open() 是惰性加载 —— 此时只读取了文件头
        但在 with 块中使用时，会在需要时真正读取数据
        imagehash.phash() 返回一个 ImageHash 对象
        str(ImageHash) 得到十六进制字符串
    """
    try:
        # Image.open() 打开图片文件
        # 支持 jpg、png、gif、bmp、webp 等几十种格式
        with Image.open(file_path) as img:
            # imagehash.phash() 计算感知哈希
            # hash_size=8 表示生成 8×8 = 64 位的哈希
            # 64 位用 16 进制表示就是 16 个字符
            phash = imagehash.phash(img, hash_size=8)

            # 转字符串返回（如 "8f3a9b7c1d2e4f6a"）
            return str(phash)

    except Exception as e:
        # 图片可能损坏、格式不支持等
        # 用通用的 Exception 捕获所有可能的异常
        # 实际项目中可以细化异常类型，但对学习项目来说这样够了
        print(f"[警告] 无法计算感知哈希: {file_path}")
        print(f"       原因: {e}")
        return None


def calculate_phash_for_all(scanned_files, progress_callback=None, dir_label=''):
    """
    为扫描结果列表中的所有文件批量计算感知哈希。

    这个函数会修改传入的列表，给每个文件字典增加 'phash' 字段。
    在 Python 中，列表中的元素是引用传递（类似 Java 的引用类型），
    所以函数内部修改了元素，外部也会看到变化。

    Args:
        scanned_files: scan_directory() 返回的文件列表
        progress_callback: 进度回调函数，每处理一个文件调用一次
        dir_label: 目录标识名（如"源目录"、"目标目录"），用于日志显示

    Returns:
        list: 添加了 'phash' 字段的文件列表（就是传入的同一个列表）

    讲解：
        enumerate() 是 Python 非常实用的内置函数
        它在遍历列表时同时返回「索引」和「元素」
        类似 Java 的 for (int i=0; i<list.size(); i++) 的效果
        但写法更简洁
    """
    total = len(scanned_files)

    # enumerate() 返回 (索引, 元素) 的元组
    # 索引从 1 开始（start=1），方便显示进度
    for i, file_info in enumerate(scanned_files, 1):
        # 获取相对路径（如果没有就用文件名兜底）
        rel_path = file_info.get('relative_path', file_info['name'])

        # 显示进度
        print(f"  [pHash] ({i}/{total}) {rel_path}")

        # 通知回调：正在计算 pHash
        if progress_callback:
            progress_callback('phash_progress',
                              f'🖼️ [{dir_label}] 计算感知哈希 ({i}/{total}): {rel_path}',
                              current_file=rel_path,
                              count=i, total=total)

        # 如果 SHA256 计算失败，也没必要算 pHash 了
        if file_info.get('sha256') is None:
            file_info['phash'] = None
            continue

        # 计算感知哈希
        file_info['phash'] = phash_image(file_info['path'])

    return scanned_files
