"""
routes/dedup_single.py - 单目录查重模块路由
==============================

使用 Flask Blueprint 组织路由，与去重合并和照片整理完全独立。

路由列表：
  /dedup-single/              GET  → 配置页
  /dedup-single/              POST → 启动后台扫描
  /dedup-single/progress      GET  → AJAX 进度 JSON
  /dedup-single/scanning      GET  → 扫描进度页
  /dedup-single/report        GET  → 对比报告页
  /dedup-single/preview/<path> GET → 缩略图（PIL 缩放）
  /dedup-single/delete        POST → 执行删除
  /dedup-single/result        GET  → 删除结果页
"""

import threading
from flask import Blueprint, render_template, request, jsonify, send_file
from pathlib import Path
import io

from PIL import Image

from dedup_single import (
    scan_directory, compute_phash_all, group_duplicates,
    get_image_dimensions, delete_files
)

dedup_single_bp = Blueprint('dedup_single', __name__, template_folder='../templates')


# ── 全局进度状态 ──
dedup_progress = {
    'status': 'idle',
    'message': '',
    'current_file': '',
    'count': 0,
    'total': 0,
    'log': [],
    'result': None,
    'error': None
}

# 存储扫描结果，供报告页和删除操作使用
dedup_result = {
    'source_dir': '',
    'groups': [],
    'all_files': [],
    'summary': {}
}


@dedup_single_bp.route('/dedup-single/', methods=['GET', 'POST'])
def dedup_single_page():
    """
    配置页 / 启动扫描。

    GET → 显示配置表单
    POST → 接收目录路径，启动后台扫描线程
    """
    if request.method == 'POST':
        source_dir = request.form.get('source_dir', '').strip()

        dedup_progress.clear()
        dedup_progress.update({
            'status': 'starting',
            'message': '正在启动扫描...',
            'log': ['正在启动扫描...']
        })

        config = {'source_dir': source_dir}
        thread = threading.Thread(
            target=run_dedup_background,
            args=(config,),
            daemon=True
        )
        thread.start()

        return render_template('dedup_single_scanning.html', title='扫描中...')

    return render_template('dedup_single.html', title='单目录查重')


@dedup_single_bp.route('/dedup-single/progress')
def dedup_progress_api():
    """AJAX 进度接口，返回 JSON。"""
    return jsonify(dedup_progress)


@dedup_single_bp.route('/dedup-single/scanning')
def dedup_scanning():
    """扫描进度页面。"""
    return render_template('dedup_single_scanning.html', title='扫描中...')


@dedup_single_bp.route('/dedup-single/report')
def dedup_report():
    """对比报告页面。"""
    return render_template('dedup_single_report.html',
                           result=dedup_result,
                           title='查重报告')


@dedup_single_bp.route('/dedup-single/preview/<path:filename>')
def dedup_preview(filename):
    """
    缩略图路由。

    读取源文件，缩放到最大 300px 宽，返回 JPEG 缩略图。
    这样报告页展示缩略图不需要前端处理，直接 <img src="..."> 即可。

    参数 filename 是相对于源目录的路径（如 subdir/img.jpg）。
    """
    try:
        source_dir = dedup_result.get('source_dir', '')
        if not source_dir:
            return 'No source directory', 400

        file_path = Path(source_dir) / filename

        if not file_path.exists():
            return 'File not found', 404

        # 用 PIL 缩放图片到最大 300px
        img = Image.open(str(file_path))
        img.thumbnail((300, 300), Image.LANCZOS)

        # 转为 JPEG 字节流，不从磁盘写临时文件
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=85)
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')

    except Exception as e:
        return str(e), 500


