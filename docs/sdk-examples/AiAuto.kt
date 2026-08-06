// AIAuto API client — Android (Kotlin) example using OkHttp + kotlinx.serialization.
// NOTE: never ship an API key inside a distributed app — call your own
// backend, which holds the key, from the app instead.
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

const val BASE = "https://your-server/api/public/v1"
const val KEY = "ak_your_api_key_here"
val client = OkHttpClient()

fun submitText(prompt: String): JSONObject {
    val body = JSONObject(mapOf("prompt" to prompt)).toString()
        .toRequestBody("application/json".toMediaType())
    val req = Request.Builder().url("$BASE/text")
        .header("X-API-Key", KEY).post(body).build()
    client.newCall(req).execute().use { res ->
        require(res.isSuccessful) { "HTTP ${res.code}" }
        return JSONObject(res.body!!.string())
    }
}

suspend fun waitFor(jobId: String): JSONObject {
    while (true) {
        val req = Request.Builder().url("$BASE/jobs/$jobId")
            .header("X-API-Key", KEY).build()
        client.newCall(req).execute().use { res ->
            val job = JSONObject(res.body!!.string())
            if (job.getString("status") !in listOf("waiting", "processing")) return job
        }
        delay(3000)
    }
}
