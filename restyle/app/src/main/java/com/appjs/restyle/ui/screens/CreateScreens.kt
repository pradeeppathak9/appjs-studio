package com.appjs.restyle.ui.screens

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.appjs.restyle.AppViewModel
import com.appjs.restyle.data.OutputRatio
import com.appjs.restyle.data.Templates
import com.appjs.restyle.data.creditsLabel
import com.appjs.restyle.ui.components.HillsArt
import com.appjs.restyle.ui.components.NavIconButton
import com.appjs.restyle.ui.components.PrimaryButton
import com.appjs.restyle.ui.components.SecondaryButton
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons

// ---------------------------------------------------------------- 04 Add photo

@Composable
fun UploadScreen(
    vm: AppViewModel,
    onBack: () -> Unit,
    onChangeStyle: () -> Unit,
    onGetCredits: () -> Unit,
    onGenerated: () -> Unit,
) {
    val t = vm.template
    var pendingCameraUri by rememberSaveable { mutableStateOf<String?>(null) }
    androidx.compose.runtime.LaunchedEffect(Unit) { vm.clearError() } // not another screen's error

    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        uri?.let(vm::loadPhoto)
    }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = pendingCameraUri
        if (ok && uri != null) vm.loadPhoto(Uri.parse(uri))
    }

    BackHandler(enabled = vm.generating) { /* wait for generation to finish */ }

    Box(Modifier.fillMaxSize().background(Color.White)) {
        Column(Modifier.fillMaxSize().safeDrawingPadding().padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 16.dp)) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.offset(x = (-12).dp)) {
                    NavIconButton(RIcons.ArrowBack, "Back to templates", onBack)
                    Text("New creation", style = MaterialTheme.typography.titleMedium)
                }

                // Selected style
                Row(
                    Modifier.padding(top = 12.dp).fillMaxWidth().background(RColors.Surface, RoundedCornerShape(18.dp)).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Box(Modifier.size(64.dp).clip(RoundedCornerShape(14.dp)).background(t.color)) {
                        if (t.trending) HillsArt(Modifier.fillMaxSize(), sunRadiusFraction = 0f)
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("STYLE", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = RColors.Muted)
                        Text(t.name, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                        Text("${creditsLabel(t.credits)} per image", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
                    }
                    OutlinedButton(
                        onClick = onChangeStyle,
                        border = BorderStroke(1.dp, RColors.Border),
                        shape = RoundedCornerShape(50),
                        modifier = Modifier.height(36.dp),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp),
                    ) { Text("Change", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.Ink) }
                }

                Text("Add your photo", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 24.dp))
                Text(
                    "A clear, well-lit photo of a face or scene works best.",
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                    color = RColors.Muted,
                    modifier = Modifier.padding(top = 6.dp),
                )

                val photo = vm.photo
                if (photo == null) {
                    Column(
                        Modifier
                            .padding(top = 16.dp)
                            .fillMaxWidth()
                            .height(300.dp)
                            .background(Color(0xFFFAFAFB), RoundedCornerShape(22.dp))
                            .drawBehind {
                                drawRoundRect(
                                    color = RColors.Dashed,
                                    cornerRadius = CornerRadius(22.dp.toPx()),
                                    style = Stroke(1.5.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))),
                                )
                            }
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(Modifier.size(56.dp).background(RColors.BrandSoft, CircleShape), contentAlignment = Alignment.Center) {
                            Icon(RIcons.Upload, null, tint = RColors.Brand, modifier = Modifier.size(26.dp))
                        }
                        Text("Upload a photo", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            SecondaryButton("Camera", onClick = {
                                val uri = vm.newCameraUri()
                                pendingCameraUri = uri.toString()
                                camera.launch(uri)
                            }, icon = RIcons.Camera, height = 44.dp)
                            SecondaryButton("Gallery", onClick = {
                                gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            }, icon = RIcons.Image, height = 44.dp)
                        }
                        Text("JPG or PNG, up to 10 MB", fontSize = 12.sp, color = RColors.Muted)
                    }
                } else {
                    Box(
                        Modifier.padding(top = 16.dp).fillMaxWidth().height(300.dp).clip(RoundedCornerShape(22.dp)).background(RColors.Placeholder),
                    ) {
                        Image(
                            photo.asImageBitmap(),
                            contentDescription = "Your selected photo",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxSize(),
                        )
                        IconButton(
                            onClick = vm::clearPhoto,
                            enabled = !vm.generating,
                            modifier = Modifier.align(Alignment.TopEnd).padding(12.dp).size(44.dp).background(RColors.Ink, CircleShape),
                        ) { Icon(RIcons.Close, "Remove photo", tint = Color.White, modifier = Modifier.size(18.dp)) }
                    }
                }

                vm.error?.let {
                    Text(it, fontSize = 13.sp, color = Color(0xFFB3261E), modifier = Modifier.padding(top = 8.dp))
                }

                Text(
                    "Output size",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = RColors.Ink2,
                    modifier = Modifier.padding(top = 20.dp),
                )
                Row(
                    Modifier.padding(top = 8.dp, bottom = 16.dp).fillMaxWidth().selectableGroup(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    OutputRatio.entries.forEach { r ->
                        val on = vm.ratio == r
                        Column(
                            Modifier
                                .weight(1f)
                                .height(56.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(if (on) RColors.BrandTint else Color.White)
                                .border(if (on) 2.dp else 1.dp, if (on) RColors.Brand else RColors.Border, RoundedCornerShape(12.dp))
                                .selectable(selected = on, role = Role.RadioButton, onClick = { vm.ratio = r }),
                            verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            val c = if (on) RColors.BrandDark else RColors.Ink
                            Text(r.label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = c)
                            Text(r.hint, fontSize = 11.sp, color = c.copy(alpha = 0.8f))
                        }
                    }
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(bottom = 12.dp).heightIn(min = 20.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Balance: ${creditsLabel(vm.credits)}", fontSize = 13.sp, color = RColors.Muted)
                if (vm.canAfford) {
                    Text(
                        "After this: ${creditsLabel(vm.credits - t.credits)}",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = RColors.Ink2,
                    )
                } else {
                    TextButton(onClick = onGetCredits, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp)) {
                        Text("Get credits", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
                    }
                }
            }
            if (vm.canAfford) {
                PrimaryButton(
                    text = "Generate · ${creditsLabel(t.credits)}",
                    onClick = { vm.generate(onGenerated) },
                    enabled = vm.photo != null,
                    icon = RIcons.Sparkle,
                )
            } else {
                PrimaryButton(text = "Subscribe to generate", onClick = onGetCredits, icon = RIcons.Sparkle)
            }
        }

        if (vm.generating) GeneratingOverlay(t.name)
    }
}