@dedup_single_bp.route('/dedup-single/delete', methods=['POST'])
def dedup_delete():
    """
    执行删除——仅移入回收区，不是永久删除。

    从表单获取被勾选的文件路径列表，
    调用 delete_files() 移入 .recycle/ 目录。
    """
    global dedup_result

    selected = request.form.getlist('selected_files')
    source_dir = dedup_result.get('source_dir', '')

    if not selected:
        return render_template('dedup_single_report.html',
                               result=dedup_result,
                               error='没有选择任何文件',
                               title='查重报告')

    def update_progress(stage, message, **kwargs):
        log_entry = message
        dedup_progress.update({
            'status': stage,
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0)
        })
        log = dedup_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        dedup_progress['log'] = log

    result = delete_files(selected, source_dir, progress_callback=update_progress)

    return render_template('dedup_single_result.html',
                           result=result,
                           title='删除结果')


@dedup_single_bp.route('/dedup-single/result')
def dedup_result_page():
    """删除结果页面。"""
    return render_template('dedup_single_result.html',
                           result=dedup_progress.get('result', {}),
                           title='删除结果')


def run_dedup_background(config):
    """
    在后台线程中执行扫描 → pHash → 分组 流程。

    和去重合并的 run_scan_background 模式完全相同：
    通过 dedup_progress 全局变量向前端报告实时进度。
    前端 JS 每秒轮询 /dedup-single/progress 接口。
    """
    global dedup_result, dedup_progress

    def update_progress(stage, message, **kwargs):
        """更新进度（由 dedup_single.py 的回调触发）。"""
        log_entry = message
        dedup_progress.update({
            'status': ('scanning' if stage == 'scanning' else
                       'phashing' if stage == 'phashing' else
                       'grouping' if stage == 'grouping' else
                       dedup_progress.get('status', 'scanning')),
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0),
            'error': None
        })
        log = dedup_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        dedup_progress['log'] = log

    try:
        source_dir = config['source_dir']

        # ═══ 阶段 1：扫描 + SHA256 ═══
        dedup_progress.update({
            'status': 'scanning',
            'message': '正在扫描目录，计算 SHA256...',
            'log': ['[阶段1/3] 扫描目录 —— 遍历文件，计算 SHA256']
        })
        all_files = scan_directory(source_dir, progress_callback=update_progress)

        # ═══ 阶段 2：计算 pHash ═══
        dedup_progress.update({
            'status': 'phashing',
            'message': '正在计算感知哈希（pHash），逐张解码图片...',
            'log': dedup_progress.get('log', []) +
                   ['[阶段2/3] 计算感知哈希 —— 逐张解码图片，提取视觉指纹']
        })
        all_files = compute_phash_all(all_files, progress_callback=update_progress)

        # ═══ 阶段 3：分组 ═══
        dedup_progress.update({
            'status': 'grouping',
            'message': '正在分组比对：SHA256 精确分组 → pHash 视觉相似分组...',
            'log': dedup_progress.get('log', []) +
                   ['[阶段3/3] 分组 —— SHA256 精确分组 → pHash 视觉相似分组']
        })
        groups = group_duplicates(all_files)

        # 为每个文件获取分辨率信息
        for group in groups:
            for f in group['files']:
                f['dimensions'] = get_image_dimensions(f['path'])

        # 保存结果供报告页使用
        dedup_result = {
            'source_dir': source_dir,
            'groups': groups,
            'all_files': all_files,
            'summary': {
                'total_files': len(all_files),
                'total_groups': len(groups),
                'total_duplicate_files': sum(len(g['files']) for g in groups)
            }
        }

        total_dup = sum(len(g['files']) for g in groups)
        dedup_progress.update({
            'status': 'done',
            'message': (f'扫描完成！共 {len(all_files)} 个文件，'
                        f'发现 {len(groups)} 组重复'
                        f'（共 {total_dup} 个文件）'),
            'log': dedup_progress.get('log', []) + ['✅ 扫描完成']
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f'扫描出错: {type(e).__name__}: {e}'
        dedup_progress.update({
            'status': 'error',
            'message': error_msg,
            'error': str(e),
            'log': dedup_progress.get('log', []) + [error_msg]
        })
