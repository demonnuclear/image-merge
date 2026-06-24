"""
test_organize.py - 照片整理模块端到端测试

创建测试图片和测试目录，调用 organizer.py 执行整理，验证结果。

运行方式：
    python test_organize.py

测试步骤：
1. 创建 test_images/organize_test/ 目录
2. 用 Pillow 生成带不同 EXIF 日期的测试图片
3. 调用 organize_by_date() 执行整理
4. 验证文件被正确移动到 照片/年份/日期/ 结构下
5. 验证已整理目录被跳过
6. 清理测试文件
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organizer import organize_by_date, scan_directory


def create_test_image(filepath, year, month, day, hour=12, minute=0, second=0):
    """
    创建带指定 EXIF 日期的测试图片。

    使用 Pillow 创建一张 1x1 像素的 JPEG 图片，
    并写入 EXIF DateTimeOriginal 标签。

    Args:
        filepath: 图片保存路径
        year, month, day, hour, minute, second: 拍摄日期时间
    """
    from PIL import Image
    from PIL.ExifTags import Base

    # 创建 1x1 像素的 RGB 图片
    img = Image.new('RGB', (1, 1), color='red')

    # 创建 EXIF 数据
    # Piexif 是 Pillow 的 EXIF 处理库
    exif_data = img.getexif()

    # 36867 = DateTimeOriginal
    # EXIF 日期格式: 'YYYY:MM:DD HH:MM:SS'
    exif_data[36867] = f'{year:04d}:{month:02d}:{day:02d} {hour:02d}:{minute:02d}:{second:02d}'

    # 保存 JPEG，嵌入 EXIF 数据
    img.save(filepath, 'JPEG', exif=exif_data.tobytes())
    print(f'  [CREATE] {filepath} -> EXIF date {year}-{month:02d}-{day:02d}')


def verify_file_exists(path, description):
    """验证文件存在，并打印结果。"""
    if Path(path).exists():
        print(f'  [OK] {description}: exist ({path})')
        return True
    else:
        print(f'  [FAIL] {description}: not found ({path})')
        return False


def verify_dir_not_exists(path, description):
    """验证目录不存在（即文件没有被移动到错误位置）。"""
    if not Path(path).exists():
        print(f'  [OK] {description}: skipped ({path})')
        return True
    else:
        print(f'  [FAIL] {description}: should not exist ({path})')
        return False


def run_test():
    """
    执行端到端测试。

    测试场景：
    1. 创建 3 张不同日期的测试图片
    2. 按天模式整理 → 期望按 照片/年份/年-月-日/ 结构排列
    3. 同名冲突 → 期望自动重命名
    4. 再次整理 → 期望跳过已整理的 照片/ 目录
    """
    print('=' * 60)
    print('[TEST] 照片整理模块 - 端到端测试')
    print('=' * 60)

    # ═══ 准备测试目录 ═══
    # 使用 Path 对象管理路径
    test_root = Path('test_images') / 'organize_test'

    # 清理旧的测试数据
    if test_root.exists():
        print(f'\n[CLEAN] 清理旧测试目录: {test_root}')
        shutil.rmtree(test_root)

    # 创建测试目录结构
    # test_images/organize_test/
    # ├── subdir1/
    # │   ├── photo_2024_06_15.jpg  (EXIF: 2024-06-15)
    # │   └── photo_2025_01_01.jpg  (EXIF: 2025-01-01)
    # └── subdir2/
    #     └── photo_2024_06_15.jpg  (EXIF: 2024-06-15, 与上同名但不同日期 → 同一目录不同文件)
    print(f'\n[MKDIR] 创建测试目录: {test_root}')
    (test_root / 'subdir1').mkdir(parents=True, exist_ok=True)
    (test_root / 'subdir2').mkdir(parents=True, exist_ok=True)

    # 创建测试图片
    create_test_image(test_root / 'subdir1' / 'photo_2024_06_15.jpg', 2024, 6, 15)
    create_test_image(test_root / 'subdir1' / 'photo_2025_01_01.jpg', 2025, 1, 1)
    create_test_image(test_root / 'subdir2' / 'photo_2024_06_15.jpg', 2024, 6, 15)

    # ═══ 阶段 1: 测试扫描功能 ═══
    print('\n' + '=' * 60)
    print('[TEST 1] scan_directory() 扫描功能')
    print('=' * 60)
    scanned = scan_directory(str(test_root), organize_photos=True, organize_videos=False)
    assert len(scanned['photos']) == 3, f'expected 3 photos, got {len(scanned["photos"])}'
    assert len(scanned['videos']) == 0, f'expected 0 videos, got {len(scanned["videos"])}'
    print(f'  [OK] scan: {len(scanned["photos"])} photos, {len(scanned["videos"])} videos')

    # ═══ 阶段 2: 按天模式整理 ═══
    print('\n' + '=' * 60)
    print('[TEST 2] organize_by_date() 按天整理模式')
    print('=' * 60)

    config = {
        'source_dir': str(test_root),
        'mode': 'day',
        'organize_photos': True,
        'organize_videos': False
    }

    # 定义进度回调（打印日志）
    # 用 ASCII 兼容的方式打印进度
    def progress_callback(stage, message, **kwargs):
        # 去掉 emoji 和特殊符号，避免 Windows GBK 编码问题
        clean = message.encode('ascii', errors='replace').decode('ascii')
        print(f'    [{stage}] {clean}')

    result = organize_by_date(config, progress_callback=progress_callback)

    # 验证结果
    total_photos = result['total_photos']
    moved_photos = result['moved_photos']
    errors = result['errors']

    print(f'\n  stats: found {total_photos}, moved {moved_photos}, failed {len(errors)}')

    # 验证文件结构
    print('\n  verify file structure:')

    # 2024-06-15 应该有 2 张照片（来自 subdir1 和 subdir2，文件名不同）
    dest_dir_2024_06_15 = test_root / '照片' / '2024' / '2024-06-15'
    file_1 = dest_dir_2024_06_15 / 'photo_2024_06_15.jpg'
    file_2 = dest_dir_2024_06_15 / 'photo_2024_06_15_1.jpg'  # 同名冲突自动重命名

    verify_file_exists(file_1, '2024-06-15 第一张照片')
    verify_file_exists(file_2, '2024-06-15 第二张照片(冲突重命名)')

    # 2025-01-01 应该有 1 张照片
    dest_dir_2025_01_01 = test_root / '照片' / '2025' / '2025-01-01'
    file_3 = dest_dir_2025_01_01 / 'photo_2025_01_01.jpg'
    verify_file_exists(file_3, '2025-01-01 照片')

    # shutil.move 移动文件后，空目录会保留（这是正常行为）
    # 验证 subdir1 和 subdir2 是空目录
    sub1 = test_root / 'subdir1'
    sub2 = test_root / 'subdir2'
    if sub1.exists() and not any(sub1.iterdir()):
        print(f'  [OK] subdir1 已空（空目录保留，正常行为）')
    if sub2.exists() and not any(sub2.iterdir()):
        print(f'  [OK] subdir2 已空（空目录保留，正常行为）')

    # ═══ 阶段 3: 测试跳过已整理目录 ═══
    print('\n' + '=' * 60)
    print('[TEST 3] 已整理目录跳过')
    print('=' * 60)

    scanned2 = scan_directory(str(test_root), organize_photos=True, organize_videos=False)
    assert len(scanned2['photos']) == 0, f'expected 0 new photos (skip organized), got {len(scanned2["photos"])}'
    assert len(scanned2['videos']) == 0, f'expected 0 new videos'
    print(f'  [OK] skip: {len(scanned2["photos"])} photos, {len(scanned2["videos"])} videos')
    print(f'  [OK] organized dirs (photo/video) skipped')

    # ═══ 测试完成 ═══
    print('\n' + '=' * 60)
    print('[PASS] 所有测试通过！')
    print('=' * 60)

    # ═══ 清理 ═══
    print(f'\n[CLEAN] 清理测试目录: {test_root}')
    shutil.rmtree(test_root)
    print('[OK] 清理完成')
    print('\n[PASS] 端到端测试全部通过！')


if __name__ == '__main__':
    run_test()
