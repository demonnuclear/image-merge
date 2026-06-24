"""
routes/organize.py - 照片整理模块路由
=======================

使用 Flask Blueprint 组织路由，注册到主应用。

路由列表：
  /organize/       GET  → 整理配置页
  /organize/       POST → 启动后台整理线程
  /organize/progress  GET → AJAX 进度 JSON
  /organize/scanning  GET → 进度页
  /organize/result    GET → 结果页

Blueprint 是 Flask 提供的模块化路由机制：
- 类似 Java Spring 的 @RequestMapping("/api/users") 分组
- 类似 C# 的 Area 机制
- 每个 Blueprint 有自己的路由前缀、模板目录和静态文件目录
"""

import threading
import time
from flask import Blueprint, render_template, request, jsonify

# 创建 Blueprint 实例
# 第一个参数 'organize' 是蓝图名称：
#   - 用于 url_for('organize.xxx') 反向生成 URL
#   - 例如 url_for('organize.organize_page') 生成 /organize/
# 第二个参数 __name__ 是当前模块名，Flask 用它确定模板查找路径
# template_folder='../templates'：
#   routes/ 是子目录，模板在项目根目录的 templates/ 下
#   所以需要相对路径 ../templates 从 routes/ 回到项目根再找 templates/
organize_bp = Blueprint('organize', __name__, template_folder='../templates')


# ── 全局进度状态 ──
# 照片整理模块的进度，与去重模块的 scan_progress 完全独立
# 各自模块维护各自的进度变量，互不干扰
# Python 的模块级变量相当于 Java/C# 中的 static 字段
organize_progress = {
    'status': 'idle',       # idle / scanning / extracting / organizing / done / error
    'message': '',          # 当前状态描述文字，会显示在前端页面上
    'current_file': '',     # 正在处理的文件名
    'count': 0,             # 已处理文件数
    'total': 0,             # 总文件数
    'log': [],              # 日志列表，最多保留 300 条
    'result': None,         # 整理完成后的结果数据（dict）
    'error': None           # 出错时的错误信息
}


@organize_bp.route('/organize/', methods=['GET', 'POST'])
def organize_page():
    """
    整理配置页。

    GET 请求 → 显示配置表单
    POST 请求 → 接收表单数据，启动后台整理线程

    Flask 中用 request.method 判断请求方法
    一个路由函数可以同时处理 GET 和 POST
    """
    if request.method == 'POST':
        # ═══ 用户提交了表单 ═══
        # request.form.get() 获取 POST 表单字段
        # .strip() 去除首尾空格（用户可能不小心打了空格）
        source_dir = request.form.get('source_dir', '').strip()

        # mode 的值是 'day' 或 'month'
        # radio button 默认选中 'day'
        mode = request.form.get('mode', 'day')

        # checkbox 选中时值为 'on'，未选中则返回 None
        # == 'on' 转为布尔值 True/False
        organize_photos = request.form.get('organize_photos') == 'on'
        organize_videos = request.form.get('organize_videos') == 'on'

        # 重置进度变量到初始状态
        # .clear() 清空字典所有键，.update() 批量设置新值
        organize_progress.clear()
        organize_progress.update({
            'status': 'starting',
            'message': '正在启动整理...',
            'log': ['正在启动整理...']
        })

        # 构建配置字典，传给后台线程
        # dict 是 Python 的字典类型，类似 Java 的 HashMap / C# 的 Dictionary
        config = {
            'source_dir': source_dir,
            'mode': mode,
            'organize_photos': organize_photos,
            'organize_videos': organize_videos
        }

        # 启动后台线程
        # threading.Thread 是 Python 创建线程的标准方式
        # target=函数名：线程启动后执行的函数
        # args=(config,)：传递给函数的参数（注意逗号，单元素元组需要）
        # daemon=True：守护线程模式，主线程结束时自动终止
        thread = threading.Thread(
            target=run_organize_background,
            args=(config,),
            daemon=True
        )
        thread.start()

        # 立即跳转到进度页面，不等待整理完成
        # 前端 JS 会每秒轮询 /organize/progress 接口获取最新进度
        return render_template('organizing.html', title='整理中...')

    # ═══ GET 请求：显示配置页面 ═══
    return render_template('organize.html', title='照片整理')


