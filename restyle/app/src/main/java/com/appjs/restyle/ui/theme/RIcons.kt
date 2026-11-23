package com.appjs.restyle.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/**
 * Stroke icons from the design (24×24 viewBox, 2px round strokes).
 * Use with Icon(..., tint = ...) so they pick up the content colour.
 */
object RIcons {
    private fun circle(cx: Float, cy: Float, r: Float) =
        "M${cx - r},${cy}a$r,$r 0 1,0 ${2 * r},0a$r,$r 0 1,0 ${-2 * r},0"

    private fun rect(x: Float, y: Float, w: Float, h: Float, rx: Float) =
        "M${x + rx},${y}h${w - 2 * rx}a$rx,$rx 0 0 1 $rx,$rx" +
            "v${h - 2 * rx}a$rx,$rx 0 0 1 -$rx,$rx" +
            "h${-(w - 2 * rx)}a$rx,$rx 0 0 1 -$rx,-$rx" +
            "v${-(h - 2 * rx)}a$rx,$rx 0 0 1 $rx,-${rx}z"

    private fun icon(name: String, strokeWidth: Float = 2f, vararg paths: String): ImageVector {
        val b = ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
        paths.forEach { d ->
            b.addPath(
                pathData = addPathNodes(d),
                fill = null,
                stroke = SolidColor(Color.Black),
                strokeLineWidth = strokeWidth,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
            )
        }
        return b.build()
    }

    private const val SPARK = "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"

    val Sparkle = icon("sparkle", 2f, SPARK)
    val Sparkles = icon("sparkles", 2f, SPARK, "M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z")
    val ChevronDown = icon("chevronDown", 2f, "M6 9l6 6 6-6")
    val ArrowBack = icon("back", 2f, "M19 12H5", "M12 19l-7-7 7-7")
    val Close = icon("close", 2f, "M18 6L6 18", "M6 6l12 12")
    val Phone = icon("phone", 2f, rect(5f, 2f, 14f, 20f, 2f), "M12 18h.01")
    val Search = icon("search", 2f, circle(11f, 11f, 7f), "M21 21l-4.3-4.3")
    val Grid = icon(
        "grid", 2f,
        rect(3f, 3f, 7f, 7f, 1.5f), rect(14f, 3f, 7f, 7f, 1.5f),
        rect(3f, 14f, 7f, 7f, 1.5f), rect(14f, 14f, 7f, 7f, 1.5f),
    )
    val Image = icon("image", 2f, rect(3f, 3f, 18f, 18f, 3f), circle(9f, 9f, 2f), "M21 15l-5-5L5 21")
    val ImageThin = icon("imageThin", 1.5f, rect(3f, 3f, 18f, 18f, 3f), circle(9f, 9f, 2f), "M21 15l-5-5L5 21")
    val Person = icon("person", 2f, circle(12f, 8f, 4f), "M4 21c0-4 3.6-7 8-7s8 3 8 7")
    val Upload = icon("upload", 2f, "M12 16V4", "M7 9l5-5 5 5", "M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3")
    val Camera = icon("camera", 2f, "M4 8h3l2-3h6l2 3h3v11H4z", circle(12f, 13f, 3.5f))
    val Refresh = icon("refresh", 2f, "M21 12a9 9 0 1 1-3-6.7", "M21 4v5h-5")
    val Download = icon("download", 2f, "M12 4v12", "M7 11l5 5 5-5", "M4 20h16")
    val Share = icon(
        "share", 2f,
        circle(18f, 5f, 3f), circle(6f, 12f, 3f), circle(18f, 19f, 3f),
        "M8.6 13.5l6.8 4", "M15.4 6.5l-6.8 4",
    )
    val Logout = icon("logout", 2f, "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9")
    val Check = icon("check", 2.5f, "M5 12.5l4.5 4.5L19 7.5")
    val Plus = icon("plus", 2f, "M12 5v14", "M5 12h14")
}