@Composable
private fun GeneratingOverlay(styleName: String) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0xE614151A))
            .then(Modifier.clickableNoRipple()),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
            CircularProgressIndicator(color = Color.White, strokeWidth = 3.dp, modifier = Modifier.size(48.dp))
            Text("Applying $styleName…", fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
            Text("This usually takes a few seconds.", fontSize = 13.sp, color = Color.White.copy(alpha = 0.75f))
        }
    }
}

/** Swallows touches so the screen underneath can't be used during generation. */
@Composable
private fun Modifier.clickableNoRipple(): Modifier {
    val source = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
    return this.then(Modifier.selectable(selected = false, interactionSource = source, indication = null, onClick = {}))
}

// ---------------------------------------------------------------- 05 Result

@Composable
fun ResultScreen(
    vm: AppViewModel,
    onClose: () -> Unit,
    onRegenerate: () -> Unit,
    onTryStyle: (String) -> Unit,
    onSeeAll: () -> Unit,
) {
    val context = LocalContext.current
    val c = vm.current
    if (c == null) {
        androidx.compose.runtime.LaunchedEffect(Unit) { onClose() }
        return
    }
    val t = Templates.byId(c.templateId) ?: Templates.trending
    var showAfter by rememberSaveable { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }
    val others = Templates.all.filter { it.id != t.id }.take(4)

    Column(
        Modifier.fillMaxSize().background(Color.White).safeDrawingPadding().padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 16.dp),
    ) {
        Row(
            Modifier.fillMaxWidth().offset(x = 0.dp).padding(horizontal = 0.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            NavIconButton(RIcons.Close, "Close", onClose, Modifier.offset(x = (-12).dp))
            Text(
                "Your creation",
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.weight(1f),
            )
            NavIconButton(RIcons.Refresh, "Regenerate", onRegenerate, Modifier.offset(x = 12.dp))
        }

        // Before / After toggle
        Row(
            Modifier
                .padding(top = 8.dp)
                .align(Alignment.CenterHorizontally)
                .width(220.dp)
                .background(RColors.Field, RoundedCornerShape(22.dp))
                .padding(4.dp)
                .selectableGroup(),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            listOf("Before" to false, "After" to true).forEach { (label, after) ->
                val on = showAfter == after
                Surface(
                    shape = RoundedCornerShape(18.dp),
                    color = if (on) Color.White else Color.Transparent,
                    shadowElevation = if (on) 1.dp else 0.dp,
                    modifier = Modifier
                        .weight(1f)
                        .height(36.dp)
                        .selectable(selected = on, role = Role.Tab, onClick = { showAfter = after }),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (on) RColors.Ink else RColors.Muted)
                    }
                }
            }
        }

        // Image
        Box(
            Modifier.padding(top = 16.dp).fillMaxWidth().weight(1f).heightIn(min = 240.dp),
            contentAlignment = Alignment.Center,
        ) {
            val bmp = if (showAfter) vm.currentResult else vm.currentOriginal
            Box(
                Modifier
                    .aspectRatio(c.ratio.w.toFloat() / c.ratio.h, matchHeightConstraintsFirst = true)
                    .clip(RoundedCornerShape(24.dp))
                    .background(if (showAfter) t.color else RColors.Placeholder),
                contentAlignment = Alignment.Center,
            ) {
                if (bmp != null) {
                    Image(
                        bmp.asImageBitmap(),
                        contentDescription = if (showAfter) "${t.name} result" else "Your original photo",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize(),
                    )
                } else {
                    CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(28.dp))
                }
                if (showAfter) {
                    Surface(
                        color = RColors.Ink,
                        shape = RoundedCornerShape(50),
                        modifier = Modifier.align(Alignment.BottomStart).padding(14.dp).height(28.dp),
                    ) {
                        Box(Modifier.padding(horizontal = 10.dp), contentAlignment = Alignment.Center) {
                            Text("${t.name} · ${c.ratio.label}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
                        }
                    }
                }
            }
        }

        Text(
            "${creditsLabel(t.credits)} used · ${creditsLabel(vm.credits)} left",
            fontSize = 13.sp,
            color = RColors.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )
        Row(Modifier.padding(top = 14.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SecondaryButton(
                if (saving) "Saving…" else "Save",
                onClick = {
                    if (saving) return@SecondaryButton
                    saving = true
                    vm.saveCurrent { ok ->
                        saving = false
                        Toast.makeText(
                            context,
                            if (ok) "Saved to Pictures/Restyle" else "Couldn't save the image",
                            Toast.LENGTH_SHORT,
                        ).show()
                    }
                },
                icon = RIcons.Download,
                modifier = Modifier.weight(1f),
            )
            PrimaryButton(
                "Share",
                onClick = { vm.shareIntent()?.let(context::startActivity) },
                icon = RIcons.Share,
                modifier = Modifier.weight(1f),
            )
        }

        Row(Modifier.padding(top = 20.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Try another style", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(onClick = onSeeAll) {
                Text("See all", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            others.forEach { o ->
                Surface(
                    onClick = { onTryStyle(o.id) },
                    shape = RoundedCornerShape(14.dp),
                    color = o.color,
                    modifier = Modifier.weight(1f).aspectRatio(1f),
                ) {
                    Box(Modifier.padding(6.dp), contentAlignment = Alignment.BottomStart) {
                        Text(o.name, fontSize = 10.sp, lineHeight = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
                    }
                }
            }
        }
        Spacer(Modifier.height(4.dp))
    }
}
