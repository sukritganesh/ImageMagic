using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;

namespace ImageMagic
{
    internal partial class Studio : Window
    {
        static Brush Paint(string hex)
        {
            var b = (SolidColorBrush)new BrushConverter().ConvertFromString(hex); b.Freeze(); return b;
        }
        static readonly Brush Ink = Paint("#161914"), Paper = Paint("#F4F2E9"), Dim = Paint("#AEB3A6"),
            Panel = Paint("#252922"), Edge = Paint("#454A3F"), Lime = Paint("#D4FC76");
        readonly Grid root = new Grid();
        readonly DockPanel page = new DockPanel();
        readonly ContentControl content = new ContentControl();
        readonly TextBlock status = Label("", 14, Dim);
        readonly Stack<UIElement> focusStack = new Stack<UIElement>();
        readonly DispatcherTimer timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        readonly Dictionary<string, string> jobs = new Dictionary<string, string>();
        Service api;
        Session session;
        bool fullscreen, refreshing, installing;
        WindowState previousState, lastVisibleState = WindowState.Normal;
        Button fullButton;
        long navigation;

        public Studio()
        {
            Title = "ImageMagic"; Width = 1120; Height = 820; MinWidth = 660; MinHeight = 480;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            Background = Ink; Foreground = Paper; FontFamily = new FontFamily("Segoe UI"); FontSize = 15;
            Content = root; root.Children.Add(page);
            var head = new DockPanel { Margin = new Thickness(32, 16, 32, 10) };
            var mark = new Image { Width = 26, Height = 26, Margin = new Thickness(0, 0, 10, 0) };
            using (var icon = System.Drawing.Icon.ExtractAssociatedIcon(System.Reflection.Assembly.GetExecutingAssembly().Location))
            {
                if (icon != null)
                {
                    var bitmap = System.Windows.Interop.Imaging.CreateBitmapSourceFromHIcon(icon.Handle, Int32Rect.Empty,
                        System.Windows.Media.Imaging.BitmapSizeOptions.FromEmptyOptions());
                    bitmap.Freeze(); Icon = bitmap; mark.Source = bitmap;
                }
            }
            fullButton = ButtonFor("Full screen", () => { ToggleFull(); return Done(); });
            fullButton.ToolTip = "Toggle full screen (F11)";
            DockPanel.SetDock(fullButton, Dock.Right); head.Children.Add(fullButton);
            head.Children.Add(mark); head.Children.Add(Label("ImageMagic", 19));
            DockPanel.SetDock(head, Dock.Top); page.Children.Add(head);
            status.Margin = new Thickness(36, 4, 32, 12); DockPanel.SetDock(status, Dock.Bottom); page.Children.Add(status);
            content.Margin = new Thickness(32, 4, 32, 10); page.Children.Add(content);
            Loaded += async (s, e) => await Safe(Start);
            Closing += (s, e) =>
            {
                if (installing) { e.Cancel = true; status.Text = "Finish or close the setup download window first."; }
            };
            Closed += (s, e) => { timer.Stop(); if (api != null) api.Dispose(); };
            timer.Tick += async (s, e) => await Refresh();
            StateChanged += (s, e) => { if (WindowState != WindowState.Minimized) lastVisibleState = WindowState; };
            PreviewKeyDown += (s, e) =>
            {
                if (e.Key == Key.F11) { ToggleFull(); e.Handled = true; }
                else if (e.Key == Key.Escape && root.Children.Count > 1) { Pop(); e.Handled = true; }
                else if (e.Key == Key.Escape && fullscreen) { ToggleFull(); e.Handled = true; }
            };
        }

