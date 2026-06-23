"""
main.py - 程序入口与 Flask Web 服务
===================================

功能：
启动 Web 服务，定义所有页面路由。

Python 知识点：
1. @app.route('/') 是装饰器语法（@ 符号）
   可以理解为：在函数上贴个标签，告诉 Flask 当用户访问 '/' 时执行这个函数
   类似 Java 的 @RequestMapping("/") / C# 的 [Route("/")]
   装饰器是 Python 非常强大的特性 —— 本质是一个接收函数并返回新函数的函数

2. def index(): 定义函数
   def = define function
   不需要写参数类型和返回值类型（当然也可以写，是可选的）

3. render_template() 渲染 HTML 页面
   类似 Java 的 ModelAndView / C# 的 View()
   传入的变量可以在 HTML 中使用 {{ }} 语法获取
"""

# ── 导入标准库 ──
# threading: Python 内置的多线程模块
# 用于在后台执行扫描，不阻塞前端页面响应
import threading

# ── 导入 Flask 和相关组件 ──
# from flask import Flask   的意思：从 flask 包中导入 Flask 类
# from xxx import dir_a, dir_b, c   是 Python 常用的导入方式，可以一次导入多个
# jsonify: 将 Python 字典转为 JSON 响应（供前端 AJAX 轮询）
from flask import Flask, render_template, request, redirect, url_for, jsonify

# ── 导入自己写的模块 ──
# 同一个项目内的 .py 文件之间可以直接用 import
from config import load_config, save_config, DEFAULT_CONFIG

# ── 导入项目模块（我们自己写的 .py 文件） ──
# scanner.py 负责扫描目录和计算哈希
# analyzer.py 负责分析重复关系
from scanner import scan_directories, calculate_phash_for_all
from analyzer import analyze
from merger import generate_merge_plan, execute_merge


# ── 创建 Flask 应用实例 ──
# __name__ 是 Python 的内置变量
# 当直接运行 python main.py 时，__name__ 的值是 "__main__"
# 当被其他文件 import 时，__name__ 的值是 "main"（模块名）
# Flask 需要这个参数来确定应用的根目录，以找到 templates/ 等文件夹
app = Flask(__name__)


# ── 全局变量 ──
# 这些变量用于在多个路由函数之间共享数据
# Python 中模块顶层的变量就是"全局变量"
# 在函数内部修改全局变量需要 global 声明（否则 Python 会当作局部变量）
# 警告：项目级共享用全局变量不是好习惯，但学习和原型阶段足够了
scan_result = {}       # 存储扫描结果，dict 类型
analysis_result = {}   # 存储分析结果，dict 类型
merge_plan = {}        # 存储合并方案，dict 类型
merge_result = {}      # 存储执行结果，dict 类型
current_config = load_config()  # 当前配置

# ── 扫描进度变量 ──
# 后台扫描线程会不断更新这个字典
# 前端 /progress 接口每次轮询读取它
# 字典的 key 说明：
#   status:  当前阶段标识 (scanning/phashing/analyzing/done/error)
#   message: 给人看的文字描述
#   dir_key: 正在扫描哪个目录 (dir_a / dir_b)
#   current_file: 正在处理的文件名
#   count:   已处理数量
#   total:   总数量
#   log:     日志列表（追加模式，保留最近 50 条）
scan_progress = {
    'status': 'idle',
    'message': '等待开始',
    'dir_key': '',
    'current_file': '',
    'count': 0,
    'total': 0,
    'log': [],
    'error': None
}


