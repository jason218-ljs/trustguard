# setup_pypirc.ps1
# 交互式生成 %USERPROFILE%\.pypirc，避免 Windows 上手动创建以点开头文件的麻烦。
#
# 用法：
#   .\setup_pypirc.ps1            # 正常写入（已存在会询问是否覆盖）
#   .\setup_pypirc.ps1 -Force     # 直接覆盖
#
# 说明：
#   - token 以 pypi- 开头，粘贴时不会显示在屏幕上（安全输入）
#   - 如果还没有某个 token，直接回车跳过，之后可以再跑一次本脚本补上
#   - 文件写入 %USERPROFILE%\.pypirc，权限仅限当前用户

param([switch]$Force)

$ErrorActionPreference = "Stop"

$path = Join-Path $env:USERPROFILE ".pypirc"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  .pypirc 生成向导" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  目标文件：$path"
Write-Host ""

if ((Test-Path $path) -and (-not $Force)) {
    Write-Host "⚠  该文件已存在。" -ForegroundColor Yellow
    $ans = Read-Host "   覆盖它吗？(y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") {
        Write-Host "已取消，未做任何修改。" -ForegroundColor Yellow
        exit 0
    }
}

function Read-Token {
    param([string]$Label)

    Write-Host ""
    Write-Host "--- $Label ---" -ForegroundColor Cyan
    Write-Host "   把 token 粘贴进来后回车（输入过程不显示字符，属正常现象）"
    Write-Host "   还没有的话，直接回车跳过"

    $sec = Read-Host -AsSecureString "   token"
    if ($null -eq $sec) { return "" }

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($plain)) { return "" }

    $plain = $plain.Trim()

    if (-not $plain.StartsWith("pypi-")) {
        Write-Host "   ⚠  这串字符不是以 pypi- 开头，可能复制不完整。" -ForegroundColor Yellow
        $ans = Read-Host "   仍然使用它吗？(y/N)"
        if ($ans -ne "y" -and $ans -ne "Y") { return "" }
    }

    return $plain
}

$testToken = Read-Token "TestPyPI token（测试站，先练手用）"
$prodToken = Read-Token "PyPI token（正式站，可以之后再填）"

if ([string]::IsNullOrWhiteSpace($testToken) -and [string]::IsNullOrWhiteSpace($prodToken)) {
    Write-Host ""
    Write-Host "两个 token 都为空，没有生成文件。" -ForegroundColor Yellow
    Write-Host "拿到 token 后再跑一次本脚本即可。" -ForegroundColor Yellow
    exit 0
}

# 组装内容（只写入填了 token 的站，避免留下空 password 造成迷惑性报错）
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("[distutils]")
[void]$sb.AppendLine("index-servers =")
if (-not [string]::IsNullOrWhiteSpace($prodToken)) { [void]$sb.AppendLine("    pypi") }
if (-not [string]::IsNullOrWhiteSpace($testToken)) { [void]$sb.AppendLine("    testpypi") }
[void]$sb.AppendLine("")

if (-not [string]::IsNullOrWhiteSpace($prodToken)) {
    [void]$sb.AppendLine("[pypi]")
    [void]$sb.AppendLine("username = __token__")
    [void]$sb.AppendLine("password = $prodToken")
    [void]$sb.AppendLine("")
}

if (-not [string]::IsNullOrWhiteSpace($testToken)) {
    [void]$sb.AppendLine("[testpypi]")
    [void]$sb.AppendLine("repository = https://test.pypi.org/legacy/")
    [void]$sb.AppendLine("username = __token__")
    [void]$sb.AppendLine("password = $testToken")
    [void]$sb.AppendLine("")
}

# UTF-8 无 BOM 写入
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $sb.ToString(), $utf8NoBom)

# 收紧权限：仅当前用户可读写
try {
    $acl = Get-Acl $path
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "$env:USERNAME", "FullControl", "Allow")
    $acl.SetAccessRule($rule)
    Set-Acl -Path $path -AclObject $acl
    $aclNote = "已限制为仅当前用户可访问"
} catch {
    $aclNote = "权限设置跳过（不影响使用）"
}

Write-Host ""
Write-Host "✅ 已生成：$path" -ForegroundColor Green
Write-Host "   $aclNote"
Write-Host ""
Write-Host "已写入的账号：" -ForegroundColor Cyan
if ([string]::IsNullOrWhiteSpace($testToken)) {
    Write-Host "   testpypi：未填写" -ForegroundColor Yellow
} else {
    Write-Host "   testpypi：已填写（$($testToken.Substring(0, [Math]::Min(12, $testToken.Length)))...）" -ForegroundColor Green
}
if ([string]::IsNullOrWhiteSpace($prodToken)) {
    Write-Host "   pypi    ：未填写" -ForegroundColor Yellow
} else {
    Write-Host "   pypi    ：已填写（$($prodToken.Substring(0, [Math]::Min(12, $prodToken.Length)))...）" -ForegroundColor Green
}
Write-Host ""
Write-Host "下一步：.\publish_to_pypi.ps1 -CheckOnly" -ForegroundColor Cyan
Write-Host ""
