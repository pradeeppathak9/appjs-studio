package com.appjs.restyle

import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.appjs.restyle.data.Account
import com.appjs.restyle.data.ApiClient
import com.appjs.restyle.data.ApiException
import com.appjs.restyle.data.ApiImageGenerator
import com.appjs.restyle.data.AppConfig
import com.appjs.restyle.data.Creation
import com.appjs.restyle.data.GoogleAuth
import com.appjs.restyle.data.GoogleSignInResult
import com.appjs.restyle.data.ImageGenerator
import com.appjs.restyle.data.ImageUtils
import com.appjs.restyle.data.LocalStore
import com.appjs.restyle.data.OutputRatio
import com.appjs.restyle.data.Plan
import com.appjs.restyle.data.SignedIn
import com.appjs.restyle.data.StyleTemplate
import com.appjs.restyle.data.Templates
import kotlinx.coroutines.launch
import java.io.IOException

/** App state. Accounts, credits, styles and plans come from AppJs Studio (app "restyle-ai"). */
class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val store = LocalStore(app)
    private val api = ApiClient(BuildConfig.APPJS_BASE_URL, BuildConfig.APPJS_APP_KEY, store.deviceId) { store.token }
    private val googleAuth = GoogleAuth()
    private val generator: ImageGenerator = ApiImageGenerator(api)

    // --- Server config & session -------------------------------------------
    var config by mutableStateOf<AppConfig?>(null)
        private set
    val googleEnabled get() = config?.let { it.googleEnabled && !it.googleClientId.isNullOrBlank() } ?: false
    val countryCode = "+91"
    var user by mutableStateOf(store.user.takeIf { store.token != null })
        private set
    val isLoggedIn get() = user != null

    /** Phone number being typed on the phone-login path (10 digits). */
    var phone by mutableStateOf("")
        private set
    private var challengeId: String? = null
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    // --- Credits, plans, catalog -------------------------------------------
    var credits by mutableStateOf(0)
        private set
    private var planId by mutableStateOf<String?>(null)
    var planName by mutableStateOf<String?>(null)
        private set
    val plans = mutableStateListOf<Plan>()

    /** The user's current plan, when it's one of the plans on offer. */
    val plan: Plan? get() = plans.firstOrNull { it.id == planId }
    var catalogLoading by mutableStateOf(false)
        private set
    var catalogError by mutableStateOf<String?>(null)
        private set

    val creations = mutableStateListOf<Creation>().apply { addAll(store.loadCreations()) }

    // --- New-creation draft --------------------------------------------
    var templateId by mutableStateOf("")
        private set
    val template: StyleTemplate get() = Templates.byId(templateId) ?: Templates.trending
    var ratio by mutableStateOf(OutputRatio.Portrait)
    var photo by mutableStateOf<Bitmap?>(null)
        private set
    var generating by mutableStateOf(false)
        private set

    // --- Result being viewed -------------------------------------------
    var current by mutableStateOf<Creation?>(null)
        private set
    var currentOriginal by mutableStateOf<Bitmap?>(null)
        private set
    var currentResult by mutableStateOf<Bitmap?>(null)
        private set

    init {
        viewModelScope.launch {
            runCatching { api.config() }.onSuccess { config = it }.onFailure { messageFor(it) }
            if (isLoggedIn) refresh()
            loadPlans()
        }
    }

    fun clearError() { error = null }

    // ---- session ---------------------------------------------------------------------------

    /** Reload the account (balance, plan) and the styles. Call on start and when the app resumes. */
    fun refresh() {
        if (!isLoggedIn) return
        viewModelScope.launch {
            runCatching { api.me() }.onSuccess(::apply).onFailure(::handleBackground)
            loadTemplates()
        }
    }

    private suspend fun loadTemplates() {
        catalogLoading = Templates.all.isEmpty()
        runCatching { api.templates() }
            .onSuccess {
                Templates.all = it
                catalogError = null
                if (Templates.byId(templateId) == null) templateId = Templates.trending.id
            }
            .onFailure {
                handleBackground(it)
                catalogError = messageFor(it)
            }
        catalogLoading = false
    }

    private suspend fun loadPlans() {
        runCatching { api.plans() }.onSuccess { plans.clear(); plans.addAll(it) }
    }

    private fun apply(a: Account) {
        user = a.user
        store.user = a.user
        credits = a.credits
        planId = a.planId
        planName = a.planName
    }

    private suspend fun signedIn(s: SignedIn, onSignedIn: () -> Unit) {
        store.token = s.token
        apply(s.account)
        onSignedIn()
        loadTemplates()
    }

    /** A 401 while signed in: the session ended (expired, blocked, signed out elsewhere). */
    private fun handleBackground(e: Throwable) {
        if (e is ApiException && e.status == 401 && store.token != null) endSession()
    }

    private fun endSession() {
        store.clearSession()
        user = null
        credits = 0
        planId = null
        planName = null
        photo = null
        Templates.all = emptyList()
    }

    // ---- phone sign-in -------------------------------------------------------------------------

    fun onPhoneChange(input: String) {
        phone = input.filter { it.isDigit() }.take(10)
        error = null
    }

    val formattedPhone: String get() = formatPhone(phone)

    fun formatPhone(p: String) = if (p.length > 5) p.substring(0, 5) + " " + p.substring(5) else p

    /** "+919876543210" -> "98765 43210" for display next to [countryCode]. */
    fun displayPhone(e164: String): String = formatPhone(e164.removePrefix(countryCode))

    fun sendOtp(onSent: () -> Unit) {
        if (phone.length != 10 || busy) return
        viewModelScope.launch {
            busy = true
            error = null
            runCatching { api.sendOtp(phone) }
                .onSuccess { challengeId = it; onSent() }
                .onFailure { error = messageFor(it) }
            busy = false
        }
    }

    fun verifyOtp(code: String, onVerified: () -> Unit) {
        val id = challengeId ?: return
        if (busy) return
        viewModelScope.launch {
            busy = true
            error = null
            runCatching { api.verifyOtp(id, code) }
                .onSuccess { signedIn(it, onVerified) }
                .onFailure { error = messageFor(it) }
            busy = false
        }
    }

    // ---- Google sign-in ------------------------------------------------------------------------

    /** [activityContext] must be the Activity: the Google account picker shows over it. */
    fun signInWithGoogle(activityContext: Context, onSignedIn: () -> Unit) {
        val clientId = config?.googleClientId
        if (busy || clientId.isNullOrBlank()) return
        viewModelScope.launch {
            busy = true
            error = null
            when (val r = googleAuth.signIn(activityContext, clientId)) {
                is GoogleSignInResult.Success ->
                    runCatching { api.signInWithGoogle(r.idToken) }
                        .onSuccess { signedIn(it, onSignedIn) }
                        .onFailure { error = messageFor(it) }
                GoogleSignInResult.Cancelled -> Unit
                is GoogleSignInResult.Failed -> error = r.message
            }
            busy = false
        }
    }

    fun logout(context: Context) {
        viewModelScope.launch {
            runCatching { api.logout() }
            googleAuth.signOut(context)
            endSession()
            phone = ""
            error = null
        }
    }

    // ---- creating ------------------------------------------------------------------------------

    fun selectTemplate(id: String) { templateId = id }

    fun loadPhoto(uri: Uri) {
        viewModelScope.launch {
            runCatching { ImageUtils.decode(getApplication(), uri) }
                .onSuccess { photo = it; error = null }
                .onFailure { error = "Couldn't open that photo." }
        }
    }

    fun clearPhoto() { photo = null }

    fun newCameraUri(): Uri = store.newCameraUri()

    val canAfford get() = credits >= template.credits

    fun generate(onDone: () -> Unit) {
        val src = photo ?: return
        if (generating || !canAfford) return
        val t = template
        val r = ratio
        viewModelScope.launch {
            generating = true
            error = null
            runCatching {
                // the server charged the run: show its new balance now, not after the image is ready
                val result = generator.generate(src, t, r) { left -> credits = left }
                val original = ImageUtils.cropToRatio(src, r)
                val c = store.addCreation(original, result, t, r, creations.toList())
                creations.add(0, c)
                current = c
                currentOriginal = original
                currentResult = result
            }.onSuccess { onDone() }
                .onFailure {
                    handleBackground(it)
                    error = messageFor(it)
                }
            // the server charged (or refunded) the credits: show its balance
            runCatching { api.me() }.onSuccess(::apply)
            generating = false
        }
    }

    fun openCreation(c: Creation) {
        current = c
        currentOriginal = null
        currentResult = null
        viewModelScope.launch {
            currentResult = store.loadBitmap(c.resultPath)
            currentOriginal = store.loadBitmap(c.originalPath)
        }
    }

    /** "Try another style" from the result screen: reuse the original photo. */
    fun restyleCurrent(templateId: String? = null) {
        val c = current ?: return
        templateId?.let { this.templateId = it }
        ratio = c.ratio
        currentOriginal?.let { photo = it }
    }

    fun saveCurrent(onResult: (Boolean) -> Unit) {
        val c = current ?: return
        viewModelScope.launch { onResult(store.saveToGallery(c)) }
    }

    fun shareIntent(): Intent? = current?.let { store.shareIntent(it) }

    // ---- plans ---------------------------------------------------------------------------------

    /** Payments aren't connected yet: an admin gives plans in AppJs Studio. */
    fun subscribe(p: Plan, onDone: () -> Unit) {
        error = "Payments aren't available yet. Ask support to activate the ${p.title} plan; " +
            "your credits appear here as soon as it's on."
        refresh()
    }

    // ---- errors ---------------------------------------------------------------------------------

    private fun messageFor(e: Throwable): String {
        android.util.Log.w("Restyle", "API call failed", e)
        return userMessage(e)
    }

    private fun userMessage(e: Throwable): String = when {
        e is IOException -> "Can't reach the server. Check your connection and try again."
        e !is ApiException -> "Something went wrong. Try again."
        e.code == "otp_invalid" -> "That code didn't work." +
            (e.detailInt("attempts_left")?.let { " $it ${if (it == 1) "try" else "tries"} left." } ?: "")
        e.code == "otp_expired" -> "This code has expired. Tap Resend code."
        e.code == "insufficient_credits" -> "You need more credits for this style."
        e.code == "content_policy" -> "This photo can't be styled. Try a different one. Your credits were refunded."
        e.code == "provider_unavailable" && e.status == 503 ->
            "This style isn't available right now. Your credits weren't used."
        e.status == 200 -> "The image couldn't be made (${e.code}). Your credits were refunded."
        e.code == "unauthenticated" && store.token != null -> "Your session ended. Sign in again."
        e.code == "account_blocked" -> "This account is blocked. Contact support."
        e.code == "app_disabled" -> "Restyle AI is under maintenance. Try again later."
        else -> e.message.replaceFirstChar { it.uppercase() }
    }
}
