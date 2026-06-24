"""
dedup_single.py - 单目录查重核心模块
=========================

功能：
1. 扫描目录中所有图片文件，计算 SHA256
2. 对每个文件计算感知哈希（pHash）
3. 按 SHA256 精确分组 + pHash 视觉相似分组
4. 展示文件属性（分辨率、大小）
5. 用户勾选要删除的文件，移入回收区

依赖：
- hashlib（标准库）：SHA256
- Pillow（已安装）：读取图片、获取分辨率
- imagehash（已安装）：感知哈希

Python 知识点：
- hashlib: 标准库哈希模块，支持 SHA256 / MD5 等
- imagehash: 第三方库，计算图片"感知哈希"
  两张视觉相似的图片，pHash 的汉明距离很小
  这就是"压缩过的也能识别"的原理
"""

import os
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image
import imagehash


# ── 图片扩展名集合（与 scanner.py 保持一致） ──
# set 是集合类型，查找速度快（O(1)）
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'
}

# pHash 汉明距离阈值
# 两个图片的 pHash 差异小于这个值就认为是"视觉相似"
# 值越小越严格：10 表示最多允许 10 个位不同（64 位中）
# 常用的经验值：8-15 之间
PHASH_THRESHOLD = 10


def sha256_hash(file_path):
    """
    计算文件的 SHA256 哈希值。

    分块读取（64KB/块），避免大文件占用太多内存。
    SHA256 是加密哈希，内容不同 → 哈希完全不同（雪崩效应）。
    用于精确去重：内容完全一样的文件，SHA256 一定相同。

    Args:
        file_path: 文件路径（字符串）

    Returns:
        str: 64 位十六进制字符串，失败返回 None
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                # 每次读取 64KB，用完丢弃
                # 不管 1MB 还是 1GB 的文件，内存占用都只有 64KB
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, PermissionError):
        return None


def calculate_phash(file_path):
    """
    计算单张图片的感知哈希（pHash）。

    pHash 和 SHA256 的区别：
    - SHA256: 内容差一个 bit，哈希就完全不同
    - pHash:  视觉相似，哈希值也相似（汉明距离小）
    所以 pHash 能找到"被压缩过的"同一张图。

    Args:
        file_path: 图片文件路径

    Returns:
        str: 16 位十六进制字符串（如 '8f3a9b7c1d2e4f6a'），失败返回 None
    """
    try:
        with Image.open(file_path) as img:
            # hash_size=8 表示 8x8=64 位的哈希
            phash = imagehash.phash(img, hash_size=8)
            return str(phash)
    except Exception:
        return None


def scan_directory(source_dir, progress_callback=None):
    """
    扫描目录，找出所有图片文件，计算 SHA256。

    递归遍历所有子目录，每找到一个图片文件就计算 SHA256。
    已整理的目录（照片/、视频/）和回收区（.recycle）跳过。

    Args:
        source_dir: 源目录路径（字符串）
        progress_callback: 进度回调函数
            func(stage, message, current_file, count, total)

    Returns:
        list[dict]: 每个元素：
            - path: 完整路径
            - relative_path: 相对路径
            - size: 文件大小（字节）
            - sha256: SHA256 哈希值

    抛出:
        FileNotFoundError: 目录不存在
    """
    files = []
    source_path = Path(source_dir)

    if not source_path.exists():
        raise FileNotFoundError(f'目录不存在: {source_dir}')

    for root, dirs, filenames in os.walk(source_dir):
        for filename in sorted(filenames):
            # 跳过隐藏文件和临时文件
            if filename.startswith('.') or filename.startswith('~'):
                continue

            # 检查扩展名
            ext = Path(filename).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue

            full_path = Path(root) / filename
            relative_path = full_path.relative_to(source_path)

            # 跳过已整理目录和回收区
            parts = relative_path.parts
            if parts and parts[0] in ('照片', '视频', '.recycle'):
                continue

            # 计算 SHA256
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


def compute_phash_all(files, progress_callback=None):
    """
    为文件列表批量计算 pHash。

    直接修改传入的列表元素（Python 引用传递），
    为每个文件字典增加 'phash' 字段。

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


def group_duplicates(files):
    """
    按 SHA256 和 pHash 分组，找出重复文件。

    分两步：
    1. 先按 SHA256 分组（精确重复）
    2. SHA256 唯一的文件之间，按 pHash 汉明距离分组（视觉相似）

    每个组内的文件按文件大小降序排列（最大的排第一）。

    Args:
        files: 带 'sha256' 和 'phash' 字段的文件列表

    Returns:
        list[dict]: 每个元素：
            - group_type: 'sha256' 或 'phash'
            - description: 分组说明文字
            - files: 文件列表（按大小降序）
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

    # 分离精确重复和唯一文件
    result_groups = []
    unique_files = []  # SHA256 唯一的文件，后续做 pHash 对比

    for h, group in sha256_groups.items():
        if len(group) >= 2:
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
                'description': (f'视觉相似 · pHash 距离 ≤{PHASH_THRESHOLD}'
                                f' · {len(group)} 个文件'),
                'files': group
            })

    # 按组内最大文件的大小降序排列（最大组排最前）
    result_groups.sort(
        key=lambda g: g['files'][0].get('size', 0) if g['files'] else 0,
        reverse=True
    )

    return result_groups


def get_image_dimensions(file_path):
    """
    获取图片的分辨率（宽 x 高）。

    只读取图片头部信息，不加载完整像素数据，速度快。

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
    将选中的文件移入回收区（不是永久删除）。

    回收区路径：源目录/.recycle/dedup_single_<时间戳>/
    用户可手动从回收区恢复文件。

    Args:
        file_paths: 待删除文件的完整路径列表
        source_dir: 源目录路径
        progress_callback: 进度回调

    Returns:
        dict: {
            'success_count': 成功数,
            'failed_count': 失败数,
            'errors': [{'file': 路径, 'error': 错误信息}],
            'recycle_dir': 回收区路径
        }
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recycle_dir = Path(source_dir) / '.recycle' / f'dedup_single_{timestamp}'
    success_count = 0
    errors = []

    for idx, file_path in enumerate(file_paths):
        try:
            src = Path(file_path)
            # 保留相对路径结构
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