        internal void BringForward()
        {
            if (WindowState == WindowState.Minimized) WindowState = lastVisibleState;
            Activate(); Topmost = true; Topmost = false; Focus();
        }
        void ToggleFull()
        {
            if (!fullscreen)
            {
                previousState = WindowState;
                WindowState = WindowState.Normal; WindowStyle = WindowStyle.None;
                ResizeMode = ResizeMode.NoResize; WindowState = WindowState.Maximized;
            }
            else
            {
                WindowState = WindowState.Normal; ResizeMode = ResizeMode.CanResize;
                WindowStyle = WindowStyle.SingleBorderWindow; WindowState = previousState;
            }
            fullscreen = !fullscreen; fullButton.Content = fullscreen ? "Exit full screen" : "Full screen";
        }
        static Task Done() { return Task.FromResult(true); }
        async Task Safe(Func<Task> task)
        {
            try { await task(); }
            catch (Exception ex) { if (IsVisible) Notice(ex.Message); }
        }
        static TextBlock Label(string text, double size = 15, Brush color = null)
        {
            return new TextBlock
            {
                Text = text,
                Foreground = color ?? Paper,
                FontSize = size,
                TextWrapping = TextWrapping.Wrap,
                VerticalAlignment = VerticalAlignment.Center
            };
        }
        static StackPanel Row() { return new StackPanel { Orientation = Orientation.Horizontal }; }
        static Border Box(UIElement child, double pad = 18)
        {
            return new Border
            {
                Child = child,
                Padding = new Thickness(pad),
                Background = Panel,
                BorderBrush = Edge,
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(10),
                Margin = new Thickness(0, 4, 8, 6)
            };
        }
        Button ButtonFor(string title, Func<Task> action, bool accent = false)
        {
            var b = new Button
            {
                Content = title,
                Padding = new Thickness(13, 7, 13, 7),
                Margin = new Thickness(0, 3, 6, 3),
                Background = accent ? Lime : Panel,
                Foreground = accent ? Ink : Paper,
                BorderBrush = Edge,
                Cursor = Cursors.Hand,
                MinHeight = 32,
                VerticalContentAlignment = VerticalAlignment.Center
            };
            // Keep text readable in native pointer, focus and disabled states.
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Control.BackgroundProperty));
            border.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(Control.BorderBrushProperty));
            border.SetValue(Border.BorderThicknessProperty, new Thickness(1));
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(6));
            border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(Control.PaddingProperty));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
            presenter.SetValue(FrameworkElement.HorizontalAlignmentProperty, new TemplateBindingExtension(Control.HorizontalContentAlignmentProperty));
            presenter.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            border.AppendChild(presenter);
            var template = new ControlTemplate(typeof(Button)) { VisualTree = border };
            foreach (var prop in new[] { UIElement.IsMouseOverProperty, UIElement.IsKeyboardFocusedProperty })
            {
                var hover = new Trigger { Property = prop, Value = true };
                hover.Setters.Add(new Setter(Control.BorderBrushProperty, Lime)); template.Triggers.Add(hover);
            }
            var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.55)); template.Triggers.Add(disabled);
            b.Template = template;
            bool executing = false;
            b.Click += async (s, e) =>
            {
                if (executing) return;
                executing = true;
                try { await Safe(action); } finally { executing = false; }
            };
            return b;
        }
        static TextBox Input(string name, bool multiline, int limit)
        {
            var input = new TextBox
            {
                Background = Ink,
                Foreground = Paper,
                CaretBrush = Lime,
                BorderBrush = Edge,
                Padding = new Thickness(10),
                MaxLength = limit,
                AcceptsReturn = multiline,
                TextWrapping = TextWrapping.Wrap,
                MinHeight = multiline ? 80 : 36,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Margin = new Thickness(0, 6, 0, 6)
            };
            AutomationProperties.SetName(input, name); return input;
        }
        void Heading(StackPanel stack, string title)
        {
            var h = Label(title, 37); h.FontWeight = FontWeights.SemiBold;
            h.Margin = new Thickness(0, 8, 0, 12); stack.Children.Add(h);
        }
        static ScrollViewer Scroll(UIElement child)
        {
            return new ScrollViewer
            {
                Content = child,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
            };
        }
        Border Push(FrameworkElement body, bool photo = false)
        {
            focusStack.Push(Keyboard.FocusedElement as UIElement);
            root.Children[root.Children.Count - 1].IsEnabled = false;
            var shade = new Border
            {
                Background = photo ? Ink : Paint("#D010120F"),
                Padding = new Thickness(photo ? 10 : 24),
                Child = body,
                Focusable = true
            };
            KeyboardNavigation.SetTabNavigation(shade, KeyboardNavigationMode.Cycle);
            shade.MouseLeftButtonDown += (s, e) => { if (e.OriginalSource == shade) { Pop(); e.Handled = true; } };
            root.Children.Add(shade); shade.Focus(); return shade;
        }
        void Pop()
        {
            if (root.Children.Count < 2) return;
            if (root.Children[root.Children.Count - 1] == detailsLayer) { detailsLayer = null; updateDetails = null; }
            root.Children.RemoveAt(root.Children.Count - 1); root.Children[root.Children.Count - 1].IsEnabled = true;
            var focus = focusStack.Pop(); if (focus != null && focus.IsVisible) focus.Focus();
        }
        void Dialog(StackPanel stack)
        {
            var box = Box(Scroll(stack), 22); box.MaxWidth = 760;
            box.HorizontalAlignment = HorizontalAlignment.Center; box.VerticalAlignment = VerticalAlignment.Center;
            Push(box);
        }
        void Notice(string message)
        {
            var stack = new StackPanel(); stack.Children.Add(Label(message));
            stack.Children.Add(ButtonFor("Close", () => { Pop(); return Done(); })); Dialog(stack);
        }
        void Confirm(string title, string message, string verb, Func<Task> yes)
        {
            var stack = new StackPanel(); Heading(stack, title); stack.Children.Add(Label(message));
            var row = Row(); row.Children.Add(ButtonFor("Cancel", () => { Pop(); return Done(); }));
            row.Children.Add(ButtonFor(verb, async () => { Pop(); await yes(); }, true)); stack.Children.Add(row);
            Dialog(stack);
        }
        async Task Start()
        {
            if (App.NeedsSetup())
            {
                var stack = new StackPanel(); Heading(stack, "Set up ImageMagic");
                stack.Children.Add(Label("Download the local inference engine and Klein 4B. The first download is about 14.5 GB. Allow 25 GB on the installation drive."));
                stack.Children.Add(Label(App.Root, 14, Dim));
                stack.Children.Add(ButtonFor("Download and start", async () =>
                {
                    installing = true; status.Text = "Setup is running in the download window.";
                    try { await App.Install(); } finally { installing = false; }
                    await Start();
                }, true));
                content.Content = stack; return;
            }
            status.Text = "Starting the local inference service…";
            var wait = new StackPanel(); Heading(wait, "Opening your studio"); content.Content = wait;
            try { api = new Service(await App.StartServer()); await Home(); timer.Start(); }
            catch { wait.Children.Add(ButtonFor("Retry", Start)); throw; }
        }
        async Task Home()
        {
            long turn = ++navigation; var sessions = await api.Request<Session[]>("/studio/api/sessions");
            if (turn != navigation) return;
            session = null; status.Text = ""; Title = "ImageMagic";
            var stack = new StackPanel(); Heading(stack, "Sessions");
            var form = new StackPanel(); form.Children.Add(Label("New session name"));
            var name = Input("New session name", false, 80); form.Children.Add(name);
            var location = Label("Default gallery folder", 14, Dim); string destination = null;
            var actions = Row();
            var create = ButtonFor("Create session", async () =>
            {
                var created = await api.Request<Session>("/studio/api/sessions", new { name = name.Text.Trim(), destination });
                await Open(created);
            }, true);
            actions.Children.Add(create);
            actions.Children.Add(ButtonFor("Choose folder…", async () =>
            {
                if (string.IsNullOrWhiteSpace(name.Text)) { name.Focus(); status.Text = "Enter a session name first."; return; }
                var result = await api.Request<Snapshot>("/studio/api/choose-folder", new { name = name.Text.Trim() });
                if (result.destination != null) { destination = result.destination; location.Text = destination; }
            }));
            actions.Children.Add(ButtonFor("Use default", () => { destination = null; location.Text = "Default gallery folder"; return Done(); }));
            name.KeyDown += (s, e) => { if (e.Key == Key.Enter && create.IsEnabled) create.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); };
            form.Children.Add(actions); form.Children.Add(location); stack.Children.Add(Box(form));
            foreach (var item in sessions)
            {
                var line = new DockPanel();
                if (item.available)
                {
                    var del = ButtonFor("Delete", async () =>
                    {
                        string url = "/studio/api/sessions/" + item.id;
                        var info = await api.Request<Snapshot>(url + "/deletion");
                        Confirm("Delete “" + item.name + "”?",
                            info.images + " saved images and " + info.trashed + " in trash will be permanently deleted.\n" + info.folder,
                            "Delete permanently", async () => { await api.Request<object>(url + "/delete", new { info.revision }); await Home(); });
                    });
                    DockPanel.SetDock(del, Dock.Right); line.Children.Add(del);
                    var open = ButtonFor(item.name, () => Open(item)); open.HorizontalContentAlignment = HorizontalAlignment.Left;
                    line.Children.Add(open);
                }
                else line.Children.Add(Label(item.name + "  ·  Folder unavailable\n" + item.folder, 15, Dim));
                stack.Children.Add(line);
            }
            if (sessions.Length == 0) stack.Children.Add(Label("No sessions yet.", 15, Dim));
            content.Content = Scroll(stack);
        }
    }
}
