using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace ImageMagic
{
    internal partial class Studio
    {
        void Photo(Card card, int index)
        {
            var layout = new DockPanel { LastChildFill = true, Background = Brushes.Transparent };
            layout.MouseLeftButtonDown += (s, e) => { if (e.OriginalSource == layout) Pop(); };
            var controls = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            DockPanel.SetDock(controls, Dock.Right); layout.Children.Add(controls);
            var canvas = new Canvas { Background = Brushes.Transparent, ClipToBounds = true };
            layout.Children.Add(canvas);
            var image = new Image { Stretch = Stretch.Fill, Cursor = Cursors.SizeAll }; canvas.Children.Add(image);
            double zoom = 1, dx = 0, dy = 0;
            Point? drag = null;
            Action place = () =>
            {
                var src = image.Source;
                if (src == null || canvas.ActualWidth <= 0 || canvas.ActualHeight <= 0) return;
                double fit = Math.Min(canvas.ActualWidth / src.Width, canvas.ActualHeight / src.Height);
                image.Width = src.Width * fit * zoom; image.Height = src.Height * fit * zoom;
                double xMax = Math.Max(0, (image.Width - canvas.ActualWidth) / 2);
                double yMax = Math.Max(0, (image.Height - canvas.ActualHeight) / 2);
                dx = Math.Max(-xMax, Math.Min(dx, xMax)); dy = Math.Max(-yMax, Math.Min(dy, yMax));
                Canvas.SetLeft(image, (canvas.ActualWidth - image.Width) / 2 + dx);
                Canvas.SetTop(image, (canvas.ActualHeight - image.Height) / 2 + dy);
            };
            Action<double, Point> scale = (factor, p) =>
            {
                double next = Math.Max(0.25, Math.Min(12, zoom * factor));
                double x = p.X - canvas.ActualWidth / 2, y = p.Y - canvas.ActualHeight / 2;
                dx = x - (x - dx) * next / zoom; dy = y - (y - dy) * next / zoom; zoom = next; place();
            };
            Func<Point> center = () => new Point(canvas.ActualWidth / 2, canvas.ActualHeight / 2);
            controls.Children.Add(ButtonFor("+", () => { scale(1.25, center()); return Done(); }));
            controls.Children.Add(ButtonFor("−", () => { scale(0.8, center()); return Done(); }));
            Action<int> show = null;
            var previous = ButtonFor("‹", () => { show(index - 1); return Done(); });
            var nextVersion = ButtonFor("›", () => { show(index + 1); return Done(); });
            if (card.Versions.Length > 1) { controls.Children.Add(previous); controls.Children.Add(nextVersion); }
            controls.Children.Add(ButtonFor("Close", () => { Pop(); return Done(); }));
            show = i =>
            {
                if (i < 0 || i >= card.Versions.Length) return;
                index = i; image.Source = Bitmap(card.Versions[index], 0); zoom = 1; dx = dy = 0; place();
                previous.IsEnabled = index > 0; nextVersion.IsEnabled = index < card.Versions.Length - 1;
            };
            canvas.SizeChanged += (s, e) => place();
            canvas.MouseWheel += (s, e) => { scale(e.Delta > 0 ? 1.25 : 0.8, e.GetPosition(canvas)); e.Handled = true; };
            canvas.MouseLeftButtonDown += (s, e) =>
            {
                if (e.OriginalSource == canvas) { Pop(); return; }
                drag = e.GetPosition(canvas); image.CaptureMouse(); e.Handled = true;
            };
            image.MouseMove += (s, e) =>
            {
                if (!drag.HasValue || !image.IsMouseCaptured) return;
                var p = e.GetPosition(canvas); dx += p.X - drag.Value.X; dy += p.Y - drag.Value.Y; drag = p; place();
            };
            image.MouseLeftButtonUp += (s, e) => { drag = null; image.ReleaseMouseCapture(); };
            show(index); var layer = Push(layout, true);
            layer.PreviewKeyDown += (s, e) =>
            {
                if (e.Key == Key.Left || e.Key == Key.Right) { show(index + (e.Key == Key.Left ? -1 : 1)); e.Handled = true; }
                else if (e.Key == Key.Add || e.Key == Key.OemPlus || e.Key == Key.Subtract || e.Key == Key.OemMinus)
                {
                    scale(e.Key == Key.Add || e.Key == Key.OemPlus ? 1.25 : 0.8, center()); e.Handled = true;
                }
            };
        }
    }
}
