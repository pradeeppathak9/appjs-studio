package com.appjs.restyle.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.ImageDecoder
import android.graphics.Paint
import android.graphics.Rect
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.max
import kotlin.math.roundToInt

interface ImageGenerator {
    /** Produces a styled image from [source] at [ratio]. Runs off the main thread. [onCharged] gets the
     *  user's balance as soon as the server accepts (and charges) the run, before the image is ready. */
    suspend fun generate(
        source: Bitmap,
        template: StyleTemplate,
        ratio: OutputRatio,
        onCharged: (credits: Int) -> Unit = {},
    ): Bitmap
}

/** Runs the style's template on AppJs Studio: the photo is cropped to the chosen ratio first, so
 *  the template (aspect ratio "auto") returns an image of the same shape. */
class ApiImageGenerator(private val api: ApiClient) : ImageGenerator {
    override suspend fun generate(
        source: Bitmap,
        template: StyleTemplate,
        ratio: OutputRatio,
        onCharged: (credits: Int) -> Unit,
    ): Bitmap {
        val cropped = withContext(Dispatchers.Default) { ImageUtils.cropToRatio(source, ratio) }
        return api.generate(template.id, cropped, onCharged)
    }
}

object ImageUtils {
    /** Decodes [uri] (EXIF-rotated) as a software bitmap no larger than [maxSide]. */
    suspend fun decode(context: Context, uri: Uri, maxSide: Int = 1600): Bitmap = withContext(Dispatchers.IO) {
        val source = ImageDecoder.createSource(context.contentResolver, uri)
        ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            val longest = max(info.size.width, info.size.height)
            if (longest > maxSide) {
                val s = maxSide.toFloat() / longest
                decoder.setTargetSize((info.size.width * s).roundToInt(), (info.size.height * s).roundToInt())
            }
        }
    }

    fun cropToRatio(src: Bitmap, ratio: OutputRatio): Bitmap {
        val target = ratio.w.toFloat() / ratio.h
        val current = src.width.toFloat() / src.height
        val rect = if (current > target) {
            val w = (src.height * target).roundToInt()
            Rect((src.width - w) / 2, 0, (src.width - w) / 2 + w, src.height)
        } else {
            val h = (src.width / target).roundToInt()
            Rect(0, (src.height - h) / 2, src.width, (src.height - h) / 2 + h)
        }
        val out = Bitmap.createBitmap(rect.width(), rect.height(), Bitmap.Config.ARGB_8888)
        Canvas(out).drawBitmap(src, rect, Rect(0, 0, rect.width(), rect.height()), Paint(Paint.FILTER_BITMAP_FLAG))
        return out
    }
}
