<?php
/**
 * AIAuto API client — plain PHP example (cURL).
 *
 * Laravel: use Http facade instead —
 *   $job = Http::withHeaders(['X-API-Key' => config('services.aiauto.key')])
 *       ->post(config('services.aiauto.base').'/text', ['prompt' => $prompt])
 *       ->throw()->json();
 */
const BASE = "https://your-server/api/public/v1";
const KEY  = "ak_your_api_key_here";

function api(string $method, string $path, ?array $json = null): array {
    $ch = curl_init(BASE . $path);
    $headers = ["X-API-Key: " . KEY];
    if ($json !== null) {
        $headers[] = "Content-Type: application/json";
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($json));
    }
    curl_setopt_array($ch, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $body = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    $data = json_decode($body, true);
    if ($status >= 400) throw new Exception($data["detail"] ?? "HTTP $status");
    return $data;
}

// Webhook verification (e.g. in a Laravel route):
function verifyWebhook(string $secret, string $ts, string $rawBody, string $sig): bool {
    if (abs(time() - (int)$ts) > 300) return false;           // replay protection
    $expected = hash_hmac("sha256", $ts . "." . $rawBody, $secret);
    return hash_equals($expected, $sig);
}

$job = api("POST", "/text", ["prompt" => "Draft a quotation follow-up message"]);
echo "submitted {$job['id']}\n";
do {
    sleep(3);
    $job = api("GET", "/jobs/{$job['id']}");
} while (!in_array($job["status"], ["completed", "failed", "cancelled"]));
echo $job["status"] . "\n" . ($job["response"] ?? $job["error"]) . "\n";
