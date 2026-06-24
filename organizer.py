"""
organizer.py - 照片整理核心模块
========================

功能：
1. 按扩展名扫描目录中的图片和视频文件
2. 读取拍摄日期（照片 EXIF / 视频 ffprobe / 文件修改时间）
3. 按「源目录/照片|视频/年份/日期/」结构移动文件

依赖：
- Pillow（已安装）：读取图片 EXIF
- ffprobe（系统包）：读取视频元数据
- subprocess（标准库）：调用 ffprobe

Python 知识点：
- Pathlib：跨平台路径操作，比 os.path 更现代
- PIL (Pillow)：Python 最流行的图片处理库
- subprocess：调用外部系统命令
- shutil：高级文件操作（移动、复制）
"""

import os
import shutil
from datetime import datetime
from pathlib import Path


# ── 支持的文件扩展名集合 ──
# 使用 set（集合）而不是 list，因为 in 操作速度是 O(1)
# set 的字面量用 {} 表示，类似 Java 的 HashSet / C# 的 HashSet

# 图片扩展名（小写，因为比较时统一转小写）
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.webp', '.tiff', '.tif', '.heic', '.heif'
}

# 视频扩展名
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'
}


def scan_directory(source_dir, organize_photos=True, organize_videos=True,
                   progress_callback=None):
    """
    扫描源目录，按扩展名分类文件。

    使用 os.walk() 递归遍历所有子目录。
    os.walk 是 Python 遍历目录树的标准方式：
    - root: 当前正在遍历的目录路径
    - dirs: root 下的子目录名列表
    - files: root 下的文件名列表

    Args:
        source_dir: 源目录路径（字符串）
        organize_photos: 是否整理照片（布尔值）
        organize_videos: 是否整理视频（布尔值）
        progress_callback: 进度回调函数，用于在 UI 上显示实时进度
           函数签名: func(stage, message, current_file, count, total)

    Returns:
        dict: {
            'photos': [ 照片文件列表
                { 'path': 完整路径, 'relative_path': 相对路径, 'size': 文件字节数 },
                ...
            ],
            'videos': [ 视频文件列表（同上结构）, ... ]
        }

    抛出:
        FileNotFoundError: 当 source_dir 不存在时
    """
    # 初始化结果列表
    photos = []
    videos = []

    # Path() 是 pathlib 库的核心类
    # 比 os.path 更直观：Path / 'subdir' / 'file.txt' 自动拼接路径
    source_path = Path(source_dir)

    # 检查目录是否存在
    if not source_path.exists():
        # Python 的异常类似 Java 的 throw / C# 的 throw
        raise FileNotFoundError(f'目录不存在: {source_dir}')

    # 递归遍历所有子目录
    # os.walk(source_dir) 生成 (root, dirs, files) 元组
    # root: 当前目录路径（字符串）
    # dirs: 当前目录下的子目录名列表（可修改来剪枝遍历）
    # files: 当前目录下的文件名列表
    for root, dirs, files in os.walk(source_dir):
        # sorted(files) 按文件名排序，保证结果确定性
        for filename in sorted(files):
            # Path(filename).suffix 获取扩展名（如 '.jpg'）
            ext = Path(filename).suffix.lower()

            # 跳过隐藏文件和临时文件
            # 文件名以 . 开头是 Unix 隐藏文件约定
            # 文件名以 ~ 开头是 Office 临时文件
            if filename.startswith('.') or filename.startswith('~'):
                continue

            # Path(root) / filename 拼接完整路径
            # Python 重载了 / 操作符用于 Path 拼接
            full_path = Path(root) / filename

            # relative_to() 计算相对路径
            # 例如：source_path = /photos, full_path = /photos/2024/IMG001.jpg
            # relative_path = 2024/IMG001.jpg
            relative_path = full_path.relative_to(source_path)

            # 跳过已经整理过的目录（照片/ 和 视频/）
            # .parts 返回路径的各个部分元组
            # 例如 Path('照片/2025/2025-06-24/img.jpg').parts = ('照片', '2025', '2025-06-24', 'img.jpg')
            parts = relative_path.parts
            if parts and parts[0] in ('照片', '视频'):
                continue

            # 文件信息字典
            file_info = {
                'path': str(full_path),                          # 完整路径（字符串）
                'relative_path': str(relative_path),             # 相对路径
                'size': full_path.stat().st_size if full_path.exists() else 0  # 文件大小（字节）
            }

            # 根据扩展名分类
            # in 操作符判断元素是否在集合中
            if organize_photos and ext in IMAGE_EXTENSIONS:
                photos.append(file_info)
                # 进度回调：通知 UI 发现了新照片
                if progress_callback:
                    progress_callback(
                        'scanning',
                        f'📄 发现照片: {relative_path}',
                        current_file=str(relative_path),
                        count=len(photos), total=0
                    )
            elif organize_videos and ext in VIDEO_EXTENSIONS:
                videos.append(file_info)
                if progress_callback:
                    progress_callback(
                        'scanning',
                        f'🎬 发现视频: {relative_path}',
                        current_file=str(relative_path),
                        count=len(videos), total=0
                    )

    # 返回分类结果
    return {'photos': photos, 'videos': videos}


