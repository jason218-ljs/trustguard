# publish_to_pypi.ps1
# 把 trustguard 发布到 PyPI。
#
# 用法（在 trustguard 目录下打开 PowerShell）：
#   .\publish_to_pypi.ps1 -CheckOnly        # 只构建 + 自检，不上传（先跑这个）
#   .\publish_to_pypi.ps1 -Test            # 上传到 TestPyPI 练手
#   .\publish_to_pypi.ps1                  # 上传到正式 PyPI
#
# 前置准备（只需做一次）：
#   1. 注册 https://pypi.org 和 https://test.pypi.org（两个是独立账号）
#   2. 在 Account settings -> API tokens 里创建 token
#   3. 把 token 写进 %USERPROFILE%\.pypirc（见文末模板）
#
# 注意：包名 trustguard 若已被占用，需先改 pyproject.toml 里的 name。

param(
    [switch]$CheckOnly,
    [switch]$Test,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# ---------- 1. 选 Python ----------
if (-not $Python) {
    $candidates = @(
        "C:\Users\18976\.workbuddy-ai\binaries\python\versions\3.13.12\python.exe",
        "D:\Anaconda3\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $Python = $c; break } }
    if (-not $Python) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $Python = $cmd.Source } else { throw "找不到 Python，请用 -Python 指定路径" }
    }
}
Write-Host "[1/5] Python: $Python" -ForegroundColor Cyan
& $Python -c "import sys; print('      version', sys.version.split()[0])"

# ---------- 2. 环境 ----------
Write-Host "[2/5] 安装构建工具 build / twine ..." -ForegroundColor Cyan
& $Python -m pip install --quiet --upgrade build twine

# ---------- 3. 清理旧产物 ----------
Write-Host "[3/5] 清理 dist/ build/ ..." -ForegroundColor Cyan
foreach ($d in @("dist", "build", "src\trustguard.egg-info")) {
    if (Test-Path $d) { Remove-Item -Recurse -Force $d }
}

# ---------- 4. 构建 ----------
Write-Host "[4/5] 构建 sdist + wheel ..." -ForegroundColor Cyan
& $Python -m build
if ($LASTEXITCODE -ne 0) { throw "构建失败" }

Write-Host "      twine check ..." -ForegroundColor Cyan
& $Python -m twine check dist/*
if ($LASTEXITCODE -ne 0) { throw "twine check 失败（通常是 README 或元数据问题）" }

$version = (& $Python -c "import tomllib,sys; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>$null)
if (-not $version) { $version = "0.1.0" }
Write-Host "      版本：$version" -ForegroundColor Green

if ($CheckOnly) {
    Write-Host "`n✅ 构建与自检通过。产物在 dist\ 下，未上传。" -ForegroundColor Green
    Write-Host "   确认无误后执行：.\publish_to_pypi.ps1 -Test" -ForegroundColor Yellow
    exit 0
}

# ---------- 5. 上传 ----------
if ($Test) {
    Write-Host "[5/5] 上传到 TestPyPI ..." -ForegroundColor Cyan
    & $Python -m twine upload --repository testpypi dist/*
    if ($LASTEXITCODE -ne 0) { throw "上传失败。检查 .pypirc 里的 testpypi token" }
    Write-Host "`n✅ 已上传到 TestPyPI。验证安装：" -ForegroundColor Green
    Write-Host "   pip install -i https://test.pypi.org/simple/ trustguard-ai" -ForegroundColor Yellow
} else {
    Write-Host "[5/5] 上传到正式 PyPI ..." -ForegroundColor Cyan
    & $Python -m twine upload dist/*
    if ($LASTEXITCODE -ne 0) { throw "上传失败。检查 .pypirc 里的 pypi token，或该版本号是否已存在" }
    Write-Host "`n✅ 已发布。1 分钟后验证：" -ForegroundColor Green
    Write-Host "   pip install trustguard-ai" -ForegroundColor Yellow
    Write-Host "   页面：https://pypi.org/project/trustguard-ai/" -ForegroundColor Yellow
}

# ============================================================
# %USERPROFILE%\.pypirc 模板（注意：token 里包含 pypi- 前缀）
# ============================================================
# [distutils]
# index-servers =
#     pypi
#     testpypi
#
# [pypi]
# username = __token__
# password = pypi-AgEIcHlwaS5vcmc...
#
# [testpypi]
# repository = https://test.pypi.org/legacy/
# username = __token__
# password = pypi-AgENdGVzdC5weXBpLm9yZw...
