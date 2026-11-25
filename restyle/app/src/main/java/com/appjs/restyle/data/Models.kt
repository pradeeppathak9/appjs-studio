package com.appjs.restyle.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import org.json.JSONObject
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.abs

/** A style the user can apply to a photo: a template of the app in AppJs Studio. [id] is its slug. */
data class StyleTemplate(
    val id: String,
    val name: String,
    val meta: String,
    val category: String,
    val color: Color,
    val credits: Int,
    val isNew: Boolean = false,
    val trending: Boolean = false,
    val subtitle: String = "",
)

enum class OutputRatio(val label: String, val hint: String, val w: Int, val h: Int) {
    Square("1:1", "Post", 1, 1),
    Portrait("4:5", "Portrait", 4, 5),
    Story("9:16", "Story", 9, 16),
}

/** One generated image the user has made. */
data class Creation(
    val id: String,
    val templateId: String,
    val ratio: OutputRatio,
    val originalPath: String,
    val resultPath: String,
    val createdAt: Long,
)

/**
 * The app's styles, as last loaded from the server (observable by Compose). The server decides which
 * styles exist, their order and price; [hints] only add the design's colour and category.
 */
object Templates {
    var all by mutableStateOf<List<StyleTemplate>>(emptyList())

    val categories: List<String> get() = listOf("All") + all.map { it.category }.distinct()

    fun byId(id: String?): StyleTemplate? = all.firstOrNull { it.id == id }

    /** The first style (the dashboard order puts it first), or a placeholder while nothing is loaded. */
    val trending: StyleTemplate get() = all.firstOrNull { it.trending } ?: all.firstOrNull() ?: PLACEHOLDER

    private val PLACEHOLDER = StyleTemplate("", "Style", "", "All", Color(0xFF2F4B3A), 0)

    private data class Hint(val category: String, val meta: String, val color: Color, val isNew: Boolean = false)

    private val hints = mapOf(
        "ghibli-style" to Hint("Anime", "Anime · Hand-painted", Color(0xFF3C5A3A)),
        "anime-watercolor" to Hint("Anime", "Anime · Popular", Color(0xFF2F4B3A)),
        "80s-style" to Hint("Retro", "Retro · Synthwave", Color(0xFF3B1F5C)),
        "80s-retro" to Hint("Retro", "Retro · Synthwave", Color(0xFF3B1F5C)),
        "oil-portrait" to Hint("Painting", "Painting · Classic", Color(0xFF7A3B1D)),
        "comic-pop" to Hint("Cartoon", "Cartoon · Bold ink", Color(0xFF1E3A5F)),
        "clay-figure" to Hint("3D", "3D · Playful", Color(0xFF8A4B2E), isNew = true),
        "pixel-art" to Hint("Retro", "Retro · 16-bit", Color(0xFF24364F)),
        "90s-film" to Hint("Retro", "Retro · Grainy", Color(0xFF5A4632), isNew = true),
        "cyber-neon" to Hint("3D", "3D · Night city", Color(0xFF2B1640)),
    )

    private val palette = listOf(
        Color(0xFF2F4B3A), Color(0xFF3B1F5C), Color(0xFF7A3B1D), Color(0xFF1E3A5F),
        Color(0xFF8A4B2E), Color(0xFF24364F), Color(0xFF5A4632), Color(0xFF2B1640),
    )

    fun fromApi(o: JSONObject, first: Boolean): StyleTemplate {
        val slug = o.getString("slug")
        val description = o.str("description").orEmpty()
        val hint = hints[slug]
        return StyleTemplate(
            id = slug,
            name = o.getString("title"),
            meta = hint?.meta ?: description.ifEmpty { "Style" },
            category = hint?.category ?: "More",
            color = hint?.color ?: palette[abs(slug.hashCode()) % palette.size],
            credits = o.optInt("credit_cost", 1),
            isNew = hint?.isNew ?: false,
            trending = first,
            subtitle = description,
        )
    }
}

/** A subscription plan offered by the app (from the server; prices are shown, payment comes later). */
data class Plan(
    val id: String,
    val slug: String,
    val title: String,
    val price: String,
    val period: String,
    val creditsPerMonth: Int,
    val note: String,
    val badge: String? = null,
    val trialEnabled: Boolean = false,
    val trialDays: Int = 0,
    val trialCredits: Int = 0,
) {
    companion object {
        fun fromApi(o: JSONObject) = Plan(
            id = o.getString("id"),
            slug = o.getString("slug"),
            title = o.getString("name"),
            price = formatPrice(o.getInt("price_minor"), o.optString("currency", "INR")),
            period = o.optString("billing_period", "month"),
            creditsPerMonth = o.optInt("credits_per_month"),
            note = o.str("description").orEmpty(),
            badge = o.str("badge"),
            trialEnabled = o.optBoolean("trial_enabled"),
            trialDays = o.optInt("trial_days"),
            trialCredits = o.optInt("trial_credits"),
        )

        fun formatPrice(minor: Int, currency: String): String {
            val symbol = when (currency) { "INR" -> "₹"; "USD" -> "$"; "EUR" -> "€"; else -> "$currency " }
            val nf = NumberFormat.getNumberInstance(Locale.forLanguageTag("en-IN")).apply {
                minimumFractionDigits = if (minor % 100 == 0) 0 else 2
                maximumFractionDigits = 2
            }
            return symbol + nf.format(minor / 100.0)
        }
    }
}

fun creditsLabel(n: Int) = if (n == 1) "1 credit" else "$n credits"
