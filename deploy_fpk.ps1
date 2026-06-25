# deploy_fpk.ps1 - 部署脚本
# 用法: .\deploy_fpk.ps1
#
# 功能:
#   1. 复制源码到 image-tools/app/server/
#   2. 自动升级 patch 版本号 (1.0.0 → 1.0.1)
#   3. 通过 scp 传输到飞牛 NAS
#   4. 提示 NAS 上执行 fnpack build + 安装

# ── 配置 ── 按需修改 ──
$NAS_HOST = "100.66.1.2"
$NAS_USER = "yangqi"      # 留空则脚本中手动输入
$NAS_PORT = 22
$NAS_PATH = "/home/yangqi/image-tools"   # NAS 上的临时目录

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$FPK_DIR = Join-Path $PROJECT_ROOT "image-tools"
$SERVER_DIR = Join-Path $FPK_DIR "app\server"

# ── 1. 复制源码 ──
Write-Host "`n=== 1/4: 复制源码 ===" -ForegroundColor Cyan

$files = @(
    "main.py", "config.py", "scanner.py", "analyzer.py",
    "merger.py", "organizer.py", "dedup_single.py"
)
foreach ($f in $files) {
    Copy-Item (Join-Path $PROJECT_ROOT $f) (Join-Path $SERVER_DIR $f) -Force
}
Copy-Item (Join-Path $PROJECT_ROOT "routes\*.py") (Join-Path $SERVER_DIR "routes\") -Force
Copy-Item (Join-Path $PROJECT_ROOT "static\style.css") (Join-Path $SERVER_DIR "static\") -Force
Copy-Item (Join-Path $PROJECT_ROOT "templates\*.html") (Join-Path $SERVER_DIR "templates\") -Force

Write-Host "  源码复制完成 ($($files.Count) py + routes + templates + css)"

# ── 2. 升级版本号 ──
Write-Host "`n=== 2/4: 升级版本 ===" -ForegroundColor Cyan

$manifestPath = Join-Path $FPK_DIR "manifest"
$content = Get-Content $manifestPath -Raw

if ($content -match 'version=(\d+)\.(\d+)\.(\d+)') {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $patch = [int]$Matches[3] + 1
    $oldVer = "$major.$minor.$($Matches[3])"
    $newVer = "$major.$minor.$patch"
    $content = $content -replace "version=$oldVer", "version=$newVer"
    Set-Content -Path $manifestPath -Value $content -NoNewline
    Write-Host "  $oldVer → $newVer"
} else {
    Write-Host "  无法解析版本号，跳过" -ForegroundColor Yellow
}

# ── 3. SCP 传输到 NAS ──
Write-Host "`n=== 3/4: SCP 传输 ===" -ForegroundColor Cyan

if (-not $NAS_USER) {
    $NAS_USER = Read-Host "  输入 NAS SSH 用户名"
}

$remote = "${NAS_USER}@${NAS_HOST}:${NAS_PATH}"
Write-Host "  目标: $remote"

# 在 NAS 上先创建目录
ssh -p $NAS_PORT "${NAS_USER}@${NAS_HOST}" "mkdir -p $NAS_PATH"

# SCP 传输整个 image-tools 目录
# 用 rsync 如果可用，否则 scp
$rsyncCmd = Get-Command rsync -ErrorAction SilentlyContinue
if ($rsyncCmd) {
    rsync -avz --delete -e "ssh -p $NAS_PORT" "$FPK_DIR/" "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"
} else {
    scp -P $NAS_PORT -r "$FPK_DIR\*" "${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  SCP 失败" -ForegroundColor Red
    exit 1
}
Write-Host "  传输完成"

# ── 4. NAS 构建指令 ──
Write-Host "`n=== 4/4: NAS 构建 ===" -ForegroundColor Cyan
Write-Host @"

SSH 到 NAS 执行：
  ssh $NAS_USER@$NAS_HOST -p $NAS_PORT

  打包：
    cd $NAS_PATH
    fnpack build .

  安装（方式1：命令行安装）：
    appcenter-cli install-fpk image-tools.fpk

  安装（方式2：应用商店手动安装）：
    在飞牛 Web 界面 → 应用中心 → 手动安装 → 选择 image-tools.fpk
"@ -ForegroundColor Green

Write-Host "`n部署完成" -ForegroundColor Green
