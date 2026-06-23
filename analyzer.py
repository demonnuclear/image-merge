"""
analyzer.py - 去重分析模块
==========================

功能：
1. 对比两个目录的文件列表，找出重复和唯一的文件
2. 将文件分为四类：完全重复、视觉重复、目录内重复、唯一文件
3. 统计重复数量、可释放空间等汇总指标

算法核心：
- 先用 SHA256 做精确分组（O(n) 时间）
- 再用集合运算找重复（O(1) 时间）
- 最后对「唯一文件」中的两两比较 pHash（O(n²) 时间，但数据量已缩小）

Python 知识点：
- 字典的 .setdefault(): 类似 Java 的 computeIfAbsent()
- 集合的 &、-、| 运算符: 交集、差集、并集
- 列表推导式: 简洁构建列表
- extend() vs append(): 前者展开添加，后者作为整体添加
"""


def analyze(scan_result, progress_callback=None):
    """
    分析扫描结果，找出所有重复关系。

    参数 scan_result 的结构（来自 scanner.scan_directories()）：
    {
        'dir_a': { 'path': '...', 'files': [...], 'total_count': N, 'total_size': N },
        'dir_b': { ... }
    }

    返回的分析结果结构：
    {
        'dir_a': { 目录 A 的统计 },
        'dir_b': { 目录 B 的统计 },
        'exact_duplicates': [完全重复组],      # SHA256 相同的文件
        'visual_duplicates': [视觉相似组],     # SHA256 不同但 pHash 相近
        'unique_to_a': [仅 A 有的文件],
        'unique_to_b': [仅 B 有的文件],
        'self_duplicates_a': [A 内部重复],
        'self_duplicates_b': [B 内部重复],
        'summary': { 汇总统计 }
    }

    Args:
        scan_result: scanner.scan_directories() 返回的结果
        progress_callback: 进度回调函数，在视觉对比阶段逐对上报进度
    """
    # ── 提取文件列表 ──
    # scan_result.get('dir_a', {}) 是「安全获取」
    # 如果 'dir_a' 不存在或为空，返回空字典 {}
    # 然后再 .get('files', []) 获取文件列表，不存在则返回空列表 []
    # 这种链式调用在 Python 中很常见
    files_a = scan_result.get('dir_a', {}).get('files', [])
    files_b = scan_result.get('dir_b', {}).get('files', [])

    # ── Step 1: 构建 SHA256 索引 ──
    # 为什么要建立索引？
    # 如果没有索引，要找两个目录中的重复文件需要两层循环：
    #   for f_a in files_a:          # O(n)
    #       for f_b in files_b:      # O(m)
    #           if f_a.sha256 == f_b.sha256: ...
    # 总复杂度 O(n*m)，如果有 10000 个文件，就是 1 亿次比较！
    #
    # 用字典索引后：
    #   1. 遍历 A，把每个 SHA256 作为 key 放入字典  → O(n)
    #   2. 遍历 B，对每个 SHA256 去字典中查找     → O(m)
    # 总复杂度 O(n+m)，10000 个文件只需 20000 次操作
    #
    # 这就是「哈希表」的威力：以空间换时间！

    # SHA256 → [文件列表] 的映射
    # 值是列表而不是单个文件，因为同一个目录内可能就有 SHA256 相同的文件（目录内重复）
    sha_index_a = {}
    for f in files_a:
        sha = f.get('sha256')
        if sha is None:
            continue  # SHA256 计算失败的文件跳过
        # .setdefault(key, default) 是字典的重要方法：
        # 如果 key 存在，返回已有值
        # 如果 key 不存在，设置默认值并返回
        # 类似 Java 的 computeIfAbsent()
        sha_index_a.setdefault(sha, []).append(f)

    sha_index_b = {}
    for f in files_b:
        sha = f.get('sha256')
        if sha is None:
            continue
        sha_index_b.setdefault(sha, []).append(f)

    # ── Step 2: 用集合运算找出重复和唯一的 SHA256 ──
    # set(字典.keys()) 提取所有 key 并转为集合
    # Python 的集合支持数学运算符：
    #   set_a & set_b  → 交集（两个都有的）
    #   set_a - set_b  → 差集（A 有但 B 没有的）
    #   set_a | set_b  → 并集（所有）
    set_a = set(sha_index_a.keys())
    set_b = set(sha_index_b.keys())

    # 完全重复的 SHA256（两个目录都有相同的 SHA256）
    common_sha256 = set_a & set_b

    # 仅 A 有的 SHA256
    unique_sha_a = set_a - set_b

    # 仅 B 有的 SHA256
    unique_sha_b = set_b - set_a

    # ── Step 3: 构建完全重复组列表 ──
    # 对于每个重复的 SHA256，记录 A 和 B 中对应的文件
    exact_duplicates = []
    for sha in common_sha256:
        exact_duplicates.append({
            'sha256': sha,
            'files_a': sha_index_a[sha],  # A 中的文件（可能有多个）
            'files_b': sha_index_b[sha],  # B 中的文件（可能有多个）
            'count': len(sha_index_a[sha]) + len(sha_index_b[sha]),
            'size_per_file': sha_index_a[sha][0]['size']
        })

    # ── Step 4: 找出目录内重复 ──
    # 同一个目录内，同一个 SHA256 对应多个文件的情况
    # 比如你把同一张照片复制粘贴了多次

    self_duplicates_a = []
    for sha, files in sha_index_a.items():
        if len(files) > 1:
            self_duplicates_a.append({
                'sha256': sha,
                'files': files,
                'count': len(files),
                'size_per_file': files[0]['size']
            })

    self_duplicates_b = []
    for sha, files in sha_index_b.items():
        if len(files) > 1:
            self_duplicates_b.append({
                'sha256': sha,
                'files': files,
                'count': len(files),
                'size_per_file': files[0]['size']
            })

    # ── Step 5: 收集唯一文件 ──
    # SHA256 只在一个目录中的文件
    unique_to_a = []
    for sha in unique_sha_a:
        # extend() 将一个列表中的所有元素追加到另一个列表
        # 和 append() 的区别：
        #   list.append([1,2,3])  → [..., [1,2,3]]
        #   list.extend([1,2,3])  → [..., 1, 2, 3]
        unique_to_a.extend(sha_index_a[sha])

    unique_to_b = []
    for sha in unique_sha_b:
        unique_to_b.extend(sha_index_b[sha])

    # ── Step 6: 视觉相似检测 ──
    # 在「唯一文件」中，比较 pHash，找出视觉相似的文件
    # 注意：这是一个 O(n²) 的操作，如果唯一文件很多会很慢
    # 这里只做简单的实现，实际优化可以用 BK-tree 等算法

    visual_duplicates = []
    # 简化实现：只在唯一文件较少时启用视觉检测
    # 如果两个目录的唯一文件都超过 200 个，跳过视觉检测
    MAX_VISUAL_CHECK = 200

    if (len(unique_to_a) <= MAX_VISUAL_CHECK and
        len(unique_to_b) <= MAX_VISUAL_CHECK and
        unique_to_a and unique_to_b):
        # 计算总比较次数，用于进度显示
        total_comparisons = len(unique_to_a) * len(unique_to_b)
        # 每比较完 ~20 对上报一次进度，防止日志刷屏
        log_interval = max(1, total_comparisons // 20)

        # 通知回调：开始视觉对比
        if progress_callback:
            progress_callback('visual_compare',
                              f'🔍 开始视觉相似对比：源目录 {len(unique_to_a)} 个文件 × 目标目录 {len(unique_to_b)} 个文件 = {total_comparisons} 次逐对比较...',
                              current_file='', count=0, total=total_comparisons)

        compare_count = 0
        for f_a in unique_to_a:
            phash_a = f_a.get('phash')
            if not phash_a:
                continue
            for f_b in unique_to_b:
                phash_b = f_b.get('phash')
                if not phash_b:
                    continue
                compare_count += 1

                # 计算两个十六进制哈希值的汉明距离
                # int(x, 16) 将十六进制字符串转为整数
                # bin(x) 将整数转为二进制字符串
                # .count('1') 统计二进制中 1 的个数（即不同位的数量）
                hamming = bin(
                    int(phash_a, 16) ^ int(phash_b, 16)
                ).count('1')

                # 每 log_interval 次或找到匹配时上报进度
                # 这样用户能清楚看到正在对比哪两个文件
                if progress_callback and (
                    compare_count % log_interval == 0 or hamming <= 10
                ):
                    rel_a = f_a.get('relative_path', f_a.get('name', ''))
                    rel_b = f_b.get('relative_path', f_b.get('name', ''))
                    if hamming <= 10:
                        log_msg = (f'✅ 发现视觉相似: [源] {rel_a} ↔ [目标] {rel_b}'
                                   f'（汉明距离: {hamming}）')
                    else:
                        log_msg = (f'🔄 正在逐对比对第 {compare_count}/{total_comparisons} 对:'
                                   f' [源] {rel_a} ↔ [目标] {rel_b}'
                                   f'（汉明距离: {hamming}）')
                    progress_callback('visual_compare', log_msg,
                                      current_file=rel_a,
                                      count=compare_count, total=total_comparisons)

                # 汉明距离 ≤ 10 视为视觉相似
                if hamming <= 10:
                    visual_duplicates.append({
                        'file_a': f_a,
                        'file_b': f_b,
                        'hamming_distance': hamming
                    })

    # ── Step 7: 汇总统计 ──
    # 计算可释放的空间
    # 对于每个重复组，保留一份，多余的可以删掉
    reclaimable = 0

    for item in exact_duplicates:
        # 每个重复组，保留 1 份，其余都可以释放
        # count 是 A+B 的总文件数，减 1 就是可释放的数量
        reclaimable += (item['count'] - 1) * item['size_per_file']

    for item in self_duplicates_a:
        reclaimable += (item['count'] - 1) * item['size_per_file']

    for item in self_duplicates_b:
        reclaimable += (item['count'] - 1) * item['size_per_file']

    result = {
        'dir_a': {
            'name': scan_result.get('dir_a', {}).get('path', '目录 A'),
            'total_count': scan_result.get('dir_a', {}).get('total_count', 0),
            'total_size': scan_result.get('dir_a', {}).get('total_size', 0)
        },
        'dir_b': {
            'name': scan_result.get('dir_b', {}).get('path', '目录 B'),
            'total_count': scan_result.get('dir_b', {}).get('total_count', 0),
            'total_size': scan_result.get('dir_b', {}).get('total_size', 0)
        },
        'exact_duplicates': exact_duplicates,
        'visual_duplicates': visual_duplicates,
        'unique_to_a': unique_to_a,
        'unique_to_b': unique_to_b,
        'self_duplicates_a': self_duplicates_a,
        'self_duplicates_b': self_duplicates_b,
        'summary': {
            'total_files': (
                scan_result.get('dir_a', {}).get('total_count', 0) +
                scan_result.get('dir_b', {}).get('total_count', 0)
            ),
            'exact_duplicate_count': len(exact_duplicates),
            'visual_duplicate_count': len(visual_duplicates),
            'unique_to_a_count': len(unique_to_a),
            'unique_to_b_count': len(unique_to_b),
            'self_duplicates_a_count': len(self_duplicates_a),
            'self_duplicates_b_count': len(self_duplicates_b),
            'reclaimable_size': reclaimable
        }
    }

    return result
