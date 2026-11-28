$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$output = Join-Path $root 'ImageMagic.exe'
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$icon = Join-Path $root 'installer\ImageMagic.ico'
$source = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs')
$inputs = @($source) + @(Get-Item -LiteralPath $icon, $PSCommandPath)
if ((Test-Path -LiteralPath $output) -and
    !($inputs | Where-Object LastWriteTimeUtc -gt (Get-Item -LiteralPath $output).LastWriteTimeUtc)) { return }
$references = @('System.Net.Http', 'System.Web.Extensions', 'System.Windows.Forms', 'System.Drawing', 'System.Xaml') |
    ForEach-Object { "/reference:$framework\$_.dll" }
$references += @('PresentationCore', 'PresentationFramework', 'WindowsBase') |
    ForEach-Object { "/reference:$framework\WPF\$_.dll" }
$work = Join-Path $root ("dist\desktop-" + [Guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $work -Force
$temp = Join-Path $work 'ImageMagic.exe'
try {
    & "$framework\csc.exe" /nologo /target:winexe /platform:x64 /optimize+ /utf8output /codepage:65001 "/win32icon:$icon" "/out:$temp" @references $source.FullName
    if ($LASTEXITCODE) { throw 'Could not compile the ImageMagic desktop application.' }
    try {
        if (Test-Path -LiteralPath $output) { [IO.File]::Replace($temp, $output, (Join-Path $work 'previous.exe')) }
        else { [IO.File]::Move($temp, $output) }
    } catch {
        if (!(Test-Path -LiteralPath $output) -or
            ($inputs | Where-Object LastWriteTimeUtc -gt (Get-Item -LiteralPath $output).LastWriteTimeUtc)) {
            throw 'Close the running source copy of ImageMagic and try the build again.'
        }
    }
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp }
    $previous = Join-Path $work 'previous.exe'
    if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous }
    [IO.Directory]::Delete($work)
}
