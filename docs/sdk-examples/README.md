# SDK Examples

Ready-to-adapt clients for the AIAuto public API (`/api/public/v1`):

| File | Stack |
|---|---|
| `aiauto_client.py` | Python (requests) |
| `aiauto.js` | Node.js / Express webhook / React backend routes |
| `aiauto.php` | PHP (cURL) + Laravel `Http` facade snippet + webhook verify |
| `AiAutoClient.cs` | C# / .NET 8 |
| `AiAuto.kt` | Android (Kotlin, OkHttp) |
| `aiauto_client.dart` | Flutter / Dart |

Replace `https://your-server` and `ak_your_api_key_here`, then run.
Full guide: [`../PUBLIC_API.md`](../PUBLIC_API.md).

Mobile/desktop apps you distribute should NEVER embed a key — call your
own backend, which holds the key, instead.
