// AIAuto API client — Flutter/Dart example (package:http).
// NOTE: never ship an API key inside a distributed app — proxy through
// your own backend instead.
import 'dart:convert';
import 'package:http/http.dart' as http;

const base = 'https://your-server/api/public/v1';
const key = 'ak_your_api_key_here';
const headers = {'X-API-Key': key, 'Content-Type': 'application/json'};

Future<Map<String, dynamic>> submitImage(String prompt) async {
  final res = await http.post(Uri.parse('$base/images'),
      headers: headers, body: jsonEncode({'prompt': prompt}));
  if (res.statusCode >= 400) throw Exception(jsonDecode(res.body)['detail']);
  return jsonDecode(res.body);
}

Future<Map<String, dynamic>> waitFor(String jobId) async {
  while (true) {
    final res = await http.get(Uri.parse('$base/jobs/$jobId'),
        headers: {'X-API-Key': key});
    final job = jsonDecode(res.body) as Map<String, dynamic>;
    if (!['waiting', 'processing'].contains(job['status'])) return job;
    await Future.delayed(const Duration(seconds: 3));
  }
}

Future<List<int>> downloadFile(int fileId) async {
  final res = await http.get(Uri.parse('$base/files/$fileId'),
      headers: {'X-API-Key': key});
  return res.bodyBytes;
}
