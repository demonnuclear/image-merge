"""
merger.py - 合并执行模块
========================

功能：
1. 生成合并方案：根据分析结果和配置，生成待操作文件清单
2. 执行合并：复制唯一文件，将重复文件移至回收区
3. 记录日志：所有操作写入日志文件

安全策略：
- 删除文件前先移动到回收区（.recycle 目录），绝不直接删除
- 所有操作都有日志记录

Python 知识点：
- shutil: 高级文件操作模块（标准库）
  - shutil.copy2(): 复制文件并保留元数据（类似 cp -p）
  - shutil.move(): 移动文件（类似 mv）
- logging: 日志模块（标准库，类似 log4j / NLog）
- datetime: 日期时间处理（标准库）
"""

import os
import shutil
from datetime import datetime
import logging
from pathlib import Path


# ── 日志配置 ──
# logging 是 Python 标准库的日志模块
# 比 print() 好的地方：
#   1. 可以控制日志级别（DEBUG/INFO/WARNING/ERROR）
#   2. 可以同时输出到文件和控制台
#   3. 自带时间戳和格式化
def setup_logger():
    """配置日志记录器，同时输出到文件和控制台。"""
    logger = logging.getLogger('image_dedup')
    logger.setLevel(logging.INFO)

    # 防止重复添加 handler（多次调用 setup_logger 时）
    if not logger.handlers:
        # 文件处理器：日志写入文件
        log_file = Path(__file__).parent / 'merge.log'
        file_handler = logging.FileHandler(
            log_file, mode='a', encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)

        # 控制台处理器：日志也输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


# 创建全局日志记录器实例
logger = setup_logger()


def generate_merge_plan(analysis_result, config):
    """
    根据分析结果和配置生成合并方案。

    合并策略（合并目录 → 主目录）：
    - 主目录（dir_a）：照片的核心存放位置，合并的目标
    - 合并目录（dir_b）：要整理进来的目录
    - 合并目录中独有的文件（unique_to_b）→ 复制到主目录
    - 重复文件中，合并目录中的副本 → 移入回收区（主目录中的保留）
    - 主目录的文件始终不动

    Args:
        analysis_result: analyzer.analyze() 的返回值
        config: 配置字典

    Returns:
        dict: {
            'direction': 'merge_to_primary',
            'source_dir': 合并目录路径（来源）,
            'target_dir': 主目录路径（目的地）,
            'operations': [
                {
                    'type': 'copy' 或 'delete',
                    'file_path': 源文件完整路径,
                    'dest_path': 目标路径（仅 copy 类型有）,
                    'filename': 文件名,
                    'size': 文件大小,
                    'reason': 操作原因说明
                }, ...
            ],
            'summary': { 统计汇总 }
        }

    讲解：
        这个函数主要是「数据转换」：
        把 analyzer.py 的分析结果（分类数据）
        转换成 merger.py 需要的操作指令列表（每个文件要做什么）
        这是一种常见的编程模式：分层之间的数据转换
    """
    # ── 固定方向：合并目录 → 主目录 ──
    # 主目录 = dir_a = 合并的目标位置（文件最终到这儿）
    # 合并目录 = dir_b = 被合并的来源位置（文件从这儿取）
    source_key = 'dir_b'      # 合并目录（来源）
    target_key = 'dir_a'      # 主目录（目的地）
    unique_files = analysis_result.get('unique_to_b', [])
    duplicate_groups = analysis_result.get('exact_duplicates', [])

    source_dir = analysis_result.get(source_key, {}).get('name', '')
    target_dir = analysis_result.get(target_key, {}).get('name', '')

    # ── 构建操作列表 ──
    operations = []

    # 操作 1：将合并目录中的"唯一文件"复制到主目录
    for f in unique_files:
        operations.append({
            'type': 'copy',
            'file_path': f['path'],
            'filename': f['name'],
            'relative_path': f.get('relative_path', f['name']),
            'size': f['size'],
            'reason': '合并目录中独有的文件（主目录中没有），需要复制到主目录中'
        })

    # 操作 2：将合并目录中"与主目录重复的文件"移入回收区
    # 每个重复组中，合并目录（dir_b）里的文件是多余的
    for group in duplicate_groups:
        source_files = group.get('files_b', [])
        for f in source_files:
            operations.append({
                'type': 'delete',
                'file_path': f['path'],
                'filename': f['name'],
                'relative_path': f.get('relative_path', f['name']),
                'size': f['size'],
                'reason': '与主目录中的文件重复（SHA256 相同），主目录保留，合并目录的移入回收区'
            })

    # ── 汇总 ──
    plan = {
        'direction': 'merge_to_primary',
        'source_dir': source_dir,
        'target_dir': target_dir,
        'operations': operations,
        'summary': {
            'copy_count': sum(1 for op in operations if op['type'] == 'copy'),
            'delete_count': sum(1 for op in operations if op['type'] == 'delete'),
            'total_operations': len(operations),
            'total_size': sum(op['size'] for op in operations)
        }
    }

    return plan