def extract_date_photo(file_path, progress_callback=None):
    """
    从照片文件的 EXIF 中提取拍摄日期。

    EXIF（Exchangeable Image File Format）是数码相机嵌入在 JPEG/TIFF 中的
    元数据标准，包含拍摄参数（光圈、快门、日期等）。

    优先级：
    1. EXIF 标签 DateTimeOriginal (0x9003, 十进制 36867)
       —— 拍摄时间，由相机记录，最准确
    2. 文件修改时间（os.path.getmtime）
       —— 回退方案，可能不准确

    Arg:
        file_path: 照片文件路径（字符串）
        progress_callback: 进度回调

    Returns:
        datetime 对象：拍摄日期时间
        如果 EXIF 和文件修改时间都无法读取，返回 None
    """
    try:
        # PIL (Pillow) 是 Python 最流行的图片处理库
        # 安装命令: pip install Pillow
        # Image.open() 打开图片文件，返回 Image 对象
        from PIL import Image

        # 打开图片文件
        # with 语句在离开代码块时自动关闭文件
        # 类似 Java 的 try-with-resources / C# 的 using
        with Image.open(file_path) as img:
            # _getexif() 读取 EXIF 数据
            # 返回 dict，key 是 EXIF 标签 ID（整数），value 是标签值
            # 注意：_getexif() 以下划线开头，表示"内部方法"
            # 但 Pillow 没有提供公有 API，这是实际中广泛使用的写法
            exif_data = img._getexif()

            if exif_data:
                # 36867 = DateTimeOriginal 标签 ID
                # 这是 EXIF 标准中记录"原始拍摄日期"的标签
                # 标签 36867 是字符串格式: 'YYYY:MM:DD HH:MM:SS'
                # 注意分隔符是冒号不是短横！这是 EXIF 标准定义的
                date_str = exif_data.get(36867)
                if date_str:
                    # strptime = string parse time
                    # 是 datetime 模块的类方法，将字符串按指定格式解析
                    # %Y: 4 位年份, %m: 2 位月份, %d: 2 位日期
                    # %H: 24 小时, %M: 分钟, %S: 秒
                    dt = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                    return dt

        # 没有 EXIF 标签 36867（比如截图、网络下载的图片）
        # 回退到文件修改时间
        # os.path.getmtime() 返回时间戳（秒，float）
        # datetime.fromtimestamp() 将时间戳转为 datetime 对象
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)

    except Exception:
        # 捕获所有异常：
        # - 文件格式不支持（如 .heic 在旧版 Pillow 中无法打开）
        # - 文件损坏
        # - EXIF 解析错误
        # 全部回退到文件修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)


