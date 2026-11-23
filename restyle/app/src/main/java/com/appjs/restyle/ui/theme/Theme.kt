package com.appjs.restyle.ui.theme

import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.appjs.restyle.R

/** Colour tokens taken from the Restyle design. */
object RColors {
    val Brand = Color(0xFF4F46E5)
    val BrandDark = Color(0xFF3730A3)
    val BrandTint = Color(0xFFF3F2FE)
    val BrandSoft = Color(0xFFE8E7FB)
    val Ink = Color(0xFF14151A)
    val Ink2 = Color(0xFF3A3D48)
    val Muted = Color(0xFF5B5E6B)
    val Border = Color(0xFFDCDDE2)
    val BorderStrong = Color(0xFFD5D6DC)
    val Divider = Color(0xFFECECF0)
    val Surface = Color(0xFFF6F6F8)
    val Field = Color(0xFFF4F4F6)
    val Disabled = Color(0xFFE4E4EA)
    val Placeholder = Color(0xFFC9CCD6)
    val Dashed = Color(0xFFB9BAC4)
    val Error = Color(0xFFB3261E)
    val White = Color.White
}

val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
)

// No colour here: text inherits LocalContentColor (white in buttons, ink elsewhere).
private val base = TextStyle(fontFamily = Inter)

private val RestyleTypography = Typography(
    displaySmall = base.copy(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
    headlineSmall = base.copy(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.4).sp),
    titleLarge = base.copy(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp),
    titleMedium = base.copy(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
    titleSmall = base.copy(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = base.copy(fontSize = 15.sp, lineHeight = 22.sp),
    bodyMedium = base.copy(fontSize = 14.sp, lineHeight = 20.sp),
    bodySmall = base.copy(fontSize = 13.sp, lineHeight = 18.sp),
    labelLarge = base.copy(fontSize = 16.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = base.copy(fontSize = 13.sp, lineHeight = 16.sp, fontWeight = FontWeight.SemiBold),
    labelSmall = base.copy(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium),
)

@Composable
fun RestyleTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = RColors.Brand,
            onPrimary = RColors.White,
            primaryContainer = RColors.BrandSoft,
            onPrimaryContainer = RColors.BrandDark,
            background = RColors.White,
            onBackground = RColors.Ink,
            surface = RColors.White,
            onSurface = RColors.Ink,
            onSurfaceVariant = RColors.Muted,
            outline = RColors.Border,
        ),
        typography = RestyleTypography,
    ) {
        CompositionLocalProvider(LocalContentColor provides RColors.Ink, content = content)
    }
}