def execute_merge(plan):
    """
    执行合并方案。

    流程：
    1. 创建回收区目录 → .recycle/时间戳/
    2. 逐条执行操作
    3. 记录日志

    Args:
        plan: generate_merge_plan() 返回的方案

    Returns:
        dict: {
            'success': True/False,
            'message': 结果消息,
            'executed_operations': [成功操作列表],
            'failed_operations': [失败操作列表],
            'recycle_dir': 回收区路径
        }

    讲解：
        shutil.copy2(src, dst): 复制文件
          - 比 shutil.copy() 多保留了元数据（修改时间等）
          - 类似 Linux 的 cp -p 命令

        shutil.move(src, dst): 移动文件
          - 在同一文件系统内 = os.rename()（更名操作，速度快）
          - 跨文件系统 = copy + delete（自动处理）
          - 类似 Linux 的 mv 命令
    """
    # ── 创建回收区目录（在合并目录下，与原文件同磁盘） ──
    # 例如: 文件在 /volume1/photo/merge/sub/img.jpg
    #       回收在 /volume1/photo/merge/.recycle/20260623_120000/sub/img.jpg
    # 这样回收操作不会占用主目录的磁盘空间
    target_dir = plan['target_dir']
    source_dir = plan['source_dir']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recycle_dir = os.path.join(source_dir, '.recycle', timestamp)

    try:
        # os.makedirs() 递归创建目录
        # 类似 linux 的 mkdir -p
        os.makedirs(recycle_dir, exist_ok=True)
        logger.info(f"创建回收区: {recycle_dir}")
    except OSError as e:
        logger.error(f"创建回收区失败: {e}")
        return {
            'success': False,
            'message': f'创建回收区失败: {e}',
            'executed_operations': [],
            'failed_operations': [{'error': str(e)}],
            'recycle_dir': ''
        }

    # ── 逐条执行操作 ──
    executed = []
    failed = []

    for op in plan['operations']:
        try:
            if op['type'] == 'copy':
                # ═══ 复制文件（保留合并目录的结构） ═══
                # 使用 relative_path 保留子目录结构
                # 例如: merge/sub/dir/img.jpg → primary/sub/dir/img.jpg
                rel_path = op.get('relative_path', op['filename'])
                dest_path = os.path.join(target_dir, rel_path)

                # 创建主目录中的子目录（如果不存在）
                dest_dir = os.path.dirname(dest_path)
                if dest_dir and not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)

                # 如果目标文件已存在，加后缀
                if os.path.exists(dest_path):
                    name, ext = os.path.splitext(rel_path)
                    dest_path = os.path.join(
                        target_dir,
                        f"{name}_copy{ext}"
                    )
                    # 如果加后缀后的文件也冲突，加时间戳
                    if os.path.exists(dest_path):
                        name, ext = os.path.splitext(rel_path)
                        dest_path = os.path.join(
                            target_dir,
                            f"{name}_{timestamp}{ext}"
                        )

                # shutil.copy2() 复制文件并保留元数据
                shutil.copy2(op['file_path'], dest_path)
                logger.info(f"[复制] {op['file_path']} → {dest_path}")
                executed.append(op)

            elif op['type'] == 'delete':
                # ═══ 移至回收区（保留合并目录的结构） ═══
                rel_path = op.get('relative_path', op['filename'])
                recycle_path = os.path.join(recycle_dir, rel_path)

                # 创建回收区子目录（如果不存在）
                recycle_subdir = os.path.dirname(recycle_path)
                if recycle_subdir and not os.path.exists(recycle_subdir):
                    os.makedirs(recycle_subdir, exist_ok=True)

                # 处理同名文件（加时间戳后缀）
                if os.path.exists(recycle_path):
                    name, ext = os.path.splitext(rel_path)
                    recycle_path = os.path.join(
                        recycle_dir,
                        f"{name}_{timestamp}{ext}"
                    )

                # shutil.move() 移动文件到回收区
                shutil.move(op['file_path'], recycle_path)
                logger.info(f"[回收] {op['file_path']} → {recycle_path}")
                executed.append(op)

        except (OSError, shutil.Error) as e:
            logger.error(f"[失败] {op['type']} {op.get('relative_path', op.get('filename',''))}: {e}")
            op['error'] = str(e)
            failed.append(op)

    # ── 返回执行结果 ──
    result = {
        'success': len(failed) == 0,
        'message': f'执行完成：{len(executed)} 个成功，{len(failed)} 个失败',
        'executed_operations': executed,
        'failed_operations': failed,
        'recycle_dir': recycle_dir
    }

    return result
