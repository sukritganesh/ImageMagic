# ImageMagic

ImageMagic is a local image generation and editing studio for Windows. Type a prompt to generate a 1024 × 1024 image with FLUX.2 Klein 4B. The three-column gallery keeps the original and its edits together. ComfyUI runs inference on your machine.

The home page lists your sessions. Enter a name and choose **Create session**, or open an existing session to return to its gallery. Use **All sessions** to go back. You can bookmark a session or open several in separate tabs.

Images created before sessions appear together in **Previous images**, including their edits. New sessions keep their images and a small name file in separate folders under the gallery backup directory.

## Install and run

Use Windows 11 x64 with an NVIDIA GPU and a driver compatible with the ComfyUI NVIDIA portable build. The studio has been tested on an RTX 4090 Laptop GPU with 16 GB of VRAM and 64 GB of system RAM. Setup uses Windows PowerShell, `curl.exe`, and `tar.exe`. The portable build includes Python.

From PowerShell in a writable folder:

```powershell
git clone https://github.com/sukritganesh/ImageMagic.git
cd ImageMagic
.\setup.ps1
& '.\Start ImageMagic.cmd'
```

The default setup downloads about 14.5 GB, including the archive, encoder, decoder, and fast FP8 checkpoint. Allow additional disk space for the extracted runtime and your gallery. Setup verifies SHA-256 checksums and reuses existing files. Run `.\setup.ps1 -AllModels` to add Compact and Base (about 6.6 GB more). If PowerShell blocks the downloaded setup script, review it and use `Unblock-File .\setup.ps1` where your execution policy permits local scripts.

Double-click **Start ImageMagic.cmd** to start or reopen this installation. The launcher uses port 8188 by default, then tries 8189, 8190, and so on if needed. If this installation is already running, the launcher reopens its current port even if a lower port has since become available. It opens the selected URL in your browser and writes startup diagnostics to `studio.log`.

## Use the gallery

- Choose a model and enter a prompt. FP8 is the four-step default. Compact uses a smaller checkpoint and encodes text on the CPU. Base uses 50 steps.
- Click a picture to expand it. Scroll or use **+ / −** to zoom, drag to pan, and use **← / →** to compare versions. Escape or a click outside the picture returns you to the previous view.
- Click the caption to read the full prompt or edit the selected version. Describe the change and choose **Generate edit**. The selected image serves as a visual reference. The new version appears on the same card.
- Back up `ComfyUI_windows_portable/ComfyUI/output/ImageMagic/` to keep your gallery. The PNG metadata stores prompts, timing, and version relationships. Preserve the filenames and metadata when moving images.

## Project layout

Edit the studio backend and browser UI in [custom_nodes/imagemagic_studio](custom_nodes/imagemagic_studio/). The launcher copies these files into the portable installation when starting the server. Restart the local ComfyUI process after changing the source. For contributor conventions, see [CONTRIBUTING.md](CONTRIBUTING.md).

Setup downloads third-party software and model weights directly from their publishers. Their respective licenses apply. [ComfyUI release](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.46.0) · [FLUX.2 Klein 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) · [ComfyUI encoder and VAE](https://huggingface.co/Comfy-Org/Flux-2-Klein-4B)
