using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace ImageMagic
{
    internal class Session
    {
        public string id { get; set; }
        public string name { get; set; }
        public string folder { get; set; }
        public bool available { get; set; }
    }
    internal class Picture
    {
        public string file { get; set; }
        public string original { get; set; }
        public string prompt { get; set; }
        public string model { get; set; }
        public string edit_model_label { get; set; }
        public double submitted { get; set; }
        public double seconds { get; set; }
        public string Root { get { return original ?? file; } }
    }
    internal class Snapshot
    {
        public string destination { get; set; }
        public string revision { get; set; }
        public string folder { get; set; }
        public int images { get; set; }
        public int trashed { get; set; }
        public int count { get; set; }
        public string prompt_id { get; set; }
    }
    internal class History
    {
        public JobStatus status { get; set; }
    }
    internal class JobStatus
    {
        public string status_str { get; set; }
        public object[][] messages { get; set; }
    }
    internal class Service : IDisposable
    {
        readonly HttpClient client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false });
        readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        internal Service(int port)
        {
            client.BaseAddress = new Uri("http://127.0.0.1:" + port);
            client.DefaultRequestHeaders.Add("Origin", client.BaseAddress.GetLeftPart(UriPartial.Authority));
            client.Timeout = TimeSpan.FromMinutes(10);
        }
        internal async Task<T> Request<T>(string path, object data = null)
        {
            using (var req = new HttpRequestMessage(data == null ? HttpMethod.Get : HttpMethod.Post, path))
            {
                if (data != null) req.Content = new StringContent(json.Serialize(data), Encoding.UTF8, "application/json");
                using (var reply = await client.SendAsync(req))
                {
                    string content = await reply.Content.ReadAsStringAsync();
                    if (!reply.IsSuccessStatusCode) throw new IOException(content.Length == 0 ? reply.ReasonPhrase : content);
                    return json.Deserialize<T>(content);
                }
            }
        }
        public void Dispose() { client.Dispose(); }
    }
}
