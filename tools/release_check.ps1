[CmdletBinding()]
param(
    [Parameter()]
    [string]$Output
)

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Version = (Get-Content -LiteralPath (Join-Path $Root 'VERSION') -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $env:USERPROFILE "Desktop\功能控制中心-$Version-交付包.zip"
}
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Static = [System.IO.Path]::GetFullPath((Join-Path $Root 'backend\app\web\static'))
$ExpectedStatic = [System.IO.Path]::GetFullPath((Join-Path $Root 'backend\app\web\static'))

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "没有找到项目虚拟环境：$Python"
}
if ($Static -ne $ExpectedStatic -or -not $Static.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "静态资源目标目录不安全：$Static"
}

Write-Host '[1/7] 后端测试'
Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw '后端测试失败' }
}
finally {
    Pop-Location
}

Write-Host '[2/7] 前端测试'
Push-Location (Join-Path $Root 'frontend')
try {
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw '前端测试失败' }

    Write-Host '[3/7] 前端生产构建'
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端生产构建失败' }
}
finally {
    Pop-Location
}

Write-Host '[4/7] 同步生产静态资源'
if (Test-Path -LiteralPath $Static) {
    Remove-Item -LiteralPath $Static -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root 'frontend\dist') -Destination $Static -Recurse

Write-Host '[5/7] 生成客户交付 ZIP'
& $Python (Join-Path $Root 'tools\build_delivery.py') --output $Output
if ($LASTEXITCODE -ne 0) { throw '交付包生成失败' }

Write-Host '[6/7] 校验交付结构与校验和'
& $Python (Join-Path $Root 'tools\verify_delivery.py') $Output
if ($LASTEXITCODE -ne 0) { throw '交付包完整性校验失败' }

Write-Host '[7/7] 按平台规则校验内嵌功能包'
& $Python (Join-Path $Root 'tools\verify_feature_packages.py') $Output
if ($LASTEXITCODE -ne 0) { throw '功能包校验失败' }

$Digest = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash
$Size = (Get-Item -LiteralPath $Output).Length
Write-Host ''
Write-Host '发布验证通过。'
Write-Host "交付包：$Output"
Write-Host "SHA-256：$Digest"
Write-Host "大小：$Size bytes"
