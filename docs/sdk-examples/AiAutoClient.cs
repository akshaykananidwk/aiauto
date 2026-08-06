// AIAuto API client — C# example (.NET 8, System.Net.Http + System.Text.Json)
using System.Net.Http.Json;

var http = new HttpClient { BaseAddress = new Uri("https://your-server/api/public/v1/") };
http.DefaultRequestHeaders.Add("X-API-Key", "ak_your_api_key_here");

var created = await http.PostAsJsonAsync("text",
    new { prompt = "Summarise today's sales meeting notes" });
created.EnsureSuccessStatusCode();
var job = await created.Content.ReadFromJsonAsync<Job>();
Console.WriteLine($"submitted {job!.id}");

while (job.status is "waiting" or "processing")
{
    await Task.Delay(3000);
    job = await http.GetFromJsonAsync<Job>($"jobs/{job.id}");
}
Console.WriteLine($"{job!.status}: {job.response ?? job.error}");

foreach (var f in job.files ?? [])
{
    var bytes = await http.GetByteArrayAsync($"files/{f.id}");
    await File.WriteAllBytesAsync(f.name, bytes);
    Console.WriteLine($"saved {f.name}");
}

record JobFile(int id, string name, string mime_type);
record Job(string id, string status, string? response, string? error, JobFile[]? files);
