package com.appjs.restyle.data

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit

/**
 * The AppJs Studio API for this app (`/v1/app/...`, contract in appjs-studio/docs/APPS_API.md).
 * Every call carries the app key and this install's device id; once signed in, also the session.
 */
class ApiClient(
    private val baseUrl: String,
    private val appKey: String,
    private val deviceId: String,
    private val token: () -> String?,
) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    // ---- low level -----------------------------------------------------------------------------

    private fun request(path: String): Request.Builder {
        val b = Request.Builder()
            .url(baseUrl + path)
            .header("X-App-Key", appKey)
            .header("X-Device-Id", deviceId)
            .header("Accept", "application/json")
        token()?.let { b.header("Authorization", "Bearer $it") }
        return b
    }

    private suspend fun send(req: Request): String = withContext(Dispatchers.IO) {
        if (appKey.isBlank()) throw ApiException(0, "no_app_key", "This build has no app key (appjs.appKey in local.properties).")
        http.newCall(req).execute().use { res ->
            val body = res.body?.string().orEmpty()
            if (!res.isSuccessful) throw ApiException.from(res.code, body)
            body
        }
    }

    private suspend fun get(path: String): String = send(request(path).get().build())

    private suspend fun postJson(path: String, json: JSONObject): String =
        send(request(path).post(json.toString().toRequestBody(JSON)).build())

    // ---- app & sign-in ---------------------------------------------------------------------------

    suspend fun config(): AppConfig {
        val o = JSONObject(get("/v1/app"))
        val signIn = o.getJSONObject("sign_in")
        return AppConfig(
            googleEnabled = signIn.optBoolean("google"),
            phoneEnabled = signIn.optBoolean("phone"),
            googleClientId = signIn.str("google_client_id"),
            requireLogin = o.optBoolean("require_login"),
        )
    }

    /** Returns the challenge id to verify with. [phone] is 10 digits or +<country><number>. */
    suspend fun sendOtp(phone: String): String =
        JSONObject(postJson("/v1/app/auth/otp/send", JSONObject().put("phone", phone))).getString("challenge_id")

    suspend fun verifyOtp(challengeId: String, code: String): SignedIn =
        signedIn(postJson("/v1/app/auth/otp/verify", JSONObject().put("challenge_id", challengeId).put("code", code)))

    suspend fun signInWithGoogle(idToken: String): SignedIn =
        signedIn(postJson("/v1/app/auth/google", JSONObject().put("id_token", idToken)))

    suspend fun logout() {
        send(request("/v1/app/auth/logout").post(ByteArray(0).toRequestBody()).build())
    }

    suspend fun me(): Account = account(JSONObject(get("/v1/app/me")))

    /** Start the free trial of [planId] (a plan with `trial_enabled`); returns the updated account. */
    suspend fun startTrial(planId: String): Account =
        account(JSONObject(postJson("/v1/app/me/trial", JSONObject().put("plan_id", planId))))

    // ---- catalog ---------------------------------------------------------------------------------

    suspend fun templates(): List<StyleTemplate> {
        val arr = JSONObject(get("/v1/app/templates")).getJSONArray("templates")
        return (0 until arr.length()).map { i -> Templates.fromApi(arr.getJSONObject(i), first = i == 0) }
    }

    suspend fun plans(): List<Plan> {
        val arr = JSONArray(get("/v1/app/plans"))
        return (0 until arr.length()).map { i -> Plan.fromApi(arr.getJSONObject(i)) }
    }

    // ---- generation ----------------------------------------------------------------------------

    /** Run [templateSlug] on [photo], wait for the result and return it. Credits are charged by the
     *  server when the run is accepted (the new balance goes to [onCharged] right away), and refunded
     *  by it if the job fails. */
    suspend fun generate(templateSlug: String, photo: Bitmap, onCharged: (credits: Int) -> Unit = {}): Bitmap {
        val jpeg = withContext(Dispatchers.Default) {
            ByteArrayOutputStream().also { photo.compress(Bitmap.CompressFormat.JPEG, 90, it) }.toByteArray()
        }
        val form = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("photo", "photo.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
            .build()
        var job = JSONObject(send(request("/v1/app/templates/$templateSlug/generations").post(form).build()))
        if (job.has("credits") && !job.isNull("credits")) onCharged(job.getInt("credits"))
        val id = job.getString("id")
        val started = System.currentTimeMillis()
        while (job.getString("status") != "succeeded") {
            if (job.getString("status") == "failed") {
                val err = job.optJSONObject("error")
                throw ApiException(200, err?.str("code") ?: "failed", err?.str("message") ?: "generation failed")
            }
            val waited = System.currentTimeMillis() - started
            if (waited > 5 * 60_000) throw ApiException(0, "timeout", "the image is taking too long")
            delay(if (waited < 30_000) 2_000 else 5_000)
            job = JSONObject(get("/v1/app/generations/$id"))
        }
        val url = job.getJSONArray("assets").getJSONObject(0).getString("url")
        return withContext(Dispatchers.IO) {
            http.newCall(request(url).get().build()).execute().use { res ->
                if (!res.isSuccessful) throw ApiException.from(res.code, res.body?.string().orEmpty())
                val bytes = res.body!!.bytes()
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: throw ApiException(0, "bad_image", "couldn't read the result")
            }
        }
    }

    // ---- parsing ------------------------------------------------------------------------------------

    private fun signedIn(body: String): SignedIn {
        val o = JSONObject(body)
        return SignedIn(o.getString("token"), account(o.getJSONObject("user")), o.optBoolean("is_new"))
    }

    private fun account(u: JSONObject): Account {
        val sub = u.optJSONObject("subscription")
        return Account(
            user = User(
                id = u.getString("id"),
                name = u.str("name"),
                email = u.str("email"),
                phone = u.str("phone"),
                photoUrl = u.str("photo_url"),
            ),
            credits = u.optInt("credits"),
            planId = sub?.getJSONObject("plan")?.str("id"),
            planName = sub?.getJSONObject("plan")?.str("name"),
            onTrial = sub?.optBoolean("trial") ?: false,
            periodEnd = sub?.str("current_period_end"),
            trialUsed = u.optBoolean("trial_used"),
        )
    }

    companion object {
        private val JSON = "application/json".toMediaType()
    }
}

