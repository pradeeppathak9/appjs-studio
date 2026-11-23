package com.appjs.restyle.data

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * On-device storage for the session, credits and creations.
 * Credits and plans live on the server; this keeps the session and the user's images.
 */
class LocalStore(private val context: Context) {
    private val prefs = context.getSharedPreferences("restyle", Context.MODE_PRIVATE)
    private val dir = File(context.filesDir, "creations").apply { mkdirs() }

    /** The signed-in user, or null when logged out. The ID token is not persisted. */
    var user: User?
        get() {
            val id = prefs.getString("user.id", null)
            // Sessions saved before Google sign-in existed only stored a phone number.
            val legacyPhone = prefs.getString("phone", null)
            return when {
                id != null -> User(
                    id = id,
                    name = prefs.getString("user.name", null),
                    email = prefs.getString("user.email", null),
                    phone = prefs.getString("user.phone", null),
                    photoUrl = prefs.getString("user.photo", null),
                )
                legacyPhone != null -> User("phone:$legacyPhone", null, null, legacyPhone, null)
                else -> null
            }
        }
        set(u) {
            prefs.edit().apply {
                remove("phone")
                if (u == null) {
                    listOf("user.id", "user.name", "user.email", "user.phone", "user.photo").forEach(::remove)
                } else {
                    putString("user.id", u.id)
                    putString("user.name", u.name)
                    putString("user.email", u.email)
                    putString("user.phone", u.phone)
                    putString("user.photo", u.photoUrl)
                }
            }.apply()
        }

    /** The session from AppJs Studio (`Authorization: Bearer ...`), or null when signed out. */
    var token: String?
        get() = prefs.getString("session.token", null)
        set(v) = prefs.edit().putString("session.token", v).apply()

    /** A random id for this install, sent as X-Device-Id (not a hardware id). */
    val deviceId: String
        get() = prefs.getString("device.id", null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString("device.id", it).apply()
        }

    fun loadCreations(): List<Creation> {
        val raw = prefs.getString("creations", null) ?: return emptyList()
        val arr = JSONArray(raw)
        return (0 until arr.length()).mapNotNull { i ->
            val o = arr.getJSONObject(i)
            runCatching {
                Creation(
                    id = o.getString("id"),
                    templateId = o.getString("templateId"),
                    ratio = OutputRatio.valueOf(o.getString("ratio")),
                    originalPath = o.getString("original"),
                    resultPath = o.getString("result"),
                    createdAt = o.getLong("createdAt"),
                )
            }.getOrNull()?.takeIf { File(it.resultPath).exists() }
        }
    }

    private fun saveCreations(list: List<Creation>) {
        val arr = JSONArray()
        list.forEach {
            arr.put(
                JSONObject()
                    .put("id", it.id)
                    .put("templateId", it.templateId)
                    .put("ratio", it.ratio.name)
                    .put("original", it.originalPath)
                    .put("result", it.resultPath)
                    .put("createdAt", it.createdAt),
            )
        }
        prefs.edit().putString("creations", arr.toString()).apply()
    }

    suspend fun addCreation(
        original: Bitmap,
        result: Bitmap,
        template: StyleTemplate,
        ratio: OutputRatio,
        existing: List<Creation>,
    ): Creation = withContext(Dispatchers.IO) {
        val id = UUID.randomUUID().toString()
        val o = File(dir, "${id}_orig.jpg").also { f -> f.outputStream().use { original.compress(Bitmap.CompressFormat.JPEG, 90, it) } }
        val r = File(dir, "${id}_result.jpg").also { f -> f.outputStream().use { result.compress(Bitmap.CompressFormat.JPEG, 92, it) } }
        val c = Creation(id, template.id, ratio, o.absolutePath, r.absolutePath, System.currentTimeMillis())
        saveCreations(listOf(c) + existing)
        c
    }

    suspend fun loadBitmap(path: String): Bitmap? = withContext(Dispatchers.IO) { BitmapFactory.decodeFile(path) }

    fun clearSession() {
        user = null
        token = null
    }

    /** Copies the result into the shared Pictures/Restyle folder. */
    suspend fun saveToGallery(creation: Creation): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "Restyle_${creation.createdAt}.jpg")
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/Restyle")
            }
            val resolver = context.contentResolver
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return@runCatching false
            resolver.openOutputStream(uri)?.use { out -> File(creation.resultPath).inputStream().use { it.copyTo(out) } }
            true
        }.getOrDefault(false)
    }

    fun shareIntent(creation: Creation): Intent {
        val shareDir = File(context.cacheDir, "share").apply { mkdirs() }
        val file = File(shareDir, "Restyle_${creation.createdAt}.jpg")
        File(creation.resultPath).copyTo(file, overwrite = true)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "image/jpeg"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return Intent.createChooser(send, "Share your creation")
    }

    /** A fresh content:// URI the camera app can write a photo into. */
    fun newCameraUri(): Uri {
        val camDir = File(context.cacheDir, "camera").apply { mkdirs() }
        val file = File(camDir, "photo_${System.currentTimeMillis()}.jpg")
        return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    }
}
