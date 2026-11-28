using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

[assembly: AssemblyTitle("ImageMagic")]
[assembly: AssemblyProduct("ImageMagic")]
[assembly: AssemblyVersion("1.1.0.0")]

namespace ImageMagic
{
    static class App
    {
        internal static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
        static readonly string Portable = Path.Combine(Root, "ComfyUI_windows_portable");
        static readonly string Python = Path.Combine(Portable, @"python_embeded\python.exe");

        [STAThread]
        static void Main()
        {
            string key;
            using (var hash = SHA256.Create())
                key = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(Root.ToUpperInvariant())));
            bool first;
            using (var activate = new EventWaitHandle(false, EventResetMode.AutoReset,
                       @"Local\ImageMagic.Activate." + key, out first))
            {
                if (!first) { activate.Set(); return; }
                using (var maintenance = File.Exists(Path.Combine(Root, "WINDOWS-SETUP.md"))
                    ? new Mutex(false, @"Local\ImageMagic.InstalledLauncher") : null)
                {
                    var app = new Application();
                    var window = new Studio();
                    var registration = ThreadPool.RegisterWaitForSingleObject(activate, (s, t) =>
                        window.Dispatcher.BeginInvoke(new Action(window.BringForward)), null, -1, false);
                    try { app.Run(window); }
                    finally { registration.Unregister(null); }
                }
            }
        }

        internal static bool NeedsSetup()
        {
            string models = Path.Combine(Portable, @"ComfyUI\models");
            return !File.Exists(Python) || !File.Exists(Path.Combine(models, @"text_encoders\qwen_3_4b.safetensors"))
                || !File.Exists(Path.Combine(models, @"vae\flux2-vae.safetensors"))
                || !File.Exists(Path.Combine(models, @"diffusion_models\flux-2-klein-4b-fp8.safetensors"));
        }

        internal static Task Install()
        {
            return Task.Run(() =>
            {
                var info = new ProcessStartInfo("powershell.exe",
                    "-NoProfile -ExecutionPolicy RemoteSigned -File \"" + Path.Combine(Root, "setup.ps1") + "\"");
                info.WorkingDirectory = Root;
                using (var process = Process.Start(info))
                {
                    process.WaitForExit();
                    if (process.ExitCode != 0) throw new IOException("Setup stopped. Choose Download and start again to resume.");
                }
            });
        }

        internal static async Task<int> StartServer()
        {
            var info = new ProcessStartInfo(Python, "-s \"" + Path.Combine(Root, "launch_studio.py") + "\" --server-only");
            info.WorkingDirectory = Root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardOutput = info.RedirectStandardError = true;
            using (var process = Process.Start(info))
            {
                var output = process.StandardOutput.ReadToEndAsync();
                var error = process.StandardError.ReadToEndAsync();
                await Task.WhenAll(output, error);
                process.WaitForExit();
                int port;
                if (process.ExitCode != 0 || !int.TryParse(output.Result.Trim().Split('\n').Last(), out port)
                    || port < 1 || port > 65535)
                    throw new IOException(string.IsNullOrWhiteSpace(error.Result)
                        ? "Could not start the inference service. See studio.log in the install folder." : error.Result.Trim());
                return port;
            }
        }
    }
}