def run_scan_background(config):
    """
    在后台线程中执行完整的扫描+哈希+分析流程。

    这个函数被 threading.Thread 启动，在独立线程中运行。
    它会：
    1. 不断更新 scan_progress 全局变量
    2. 调用 scan_directories() 并传入进度回调
    3. 调用 calculate_phash_for_all() 并传入进度回调
    4. 调用 analyze() 分析结果
    5. 设置 status='done' 通知前端

    讲解：
        threading.Thread 是 Python 创建线程的标准方式
        注意：Python 的 GIL（全局解释器锁）对 I/O 密集型任务影响不大
        扫描和哈希计算主要是 I/O 和 CPU 混合，用线程足够
        如果是纯 CPU 密集任务，应该用 multiprocessing 替代 threading
    """
    global scan_result, analysis_result, scan_progress

    # ── 辅助函数：更新 scan_progress ──
    # 这是一个嵌套函数（闭包）
    # 它可以访问外层函数的变量（这里是 scan_progress）
    # 在 scanner.py 的回调中调用，传入当前处理的文件和状态
    def update_progress(stage, message, **kwargs):
        """更新扫描进度（由 scanner.py 的回调触发）。"""
        # 注意：scan_progress 是全局变量，所以不需要 nonlocal/global 声明
        # Python 在嵌套函数中读取全局变量会自动查找
        log_entry = message

        # 更新 scan_progress 字典
        # Python 的 dict.update() 可以一次更新多个 key
        # 类似 Java 的 putAll() 或 C# 的逐个赋值
        scan_progress.update({
            'status': 'scanning' if stage in ('dir_scan', 'file_found') else
                      'phashing' if stage == 'phash_progress' else
                      'analyzing' if stage == 'analyze' else
                      scan_progress.get('status', 'scanning'),
            'message': message,
            'dir_key': kwargs.get('dir_key', scan_progress.get('dir_key', '')),
            'current_file': kwargs.get('current_file', ''),
            'count': kwargs.get('count', scan_progress.get('count', 0)),
            'total': kwargs.get('total', scan_progress.get('total', 0)),
            'error': None
        })
        # 追加日志，限制最多 100 条
        log = scan_progress.get('log', [])
        log.append(log_entry)
        if len(log) > 100:
            log = log[-100:]
        scan_progress['log'] = log

    try:
        # ═══ 阶段 1：扫描目录 ═══
        scan_progress.update({
            'status': 'scanning',
            'message': '🔄 正在扫描目录：遍历所有子目录，识别图片文件（jpg/png/gif/bmp/webp...），计算每个文件的 SHA256 哈希值用于精确去重...',
            'log': ['[阶段1/3] 扫描目录']
        })

        # 调用 scan_directories()，传入 update_progress 作为回调
        # 这样 scanner.py 在找到每个文件时都会通知我们
        scan_result = scan_directories(config, progress_callback=update_progress)

        # ═══ 阶段 2：计算感知哈希 ═══
        scan_progress.update({
            'status': 'phashing',
            'message': '🖼️ 正在计算感知哈希（pHash）：逐张解码图片，提取视觉特征指纹，用于识别"看起来一样"的图片（即使分辨率/格式/压缩率不同）...',
            'log': scan_progress.get('log', []) + ['[阶段2/3] 计算感知哈希（pHash）']
        })

        for dir_key in ['dir_a', 'dir_b']:
            files = scan_result.get(dir_key, {}).get('files', [])
            if files:
                scan_progress['dir_key'] = dir_key
                # 传入回调，每处理一个文件上报一次进度
                scan_result[dir_key]['files'] = calculate_phash_for_all(
                    files, progress_callback=update_progress
                )

        # ═══ 阶段 3：分析重复关系 ═══
        scan_progress.update({
            'status': 'analyzing',
            'message': '📊 正在分析重复关系：比对所有文件的 SHA256 和感知哈希，找出精确重复（内容完全一样）和视觉相似（看起来一样）的图片，统计可释放空间...',
            'log': scan_progress.get('log', []) + ['[阶段3/3] 分析重复关系']
        })

        # analyze() 很快，不需要进度回调
        analysis_result = analyze(scan_result)

        # ═══ 完成 ═══
        total = analysis_result.get('summary', {}).get('total_files', 0)
        dup = analysis_result.get('summary', {}).get('exact_duplicate_count', 0)
        vis = analysis_result.get('summary', {}).get('visual_duplicate_count', 0)
        msg = f'🎉 扫描完成！共扫描 {total} 个文件，发现 {dup} 组精确重复，{vis} 组视觉相似，进入报告页查看详情'

        scan_progress.update({
            'status': 'done',
            'message': msg,
            'log': scan_progress.get('log', []) + [msg]
        })

        print(f"\n  ✅ {msg}")

    except Exception as e:
        # ═══ 异常处理 ═══
        # 后台线程的异常不会自动传到主线程
        # 所以必须用 try/except 捕获并记录到 scan_progress
        error_msg = f'扫描出错: {type(e).__name__}: {e}'
        print(f"\n  ❌ {error_msg}")
        import traceback
        traceback.print_exc()

        scan_progress.update({
            'status': 'error',
            'message': error_msg,
            'error': str(e),
            'log': scan_progress.get('log', []) + [error_msg]
        })