def extract_date_video(file_path, progress_callback=None):
    """
    从视频文件的元数据中提取拍摄日期。

    使用 ffprobe 读取元数据。
    ffprobe 是 ffmpeg 套件中的工具，用于分析多媒体文件。
    飞牛OS（Debian）通常预装 ffmpeg/ffprobe。

    优先级：
    1. ffprobe 读取 format.tags.creation_time
       格式示例: '2025-06-24T10:30:00.000000Z'
    2. 文件修改时间（os.path.getmtime）

    Arg:
        file_path: 视频文件路径（字符串）
        progress_callback: 进度回调

    Returns:
        datetime 对象或 None
    """
    try:
        # subprocess 是 Python 标准库，用于执行外部命令
        # 类似 Java 的 Runtime.exec() / C# 的 Process.Start()
        import subprocess
        import json

        # subprocess.run() 执行外部命令并等待完成
        # capture_output=True 捕获 stdout 和 stderr
        # text=True 以文本模式返回（默认是字节模式）
        # timeout=30 超时 30 秒，防止 ffprobe 卡死
        result = subprocess.run(
            # ffprobe 命令行参数：
            # -v quiet: 只输出错误，减少噪音
            # -print_format json: 输出为 JSON 格式
            # -show_format: 显示容器格式信息（包含元数据标签）
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', str(file_path)],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            # json.loads() 将 JSON 字符串解析为 Python 对象
            # 返回 dict（对应 JSON 对象）或 list（对应 JSON 数组）
            data = json.loads(result.stdout)

            # 链式调用 .get() 获取嵌套值
            # data.get('format', {}) → 获取 format 字段，不存在则返回空 dict
            # .get('tags', {}) → 获取 tags 字段
            # .get('creation_time') → 获取 creation_time 字段
            # 这种写法避免了 KeyError 异常
            creation_time = (
                data.get('format', {})
                .get('tags', {})
                .get('creation_time')
            )

            if creation_time:
                # ffprobe 的 creation_time 是 ISO 8601 格式
                # 示例: '2025-06-24T10:30:00.000000Z'
                # 注意：某些视频没有元数据，creation_time 可能为特殊值 'now'
                # 此处尝试解析，失败则回退到文件修改时间
                if creation_time.lower() == 'now':
                    # 'now' 不是合法日期字符串，跳过，走下面的 mtime 回退
                    pass
                else:
                    # Z 表示 UTC 时间（Zulu time）
                    # 需要去掉 Z 并加上 +00:00 时区偏移才能用 fromisoformat
                    dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                    return dt

        # ffprobe 失败或无 creation_time 元数据，或 creation_time 值为 'now'
        # 回退到文件修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError,
            subprocess.TimeoutExpired, ValueError):
        # CalledProcessError: ffprobe 返回非 0 退出码
        # FileNotFoundError: ffprobe 命令不存在（未安装 ffmpeg）
        # JSONDecodeError: ffprobe 输出不是有效 JSON
        # TimeoutExpired: ffprobe 执行超时（30 秒）
        # ValueError: creation_time 格式异常（如 'now'、'Unknown' 等非日期字符串）
        # 全部回退到文件修改时间
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)


