"""
merger.py - 合并执行模块
========================

功能：
1. 生成合并方案：根据分析结果和配置，生成待操作文件清单
2. 执行合并：复制唯一文件，将重复文件移至回收区
3. 记录日志：所有操作写入日志文件

安全策略：
- 删除文件前先移动到回收区（.recycle 目录），绝不直接删除
- 预览模式下不执行任何写操作
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

    合并策略（以 A→B 为例）：
    - 方向 A→B：A 是源目录，B 是目标目录
    - A 中独有的文件（unique_to_a）→ 复制到 B
    - 重复文件中，A 中的副本 → 移动到回收区（B 中的保留）
    - B 的文件保持不变
    - B→A 则反过来处理

    Args:
        analysis_result: analyzer.analyze() 的返回值
        config: 配置字典

    Returns:
        dict: {
            'direction': 'a_to_b' 或 'b_to_a',
            'preview_mode': True/False,
            'source_dir': 源目录路径,
            'target_dir': 目标目录路径,
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
    direction = config.get('merge_direction', 'a_to_b')
    preview_mode = config.get('preview_mode', True)

    # ── 确定源目录和目标目录 ──
    # 源目录 = 要被合并的目录（它的文件要被处理）
    # 目标目录 = 合并到哪里去（它的文件保持不变）
    if direction == 'a_to_b':
        source_key = 'dir_a'
        target_key = 'dir_b'
        # A 中独有的文件
        unique_files = analysis_result.get('unique_to_a', [])
        # 从 A 的角度看重复组
        duplicate_groups = analysis_result.get('exact_duplicates', [])
    else:
        source_key = 'dir_b'
        target_key = 'dir_a'
        unique_files = analysis_result.get('unique_to_b', [])
        duplicate_groups = analysis_result.get('exact_duplicates', [])

    source_dir = analysis_result.get(source_key, {}).get('name', '')
    target_dir = analysis_result.get(target_key, {}).get('name', '')

    # ── 构建操作列表 ──
    operations = []

    # 操作 1：将源目录中的唯一文件复制到目标目录
    for f in unique_files:
        operations.append({
            'type': 'copy',
            'file_path': f['path'],
            'filename': f['name'],
            'size': f['size'],
            'reason': '源目录中独有的文件，需要复制到目标目录'
        })

    # 操作 2：将源目录中与目标目录重复的文件移入回收区
    # 每个重复组中，源目录对应的文件都是多余的
    for group in duplicate_groups:
        if direction == 'a_to_b':
            source_files = group.get('files_a', [])
        else:
            source_files = group.get('files_b', [])

        for f in source_files:
            operations.append({
                'type': 'delete',
                'file_path': f['path'],
                'filename': f['name'],
                'size': f['size'],
                'reason': '与目标目录中的文件重复（SHA256 相同）'
            })

    # ── 汇总 ──
    plan = {
        'direction': direction,
        'preview_mode': preview_mode,
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
    1. 检查预览模式 → 预览模式不执行，直接返回
    2. 创建回收区目录 → .recycle/时间戳/
    3. 逐条执行操作
    4. 记录日志

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
    # ── 预览模式检查 ──
    if plan.get('preview_mode'):
        logger.info("预览模式：不执行写操作")
        return {
            'success': True,
            'message': '预览模式，未执行实际操作',
            'executed_operations': [],
            'failed_operations': [],
            'recycle_dir': ''
        }

    # ── 创建回收区目录 ──
    # 在目标目录下创建 .recycle/YYYYMMDD_HHMMSS/ 目录
    # 回收区命名带时间戳，防止多次操作的文件混在一起
    target_dir = plan['target_dir']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recycle_dir = os.path.join(target_dir, '.recycle', timestamp)

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
                # ═══ 复制文件 ═══
                # 构建目标路径
                dest_path = os.path.join(
                    target_dir, op['filename']
                )
                # 如果目标文件已存在，加后缀
                if os.path.exists(dest_path):
                    name, ext = os.path.splitext(op['filename'])
                    dest_path = os.path.join(
                        target_dir,
                        f"{name}_copy{ext}"
                    )

                # shutil.copy2() 复制文件并保留元数据
                shutil.copy2(op['file_path'], dest_path)
                logger.info(f"[复制] {op['file_path']} → {dest_path}")
                executed.append(op)

            elif op['type'] == 'delete':
                # ═══ 移至回收区 ═══
                # 在回收区中的路径
                recycle_path = os.path.join(
                    recycle_dir, op['filename']
                )

                # 处理同名文件（加时间戳后缀）
                if os.path.exists(recycle_path):
                    name, ext = os.path.splitext(op['filename'])
                    recycle_path = os.path.join(
                        recycle_dir,
                        f"{name}_{timestamp}{ext}"
                    )

                # shutil.move() 移动文件到回收区
                shutil.move(op['file_path'], recycle_path)
                logger.info(f"[回收] {op['file_path']} → {recycle_path}")
                executed.append(op)

        except (OSError, shutil.Error) as e:
            logger.error(f"[失败] {op['type']} {op.get('filename','')}: {e}")
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
