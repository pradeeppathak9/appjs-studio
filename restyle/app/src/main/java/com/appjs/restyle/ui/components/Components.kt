package com.appjs.restyle.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons

private val ButtonShape = RoundedCornerShape(14.dp)

@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        shape = ButtonShape,
        colors = ButtonDefaults.buttonColors(
            containerColor = RColors.Brand,
            contentColor = Color.White,
            disabledContainerColor = if (loading) RColors.Brand else RColors.Disabled,
            disabledContentColor = if (loading) Color.White else RColors.Muted,
        ),
        modifier = modifier.fillMaxWidth().height(56.dp),
    ) {
        if (loading) {
            CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        } else {
            ButtonContent(text, icon)
        }
    }
}

@Composable
fun SecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    height: Dp = 56.dp,
) {
    OutlinedButton(
        onClick = onClick,
        shape = ButtonShape,
        border = BorderStroke(1.dp, RColors.Border),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = RColors.Ink),
        modifier = modifier.height(height),
    ) { ButtonContent(text, icon) }
}

@Composable
private fun RowScope.ButtonContent(text: String, icon: ImageVector?) {
    if (icon != null) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(8.dp))
    }
    Text(text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
}

@Composable
fun NavIconButton(icon: ImageVector, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(onClick = onClick, modifier = modifier.size(48.dp)) {
        Icon(icon, contentDescription = label, tint = RColors.Ink, modifier = Modifier.size(24.dp))
    }
}

/** Small rounded label, e.g. "Trending", "2 credits". */
@Composable
fun Pill(
    text: String,
    background: Color,
    content: Color,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    height: Dp = 26.dp,
    fontSize: Int = 12,
) {
    Surface(color = background, contentColor = content, shape = RoundedCornerShape(50), modifier = modifier.height(height)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            modifier = Modifier.padding(horizontal = 9.dp),
        ) {
            if (icon != null) Icon(icon, null, modifier = Modifier.size(12.dp))
            Text(text, fontSize = fontSize.sp, fontWeight = FontWeight.Bold, color = content)
        }
    }
}

@Composable
fun CreditsChip(credits: Int, modifier: Modifier = Modifier, onClick: () -> Unit = {}) {
    Surface(
        onClick = onClick,
        color = RColors.BrandTint,
        contentColor = RColors.BrandDark,
        shape = RoundedCornerShape(50),
        modifier = modifier.height(36.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.padding(horizontal = 12.dp),
        ) {
            Icon(RIcons.Sparkle, null, modifier = Modifier.size(16.dp))
            Text(if (credits == 1) "1 credit" else "$credits credits", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
        }
    }
}

/** The sun-and-hills illustration used on the Anime Watercolor cards. */
@Composable
fun HillsArt(modifier: Modifier = Modifier, sunRadiusFraction: Float = 0.12f) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        drawCircle(
            Color(0xFFF2D27A).copy(alpha = 0.85f),
            radius = w * sunRadiusFraction,
            center = Offset(w * 0.72f, h * 0.26f),
        )
        val back = Path().apply {
            moveTo(0f, h); lineTo(w * 0.3f, h * 0.55f); lineTo(w * 0.53f, h * 0.76f)
            lineTo(w * 0.77f, h * 0.45f); lineTo(w, h * 0.7f); lineTo(w, h); close()
        }
        drawPath(back, Color(0xFF4E7A5C))
        val front = Path().apply {
            moveTo(0f, h); lineTo(w * 0.26f, h * 0.82f); lineTo(w * 0.52f, h * 0.9f)
            lineTo(w * 0.74f, h * 0.77f); lineTo(w, h * 0.86f); lineTo(w, h); close()
        }
        drawPath(front, Color(0xFF7FA67F))
    }
}