def move_file(file_path, source_dir, category, dt, mode,
              progress_callback=None):
    """
    将文件移动到目标位置。

    目标路径格式：
    - 按天: 源目录 / 照片|视频 / 年份 / 年-月-日 / 文件名
    - 按月: 源目录 / 照片|视频 / 年份 / 年-月 / 文件名

    Args:
        file_path: 源文件完整路径
        source_dir: 源目录路径（所有整理后的文件都在此目录下）
        category: '照片' 或 '视频'（决定放入照片/还是视频/子目录）
        dt: datetime 对象（拍摄日期）
        mode: 'day' 按天 或 'month' 按月
        progress_callback: 进度回调

    Returns:
        dict: {
            'success': True/False,      # 是否成功
            'dest_path': str 或 None,   # 目标路径（成功时）
            'error': str 或 None        # 错误信息（失败时）
        }
    """
    source_path = Path(source_dir)
    file_path = Path(file_path)

    # 计算年份和日期字符串
    year_str = str(dt.year)       # 如 '2025'

    if mode == 'day':
        # strftime = string format time（与 strptime 相反）
        # 将 datetime 格式化为字符串
        date_str = dt.strftime('%Y-%m-%d')  # 如 '2025-06-24'
    else:
        date_str = dt.strftime('%Y-%m')      # 如 '2025-06'

    # .name 获取文件名（包含扩展名）
    filename = file_path.name

    # 构建目标目录路径
    # Path 的 / 操作符自动处理路径分隔符
    # 最终结构: source_dir / 照片 / 2025 / 2025-06-24 /
    dest_dir = source_path / category / year_str / date_str

    # 初始目标文件路径
    dest_path = dest_dir / filename

    try:
        # 创建目标目录（递归创建所有不存在的父目录）
        # parents=True: 如果 year_str 或 父目录也不存在，一起创建
        # exist_ok=True: 如果目录已存在不报错
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 冲突处理：如果同名文件已存在，自动重命名
        # 重命名规则：文件名_1.ext → 文件名_2.ext → ...
        # 类似 macOS Finder / Windows 资源管理器的行为
        if dest_path.exists():
            name_stem = file_path.stem   # 文件名（不含扩展名）
            ext = file_path.suffix        # 扩展名（含 .）
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f'{name_stem}_{counter}{ext}'
                counter += 1

        # shutil.move() 移动文件（或重命名）
        # 类似 Linux mv 命令 / Windows move 命令
        # 可以跨文件系统移动（先复制再删除）
        # 如果目标已存在会被覆盖（但我们上面已经做了冲突处理）
        shutil.move(str(file_path), str(dest_path))

        # 返回成功结果
        return {
            'success': True,
            'dest_path': str(dest_path),
            'error': None
        }

    except (OSError, shutil.Error) as e:
        # OSError: 操作系统级错误（权限不足、磁盘满等）
        # shutil.Error: shutil 操作失败
        return {
            'success': False,
            'dest_path': None,
            'error': str(e)
        }


