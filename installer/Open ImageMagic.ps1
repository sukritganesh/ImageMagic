param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot 'ComfyUI_windows_portable'
$python = Join-Path $runtime 'python_embeded\python.exe'
$readyFile = Join-Path $PSScriptRoot '.downloads\klein-4b-v1.ready'

# Inno Setup uses the same mutex to keep maintenance out of first-run setup.
$opening = [Threading.Mutex]::new($false, 'Local\ImageMagic.InstalledLauncher')
try {
    if (!(Test-Path -LiteralPath $readyFile) -or !(Test-Path -LiteralPath $python)) {
        Write-Host 'Welcome to ImageMagic'
        Write-Host 'The first launch downloads about 14.5 GB of ComfyUI and Klein 4B files.'
        Write-Host 'Allow 25 GB of free space for setup. Downloads resume if interrupted.'
        Write-Host "Install folder: $PSScriptRoot"
        if ((Read-Host 'Press Enter to download and start, or type C to cancel') -eq 'C') { return }
        while ($true) {
            try {
                & (Join-Path $PSScriptRoot 'setup.ps1')
                [IO.File]::WriteAllText($readyFile, 'Klein 4B setup completed.')
                break
            } catch {
                Write-Host $_.Exception.Message
                if ((Read-Host 'Press Enter to retry, or type C to close and resume later') -eq 'C') { return }
            }
        }
    }

    $options = @()
    if ($NoBrowser) { $options += '--no-browser' }
    & $python -s (Join-Path $PSScriptRoot 'launch_studio.py') @options
    if ($LASTEXITCODE) { throw "ImageMagic could not start. See $PSScriptRoot\studio.log." }
} catch {
    Write-Host $_.Exception.Message
    $null = Read-Host 'Press Enter to close'
    exit 1
} finally {
    $opening.Dispose()
}