data class AppConfig(
    val googleEnabled: Boolean,
    val phoneEnabled: Boolean,
    val googleClientId: String?,
    val requireLogin: Boolean,
)

/** The signed-in user as the server knows them: profile, balance and current plan. */
data class Account(
    val user: User,
    val credits: Int,
    val planId: String?,
    val planName: String?,
    val onTrial: Boolean = false,
    val periodEnd: String? = null,
    val trialUsed: Boolean = false,
)

data class SignedIn(val token: String, val account: Account, val isNew: Boolean)

/** An error from the API (`{"error": {"code", "message", "details"}}`), or a network/client failure
 *  (status 0). Jobs that fail after being accepted use their job error code. */
class ApiException(
    val status: Int,
    val code: String,
    override val message: String,
    val details: JSONArray? = null,
) : Exception(message) {
    fun detailInt(key: String): Int? =
        details?.optJSONObject(0)?.takeIf { it.has(key) }?.optInt(key)

    companion object {
        fun from(status: Int, body: String): ApiException = runCatching {
            val e = JSONObject(body).getJSONObject("error")
            ApiException(status, e.optString("code", "error"), e.optString("message", "request failed"), e.optJSONArray("details"))
        }.getOrElse { ApiException(status, "http_$status", "request failed ($status)") }
    }
}

internal fun JSONObject.str(key: String): String? = if (!has(key) || isNull(key)) null else optString(key).ifEmpty { null }