def organize_by_date(config, progress_callback=None):
    """
    按日期整理照片和视频的主函数。

    这是整理模块的唯一"入口函数"，被 routes/organize.py 中的后台线程调用。
    整理流程分三个阶段：
    1. 扫描目录 → 发现所有图片和视频文件
    2. 提取日期 → 从 EXIF/ffprobe 读取拍摄日期
    3. 移动文件 → 按 照片|视频/年份/日期/ 结构移动

    Args:
        config: dict 配置字典，包含：
            - 'source_dir': str      源目录路径（要整理哪个目录）
            - 'mode': 'day'|'month'  按天还是按月
            - 'organize_photos': bool 是否整理照片
            - 'organize_videos': bool 是否整理视频
        progress_callback: 进度回调函数
            函数签名: func(stage, message, **kwargs)

    Returns:
        dict 结果字典，包含：
            - 'source_dir': 源目录
            - 'mode': 整理模式
            - 'total_photos': 发现的照片数
            - 'total_videos': 发现的视频数
            - 'moved_photos': 成功移动的照片数
            - 'moved_videos': 成功移动的视频数
            - 'no_exif_photos': 无 EXIF 的照片（空列表，简化处理）
            - 'no_exif_videos': 无 ffprobe 的视频（空列表）
            - 'errors': 失败文件列表 [{file, error}, ...]
            - 'summary': {moved, failed, total}
    """
    # 从配置字典中读取参数
    # config.get('key', default) 比 config['key'] 安全
    # key 不存在时返回默认值，不会抛 KeyError
    source_dir = config['source_dir']
    mode = config.get('mode', 'day')
    organize_photos = config.get('organize_photos', True)
    organize_videos = config.get('organize_videos', True)

    if progress_callback:
        progress_callback('scanning',
                          f'🔍 正在扫描目录: {source_dir} ...',
                          current_file='', count=0, total=0)

    # ═══ 阶段 1：扫描文件 ═══
    # scan_directory 返回 {photos: [...], videos: [...]}
    scanned = scan_directory(source_dir, organize_photos, organize_videos,
                             progress_callback)

    photos = scanned.get('photos', [])
    videos = scanned.get('videos', [])

    if progress_callback:
        progress_callback('scanning',
                          f'✅ 扫描完成：{len(photos)} 张照片，{len(videos)} 个视频',
                          count=len(photos) + len(videos),
                          total=len(photos) + len(videos))

    # ═══ 阶段 2：提取日期 ═══
    # 遍历 photos 和 videos 列表，为每个文件提取拍摄日期
    if progress_callback:
        progress_callback('extracting',
                          '📅 正在提取拍摄日期...',
                          count=0, total=len(photos) + len(videos))

    # 用于记录无 EXIF/ffprobe 的文件（预留，当前实现简化处理）
    no_exif_photos = []
    no_exif_videos = []

    # 存储 (文件信息, datetime) 元组的列表
    # 只在成功提取日期时才添加
    photo_dates = []
    video_dates = []
    total_files = len(photos) + len(videos)
    processed = 0

    # 处理所有照片文件
    for f in photos:
        # 调用 EXIF 日期提取函数
        dt = extract_date_photo(f['path'], progress_callback)
        if dt is None:
            # 理论上不会走到这里（extract_date_photo 会回退到 mtime）
            # 但保留防御性判断
            continue

        # 记录文件和它对应的日期
        photo_dates.append((f, dt))
        processed += 1
        if progress_callback:
            rel = f.get('relative_path', f['path'])
            progress_callback('extracting',
                              f'📷 读取日期: {rel} → {dt.strftime("%Y-%m-%d")}',
                              current_file=rel,
                              count=processed, total=total_files)

    # 处理所有视频文件
    for f in videos:
        dt = extract_date_video(f['path'], progress_callback)
        if dt is None:
            continue
        video_dates.append((f, dt))
        processed += 1
        if progress_callback:
            rel = f.get('relative_path', f['path'])
            progress_callback('extracting',
                              f'🎬 读取日期: {rel} → {dt.strftime("%Y-%m-%d")}',
                              current_file=rel,
                              count=processed, total=total_files)

    # ═══ 阶段 3：移动文件 ═══
    if progress_callback:
        progress_callback('organizing',
                          '📦 正在移动文件...',
                          count=0, total=total_files)

    moved_photos = 0   # 成功移动的照片计数
    moved_videos = 0   # 成功移动的视频计数
    errors = []        # 失败操作列表
    moved_count = 0    # 总移动计数

    # 合并照片和视频列表，统一处理
    # (文件信息, datetime, 分类名称) 元组列表
    all_to_move = (
        [(f, dt, '照片') for f, dt in photo_dates] +
        [(f, dt, '视频') for f, dt in video_dates]
    )

    # 遍历所有待移动文件
    for f, dt, category in all_to_move:
        # 调用移动函数
        result = move_file(f['path'], source_dir, category, dt, mode,
                           progress_callback)
        moved_count += 1

        if result['success']:
            # 根据分类分别计数
            if category == '照片':
                moved_photos += 1
            else:
                moved_videos += 1
        else:
            # 记录失败信息
            errors.append({'file': f['path'], 'error': result['error']})

        if progress_callback:
            rel = f.get('relative_path', f['path'])
            action = '✅' if result['success'] else '❌'
            dest = result.get('dest_path', '')
            log_msg = f'{action} [{category}] {rel} → {dest}'
            progress_callback('organizing', log_msg,
                              current_file=rel,
                              count=moved_count, total=len(all_to_move))

    # ═══ 返回结果 ═══
    return {
        'source_dir': source_dir,
        'mode': mode,
        'total_photos': len(photos),
        'total_videos': len(videos),
        'moved_photos': moved_photos,
        'moved_videos': moved_videos,
        'no_exif_photos': no_exif_photos,
        'no_exif_videos': no_exif_videos,
        'errors': errors,
        'summary': {
            'moved': moved_photos + moved_videos,
            'failed': len(errors),
            'total': total_files
        }
    }