@organize_bp.route('/organize/progress')
def organize_progress_api():
    """
    AJAX 进度接口。

    前端 JS 每秒轮询这个接口，获取最新的进度状态。
    jsonify() 将 Python 字典自动转为 JSON 字符串返回。
    相当于 Java 的 @ResponseBody / C# 的 return Json()。
    """
    return jsonify(organize_progress)


@organize_bp.route('/organize/scanning')
def organize_scanning():
    """整理进度页面（前端轮询）。"""
    return render_template('organizing.html', title='整理中...')


@organize_bp.route('/organize/result')
def organize_result():
    """
    整理结果页面。

    显示整理完成后的统计数据：
    - 移动了多少张照片、多少个视频
    - 失败的文件列表
    """
    result = organize_progress.get('result', {})
    return render_template('organize_result.html',
                           result=result,
                           title='整理结果')


def run_organize_background(config):
    """
    在后台线程中执行整理流程。

    这个函数被 threading.Thread 在独立线程中调用。
    类似 Java 的 Runnable.run() / C# 的 ThreadStart。

    流程：
    1. 扫描源目录，发现图片和视频文件
    2. 提取每个文件的拍摄日期（照片读 EXIF，视频用 ffprobe）
    3. 按「年份/日期」结构移动到对应目录

    Args:
        config: dict，包含 source_dir / mode / organize_photos / organize_videos
    """
    global organize_progress

    # ── 嵌套函数：更新进度（闭包） ──
    # 这个函数定义在 run_organize_background 内部
    # 它可以访问外层函数的变量（config, organize_progress 等）
    # 类似 Java 匿名内部类 / C# 的 lambda 表达式
    def update_progress(stage, message, **kwargs):
        """
        更新进度状态。

        Args:
            stage: 阶段标识（scanning / extracting / organizing）
            message: 日志消息文本
            **kwargs: 关键字参数，可以传 current_file / count / total 等
        """
        log_entry = message

        # 根据 stage 更新 status
        # organize_progress 是全局变量，可以直接读取和修改
        organize_progress.update({
            'status': ('organizing' if stage == 'organizing' else
                       'extracting' if stage == 'extracting' else
                       'scanning' if stage == 'scanning' else
                       organize_progress.get('status', 'organizing')),
            'message': message,
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', 0),
            'total': kwargs.get('total', 0),
            'error': None
        })

        # 追加日志，限制最多 300 条
        log = organize_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 300:
            log = log[-300:]
        organize_progress['log'] = log

    try:
        # 延迟导入 organizer 模块
        # 因为 organizer.py 还没创建，但路由定义需要先能加载
        from organizer import organize_by_date

        # 执行核心整理逻辑
        # organize_by_date() 会调用 update_progress() 报告进度
        result = organize_by_date(config, progress_callback=update_progress)

        # ═══ 整理完成 ═══
        organize_progress.update({
            'status': 'done',
            'message': (f'✅ 整理完成！照片 {result.get("moved_photos", 0)} 个，'
                        f'视频 {result.get("moved_videos", 0)} 个'),
            'result': result,
            'log': organize_progress.get('log', []) + [
                f'✅ 整理完成：{result.get("moved_photos", 0)} 张照片，'
                f'{result.get("moved_videos", 0)} 个视频'
            ]
        })

    except Exception as e:
        # ═══ 异常处理 ═══
        # 后台线程的异常不会自动传到主线程
        # 必须用 try/except 捕获并记录到 organize_progress
        import traceback
        traceback.print_exc()
        error_msg = f'整理出错: {type(e).__name__}: {e}'
        organize_progress.update({
            'status': 'error',
            'message': error_msg,
            'error': str(e),
            'log': organize_progress.get('log', []) + [error_msg]
        })