# ── 路由定义 ──
# @app.route() 是 Flask 的装饰器
# 第一个参数是 URL 路径，第二个参数 methods 是允许的 HTTP 方法
# 一个函数可以同时处理 GET（访问页面）和 POST（提交表单）

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    首页：配置页面。

    GET 请求  → 显示配置表单
    POST 请求 → 接收表单提交，开始扫描，跳转到报告页

    request 是 Flask 自动注入的请求对象：
    - request.method:    请求方法（'GET' 或 'POST'）
    - request.form.get(): 获取 POST 表单中的某个字段值
    """
    global scan_result, analysis_result, current_config

    if request.method == 'POST':
        # ═══ 用户提交了表单 ═══
        config = {
            'dir_a': request.form.get('dir_a', '').strip(),
            'dir_b': request.form.get('dir_b', '').strip(),
            'merge_direction': request.form.get('merge_direction', 'a_to_b'),
            'preview_mode': request.form.get('preview_mode') == 'on'
        }

        # 保存配置到文件
        save_config(config)
        current_config = config

        # ═══ 后台启动扫描线程 ═══
        # 以前这里是同步阻塞的，用户要等扫描完才能看到页面
        # 现在改为后台线程执行，用户立刻看到进度页面
        # threading.Thread(target=函数, args=(参数,)) 创建并启动线程
        # daemon=True: 主线程退出时自动终止后台线程（防止进程无法退出）
        print("\n" + "=" * 50)
        print("  在后台线程中启动扫描...")
        print("=" * 50)

        # 重置进度
        scan_progress.clear()
        scan_progress.update({
            'status': 'starting',
            'message': '正在启动扫描...',
            'log': ['正在启动扫描...']
        })

        # 启动后台线程
        # daemon=True 是守护线程模式：
        # 主线程结束 → 后台线程自动结束（不会卡住进程退出）
        thread = threading.Thread(
            target=run_scan_background,
            args=(config,),
            daemon=True
        )
        thread.start()

        # 立即跳转到进度页面，由前端 JS 轮询进度
        return render_template('scanning.html', title='扫描中...')

    # ═══ GET 请求：显示配置表单 ═══
    config = load_config()
    # render_template() 渲染 HTML 模板
    # Flask 默认在 templates/ 目录下找模板文件
    # 传入的变量可以在模板中用 {{ }} 使用
    return render_template('index.html',
                           config=config,
                           title='图片去重合并工具')


@app.route('/report')
def show_report():
    """
    分析报告页面。
    展示扫描和分析的结果。
    """
    global analysis_result
    return render_template('report.html',
                           result=analysis_result,
                           title='分析报告')


@app.route('/plan')
def show_plan():
    """
    合并方案页面。
    展示将要执行的操作列表，等待用户确认。
    """
    global analysis_result, merge_plan, current_config
    merge_plan = generate_merge_plan(analysis_result, current_config)
    return render_template('plan.html',
                           plan=merge_plan,
                           title='合并方案')


@app.route('/progress')
def progress():
    """
    AJAX 轮询接口：返回当前扫描进度（JSON 格式）。

    前端页面（scanning.html）每隔 1 秒请求这个接口：
    fetch('/progress') → 得到 JSON → 更新页面上的进度条和日志

    为什么用轮询而不是 WebSocket？
    - 轮询实现简单，只需一个 GET 接口
    - 每秒请求一次对服务器几乎无负担
    - WebSocket 需要额外库和更复杂的代码
    - 适合"扫描几秒到几十秒"这种短时间任务

    讲解：
        jsonify() 是 Flask 的辅助函数
        将 Python 字典转为 JSON 格式的 HTTP 响应
        前端 JS 可以直接用 response.json() 解析
    """
    global scan_progress
    return jsonify(scan_progress)


@app.route('/scanning')
def show_scanning():
    """
    扫描进度页面。
    用户提交表单后立即跳转到此页面。
    页面上的 JS 会自动轮询 /progress 并显示实时状态。
    扫描完成后自动跳转到 /report。
    """
    return render_template('scanning.html', title='扫描中...')


@app.route('/execute', methods=['POST'])
def execute():
    """执行合并操作。"""
    global merge_plan, merge_result
    merge_result = execute_merge(merge_plan)
    return redirect(url_for('show_result'))


@app.route('/result')
def show_result():
    """执行结果页面。"""
    global merge_result
    return render_template('result.html',
                           result=merge_result,
                           title='执行完成')


# ── 程序入口 ──
# 这是 Python 的惯用法（idiom）
# 作用：这个 .py 文件既可以作为脚本直接运行，也可以作为模块被其他文件导入
# 直接运行时 __name__ == '__main__'，启动服务器
# 被导入时不会自动启动，由导入方控制
if __name__ == '__main__':
    print('=' * 50)
    print('  图片去重合并工具 v1.0')
    print('  启动地址: http://localhost:5000')
    print('  局域网访问: http://你的IP:5000')
    print('  按 Ctrl+C 停止服务')
    print('=' * 50)

    # 启动 Flask 开发服务器
    # host='0.0.0.0' 允许局域网内其他设备访问（不只是本机）
    # debug=True:
    #   1. 代码修改后自动重启（不用手动停止再启动）
    #   2. 页面报错时显示调试信息（生产环境要关掉）
    # port=5000 端口号
    app.run(host='0.0.0.0', debug=True, port=5000)
