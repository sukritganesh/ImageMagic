using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace ImageMagic
{
    internal partial class Studio
    {
        sealed class Card
        {
            internal Picture[] Versions;
            internal int Index;
            internal Picture Selected { get { return Versions[Index]; } }
        }
        readonly Dictionary<string, Card> cards = new Dictionary<string, Card>();
        readonly HashSet<string> missing = new HashSet<string>();
        UniformGrid tiles;
        TextBlock count;
        string signature;
        Func<Task> updateDetails;
        Border detailsLayer;

        async Task Open(Session item)
        {
            long turn = ++navigation;
            var models = await api.Request<Dictionary<string, string>>("/studio/api/models");
            if (turn != navigation) return;
            session = item; Title = item.name + " · ImageMagic"; cards.Clear(); signature = null;
            var layout = new DockPanel(); var top = new StackPanel();
            var back = ButtonFor("‹  All sessions", Home); back.HorizontalAlignment = HorizontalAlignment.Left;
            top.Children.Add(back); Heading(top, item.name);
            var form = new StackPanel();
            var prompt = Input("Image prompt", true, 8000); prompt.MaxHeight = 165;
            form.Children.Add(Label("Prompt")); form.Children.Add(prompt);
            var controls = Row();
            var model = new ComboBox
            {
                ItemsSource = models,
                DisplayMemberPath = "Value",
                SelectedValuePath = "Key",
                MinWidth = 158,
                Margin = new Thickness(0, 4, 12, 4),
                VerticalContentAlignment = VerticalAlignment.Center
            };
            AutomationProperties.SetName(model, "Generation model");
            if (models.ContainsKey("fp8")) model.SelectedValue = "fp8"; else model.SelectedIndex = 0;
            controls.Children.Add(model);
            var generate = ButtonFor("Generate", async () =>
            {
                if (string.IsNullOrWhiteSpace(prompt.Text)) { prompt.Focus(); return; }
                await Submit("/studio/api/generate", new { session = item.id, prompt = prompt.Text, model = model.SelectedValue }, item);
                prompt.SelectAll();
            }, true);
            generate.IsEnabled = models.Count > 0; controls.Children.Add(generate); form.Children.Add(controls);
            prompt.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter && Keyboard.Modifiers == ModifierKeys.Control && generate.IsEnabled)
                {
                    e.Handled = true; generate.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                }
            };
            top.Children.Add(Box(form));
            var line = new DockPanel(); var trash = ButtonFor("Empty trash", async () =>
            {
                var info = await api.Request<Snapshot>("/studio/api/trash?session=" + item.id);
                if (info.count == 0) { status.Text = "This session’s trash is empty."; return; }
                Confirm("Empty this session’s trash?", info.count + " images will be permanently deleted.", "Delete permanently",
                    async () =>
                    {
                        await api.Request<object>("/studio/api/trash/empty", new { session = item.id, info.revision });
                        status.Text = "Trash emptied.";
                    });
            });
            DockPanel.SetDock(trash, Dock.Right); line.Children.Add(trash); count = Label("Your images", 22);
            line.Children.Add(count); top.Children.Add(line); DockPanel.SetDock(top, Dock.Top); layout.Children.Add(top);
            tiles = new UniformGrid { Columns = 3, VerticalAlignment = VerticalAlignment.Top }; layout.Children.Add(Scroll(tiles));
            status.Text = models.Count == 0 ? "Install a model to generate images." : "";
            content.Content = layout; await Gallery(item); prompt.Focus();
        }

        async Task Submit(string url, object data, Session item)
        {
            var result = await api.Request<Snapshot>(url, data); jobs[result.prompt_id] = item.id;
            status.Text = "Image queued…";
        }
        async Task Refresh()
        {
            if (refreshing || api == null || !IsVisible) return;
            refreshing = true;
            try
            {
                foreach (string id in jobs.Keys.ToArray())
                {
                    var history = await api.Request<Dictionary<string, History>>("/history/" + id);
                    History entry; string message;
                    if (history.TryGetValue(id, out entry))
                    {
                        message = entry.status.status_str == "success" ? "Image saved." : "Generation interrupted.";
                        foreach (var ev in entry.status.messages ?? new object[0][])
                        {
                            if (ev.Length < 2 || (string)ev[0] != "execution_error") continue;
                            var data = ev[1] as Dictionary<string, object>;
                            if (data != null && data.ContainsKey("exception_message")) message = "Generation failed. " + data["exception_message"];
                        }
                    }
                    else
                    {
                        var queue = await api.Request<Dictionary<string, object[][]>>("/queue");
                        if (queue.Values.SelectMany(q => q).Any(j => j.Length > 1 && Equals(j[1], id))) { missing.Remove(id); continue; }
                        if (missing.Add(id)) continue;
                        message = "Queue cleared.";
                    }
                    if (session != null && session.id == jobs[id]) status.Text = message;
                    jobs.Remove(id); missing.Remove(id);
                }
                if (session != null)
                {
                    if (jobs.Values.Contains(session.id)) status.Text = "Generating…";
                    await Gallery(session);
                }
            }
            catch (Exception ex) { if (IsVisible) status.Text = ex.Message; }
            finally { refreshing = false; }
        }
        async Task Gallery(Session current)
        {
            long request = ++galleryRequest;
            var items = await api.Request<Picture[]>("/studio/api/gallery?session=" + current.id);
            if (current != session || request != galleryRequest) return;
            string next = string.Join(",", items.Select(i => i.file));
            if (next == signature) return;
            signature = next; var keys = new HashSet<string>(); tiles.Children.Clear();
            foreach (var group in items.GroupBy(i => i.Root))
            {
                keys.Add(group.Key); Card card;
                var versions = group.OrderBy(i => i.submitted).ToArray();
                int index = -1;
                if (cards.TryGetValue(group.Key, out card))
                {
                    if (card.Versions.Last().file == versions.Last().file)
                        index = Array.FindIndex(versions, v => v.file == card.Selected.file);
                }
                else cards[group.Key] = card = new Card();
                card.Versions = versions; card.Index = index < 0 ? versions.Length - 1 : index;
                tiles.Children.Add(MakeCard(card));
            }
            foreach (string old in cards.Keys.Where(k => !keys.Contains(k)).ToArray()) cards.Remove(old);
            count.Text = keys.Count == 0 ? "No images yet" : "Your images  ·  " + keys.Count;
            if (detailsLayer != null && root.Children[root.Children.Count - 1] == detailsLayer && updateDetails != null)
                await updateDetails();
        }
        long galleryRequest;
        BitmapImage Bitmap(Picture item, int pixels)
        {
            var bitmap = new BitmapImage();
            if (Path.GetFileName(item.file) != item.file) throw new IOException("Unexpected image filename.");
            using (var stream = new FileStream(Path.Combine(session.folder, item.file), FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                bitmap.BeginInit(); bitmap.CacheOption = BitmapCacheOption.OnLoad;
                if (pixels > 0) bitmap.DecodePixelWidth = pixels;
                bitmap.StreamSource = stream; bitmap.EndInit(); bitmap.Freeze();
            }
            return bitmap;
        }
        Button Thumbnail(Picture item, double height, Func<Task> open)
        {
            var b = ButtonFor("", open); b.Padding = new Thickness(0); b.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            AutomationProperties.SetName(b, "Expand image: " + item.prompt);
            try { b.Content = new Image { Source = Bitmap(item, 480), Height = height, Stretch = Stretch.Uniform, SnapsToDevicePixels = true }; }
            catch (IOException) { b.Content = "Image unavailable"; }
            return b;
        }
        StackPanel Pager(Card card, Action changed)
        {
            var row = Row();
            var prev = ButtonFor("‹", () => { card.Index--; changed(); return Done(); });
            var next = ButtonFor("›", () => { card.Index++; changed(); return Done(); });
            AutomationProperties.SetName(prev, "Previous version"); AutomationProperties.SetName(next, "Next version");
            prev.IsEnabled = card.Index > 0; next.IsEnabled = card.Index < card.Versions.Length - 1;
            row.Children.Add(prev); row.Children.Add(Label(" " + (card.Index + 1) + " / " + card.Versions.Length + " ", 14, Dim));
            row.Children.Add(next); return row;
        }
        void RepaintCards()
        {
            var groups = tiles.Children.Cast<FrameworkElement>().Select(x => (Card)x.Tag).ToArray();
            tiles.Children.Clear(); foreach (var g in groups) tiles.Children.Add(MakeCard(g));
        }
        Border MakeCard(Card card)
        {
            var stack = new StackPanel(); var item = card.Selected;
            stack.Children.Add(Thumbnail(item, 180, () => { Photo(card, card.Index); return Done(); }));
            if (card.Versions.Length > 1) stack.Children.Add(Pager(card, RepaintCards));
            var caption = new StackPanel(); var text = Label(item.prompt);
            text.LineStackingStrategy = LineStackingStrategy.BlockLineHeight; text.LineHeight = 20;
            text.MaxHeight = 120; text.TextTrimming = TextTrimming.CharacterEllipsis; caption.Children.Add(text);
            caption.Children.Add(Label(item.model + "  ·  " + item.seconds.ToString("0.0") + " s", 13, Dim));
            var details = ButtonFor("", () => { Details(card); return Done(); }); details.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            details.Content = caption; AutomationProperties.SetName(details, "Image details: " + item.prompt); stack.Children.Add(details);
            var box = Box(stack, 8); box.Tag = card; return box;
        }
        void Details(Card card)
        {
            var body = new StackPanel(); var scroll = Box(Scroll(body), 18);
            scroll.MaxWidth = 850; scroll.HorizontalAlignment = HorizontalAlignment.Center; scroll.VerticalAlignment = VerticalAlignment.Center;
            var layer = Push(scroll); detailsLayer = layer;
            var edit = Input("Edit instruction", true, 8000); edit.MaxHeight = 100;
            bool compare = true;
            Action render = null;
            render = () =>
            {
                if (!cards.ContainsKey(card.Selected.Root)) { Pop(); return; }
                body.Children.Clear(); var item = card.Selected;
                var original = card.Versions.FirstOrDefault(v => v.file == item.Root && v.file != item.file);
                var images = new UniformGrid { Rows = 1 };
                if (compare && original != null)
                {
                    var left = new StackPanel(); left.Children.Add(Label("Original · " + original.model, 14, Dim));
                    left.Children.Add(Thumbnail(original, 195, () => { Photo(card, Array.IndexOf(card.Versions, original)); return Done(); })); images.Children.Add(left);
                }
                var right = new StackPanel(); right.Children.Add(Label("Version " + (card.Index + 1) + " · " + item.model, 14, Dim));
                right.Children.Add(Thumbnail(item, 195, () => { Photo(card, card.Index); return Done(); })); images.Children.Add(right); body.Children.Add(images);
                if (card.Versions.Length > 1) body.Children.Add(Pager(card, () => { RepaintCards(); render(); }));
                if (original != null) body.Children.Add(ButtonFor(compare ? "View edit only" : "Compare with original", () => { compare = !compare; render(); return Done(); }));
                body.Children.Add(Label(item.prompt)); body.Children.Add(Label("Edit instruction", 16, Dim)); body.Children.Add(edit);
                var cmd = new WrapPanel();
                cmd.Children.Add(ButtonFor(item.edit_model_label == null ? "Generate edit" : "Edit with " + item.edit_model_label, async () =>
                {
                    if (string.IsNullOrWhiteSpace(edit.Text)) { edit.Focus(); return; }
                    await Submit("/studio/api/edit", new { session = session.id, source = item.file, prompt = edit.Text }, session);
                    edit.Clear(); compare = true; Pop();
                }, true));
                cmd.Children.Add(ButtonFor(card.Versions.Length == 1 ? "Delete image" : "Delete this version", () => { ReviewDelete(card, false); return Done(); }));
                if (card.Versions.Length > 1) cmd.Children.Add(ButtonFor("Delete entire card", () => { ReviewDelete(card, true); return Done(); }));
                cmd.Children.Add(ButtonFor("Close", () => { Pop(); return Done(); })); body.Children.Add(cmd);
            };
            updateDetails = () => { render(); return Done(); }; render();
        }
        void ReviewDelete(Card card, bool all)
        {
            string[] files = card.Versions.Select(v => v.file).ToArray();
            var item = card.Selected; var current = session;
            Confirm(all ? "Delete entire card?" : "Delete this image?", all ? files.Length + " versions will move to this session’s trash." :
                "This version will move to the session’s trash. Other versions stay in the gallery.", "Move to trash", async () =>
                {
                    await api.Request<object>("/studio/api/delete", new { session = current.id, scope = all ? "card" : "version", file = item.file, versions = files });
                    Pop(); await Gallery(current); status.Text = "Moved to trash.";
                });
        }
    }
}
