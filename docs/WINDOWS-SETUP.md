# Install ImageMagic on Windows

## Before you start

Use Windows 11 x64 and an NVIDIA GPU with a compatible driver. The tested configuration is an RTX 4090 Laptop GPU with 16 GB VRAM and 64 GB system RAM. Allow **25 GB of free space** on the installation drive for the default setup, plus space for your images.

You need internet for the first download. The installer includes the studio and its launcher. First launch downloads about **14.5 GB** of ComfyUI, its portable Python runtime, and the default FLUX.2 Klein 4B FP8 model files. Image generation and editing run locally. The default setup requires no Hugging Face account, Git installation, or separate Python installation.

## Install and make your first image

1. Download **ImageMagic-Setup-1.0.0.exe** from the ImageMagic GitHub release assets. The release also includes **SHA256SUMS.txt**. This build is unsigned. To check your download, run `Get-FileHash .\ImageMagic-Setup-1.0.0.exe -Algorithm SHA256` in PowerShell from your downloads folder and compare it with the published checksum. Windows may show an unknown-publisher warning.
2. Double-click the installer. Keep the default folder, `%LOCALAPPDATA%\Programs\ImageMagic`, or choose a separate writable folder with sufficient space. Setup installs for your Windows account. If you already run the source edition, give the installed edition its own folder.
3. Select **Open ImageMagic** on the last screen or open **ImageMagic** from Start. In the first-launch window, press **Enter** to download and start. Keep the window open while it downloads, checks the files, and extracts ComfyUI. If a transfer stops, press **Enter** to retry, or type **C** and open ImageMagic again later to resume.
4. When your browser opens, name a session and choose **Create session**. Leave **Klein 4B · FP8** selected, type a prompt, and choose **Generate**. The first image takes longer while the model loads. Click its caption to edit it.
5. Next time, open **ImageMagic** from Start to reopen this installation. It normally uses port 8188. If another studio or app is using that port, the launcher opens the next available one. Use the URL it opens.

## Optional models

For Compact and Base, open PowerShell in the install folder and run `.\setup.ps1 -AllModels` (about 6.6 GB extra). For **Klein 9B FP8**, first request access with your own Hugging Face account under the [publisher's non-commercial license](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-fp8). Run `.\setup.ps1 -Klein9B` in the same folder (about 18.1 GB extra). It uses your local Hugging Face login or prompts for a read token. Refresh the studio after setup. The [model instructions](https://github.com/sukritganesh/ImageMagic#add-klein-9b-fp8) include the manual-download option.

## Reinstall, uninstall, and recover

- To update or repair the studio files, run the installer again and choose the same folder. Let any queued images finish first. Setup stops the idle server for that installation. Open ImageMagic from Start again after setup.
- For a missing model or a checksum error, run `.\setup.ps1` in the install folder. Follow the error for the specific file, then retry. Startup diagnostics are in `studio.log` in that folder.
- To back up sessions, stop the studio and copy `ComfyUI_windows_portable\ComfyUI\output\ImageMagic\` from the install folder, including the SQLite catalog if present. If your version supports custom save locations, also copy each custom session folder in full and restore it to the same path. Preserve the filenames and folder structure.
- To uninstall, use **Settings → Apps → Installed apps → ImageMagic → Uninstall**. The uninstaller removes the studio launcher and shortcut. It keeps the downloaded runtime, models, cache, and gallery for a reinstall. To reclaim all that space, back up your gallery first, then remove the remaining dedicated install folder yourself.
