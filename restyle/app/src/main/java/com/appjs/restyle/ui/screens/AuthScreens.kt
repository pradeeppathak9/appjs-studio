package com.appjs.restyle.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.appjs.restyle.AppViewModel
import com.appjs.restyle.ui.components.NavIconButton
import com.appjs.restyle.ui.components.PrimaryButton
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons
import kotlinx.coroutines.delay

// ---------------------------------------------------------------- 01 Login

@Composable
fun LoginScreen(vm: AppViewModel, onSignedIn: () -> Unit, onOtpSent: () -> Unit) {
    val context = LocalContext.current
    var choosePhone by rememberSaveable { mutableStateOf(false) }
    // Google is offered only when the app has it on in AppJs Studio; otherwise straight to phone.
    val usePhone = choosePhone || !vm.googleEnabled
    LaunchedEffect(usePhone) { vm.clearError() }

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.White)
            .safeDrawingPadding()
            .imePadding()
            .padding(horizontal = 24.dp),
    ) {
        Column(
            Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(top = 24.dp),
        ) {
            StyleMosaic()

            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 36.dp)) {
                Box(
                    Modifier.size(36.dp).background(RColors.Brand, RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center,
                ) { Icon(RIcons.Sparkles, null, tint = Color.White, modifier = Modifier.size(20.dp)) }
                Spacer(Modifier.width(10.dp))
                Text("Restyle AI", fontSize = 18.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp)
            }

            Text(
                "Turn any photo into a styled post",
                style = MaterialTheme.typography.displaySmall,
                modifier = Modifier.padding(top = 20.dp),
            )
            Text(
                if (usePhone) "Log in with your mobile number." else "Sign in to keep your credits and creations.",
                style = MaterialTheme.typography.bodyLarge,
                color = RColors.Muted,
                modifier = Modifier.padding(top = 8.dp),
            )

            if (usePhone) {
                Text(
                    "Mobile number",
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = RColors.Ink2,
                    modifier = Modifier.padding(top = 28.dp),
                )
                PhoneField(
                    countryCode = vm.countryCode,
                    value = vm.phone,
                    onValueChange = vm::onPhoneChange,
                    onDone = { vm.sendOtp(onOtpSent) },
                    modifier = Modifier.padding(top = 8.dp),
                )
                Text(
                    "We'll send a 6-digit code by SMS.",
                    fontSize = 12.sp,
                    color = RColors.Muted,
                    modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
                )
            } else {
                vm.error?.let {
                    Text(it, fontSize = 13.sp, color = RColors.Error, modifier = Modifier.padding(top = 20.dp))
                }
                Spacer(Modifier.height(24.dp))
            }
        }

        if (usePhone) {
            // above the button, so it stays visible while the keyboard is open
            vm.error?.let {
                Text(it, fontSize = 13.sp, color = RColors.Error, modifier = Modifier.padding(bottom = 10.dp))
            }
            PrimaryButton(
                text = "Get OTP",
                onClick = { vm.sendOtp(onOtpSent) },
                enabled = vm.phone.length == 10,
                loading = vm.busy,
            )
            if (vm.googleEnabled) TextButton(
                onClick = { choosePhone = false },
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp).height(48.dp),
            ) { Text("Continue with Google instead", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark) }
        } else {
            GoogleButton(
                loading = vm.busy,
                onClick = { vm.signInWithGoogle(context, onSignedIn) },
            )
            TextButton(
                onClick = { choosePhone = true },
                enabled = !vm.busy,
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp).height(48.dp),
            ) { Text("Use phone number instead", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark) }
        }
        Text(
            buildAnnotatedString {
                append("By continuing you agree to our ")
                withStyle(SpanStyle(color = RColors.BrandDark)) { append("Terms") }
                append(" and ")
                withStyle(SpanStyle(color = RColors.BrandDark)) { append("Privacy Policy") }
                append(".")
            },
            fontSize = 12.sp,
            lineHeight = 18.sp,
            color = RColors.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 16.dp),
        )
    }
}

@Composable
private fun GoogleButton(loading: Boolean, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = !loading,
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.5.dp, RColors.Border),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White, contentColor = RColors.Ink),
        modifier = Modifier.fillMaxWidth().height(56.dp),
    ) {
        if (loading) {
            CircularProgressIndicator(color = RColors.Brand, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        } else {
            Image(rememberVectorPainter(GoogleLogo), contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(12.dp))
            Text("Continue with Google", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = RColors.Ink)
        }
    }
}

/** The multi-colour Google "G" used on sign-in buttons. */
private val GoogleLogo: ImageVector by lazy {
    fun ImageVector.Builder.fill(color: Long, d: String) =
        addPath(pathData = addPathNodes(d), fill = SolidColor(Color(color)))
    ImageVector.Builder("google", 20.dp, 20.dp, 48f, 48f)
        .fill(0xFF4285F4, "M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z")
        .fill(0xFF34A853, "M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z")
        .fill(0xFFFBBC05, "M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34C2.85 17.09 2 20.45 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z")
        .fill(0xFFEA4335, "M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z")
        .build()
}

@Composable
private fun StyleMosaic() {
    @Composable
    fun Tile(label: String, color: Color, modifier: Modifier) {
        Box(
            modifier.background(color, RoundedCornerShape(20.dp)).padding(12.dp),
            contentAlignment = Alignment.BottomStart,
        ) { Text(label, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold) }
    }
    Row(Modifier.fillMaxWidth().height(220.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Tile("Anime Watercolor", Color(0xFF2F4B3A), Modifier.weight(1f).fillMaxHeight())
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Tile("80s Retro", Color(0xFF3B1F5C), Modifier.fillMaxWidth().weight(1f))
            Tile("Oil Portrait", Color(0xFF7A3B1D), Modifier.fillMaxWidth().weight(1f))
        }
        Tile("Comic Pop", Color(0xFF1E3A5F), Modifier.weight(1f).fillMaxHeight())
    }
}

@Composable
private fun PhoneField(
    countryCode: String,
    value: String,
    onValueChange: (String) -> Unit,
    onDone: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val focus = remember { FocusRequester() }
    Row(
        modifier
            .fillMaxWidth()
            .height(56.dp)
            .border(1.5.dp, RColors.Brand, RoundedCornerShape(14.dp))
            .padding(1.5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            Modifier
                .fillMaxHeight()
                .background(RColors.Surface, RoundedCornerShape(topStart = 12.dp, bottomStart = 12.dp))
                .padding(start = 16.dp, end = 12.dp)
                .semantics { contentDescription = "Country code, India $countryCode" },
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(countryCode, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Icon(RIcons.ChevronDown, null, tint = RColors.Muted, modifier = Modifier.size(16.dp))
        }
        Box(Modifier.width(1.dp).fillMaxHeight().background(RColors.Divider))
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = androidx.compose.material3.MaterialTheme.typography.bodyLarge.copy(fontSize = 16.sp, letterSpacing = 0.5.sp),
            cursorBrush = SolidColor(RColors.Brand),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { onDone() }),
            modifier = Modifier
                .weight(1f)
                .padding(horizontal = 16.dp)
                .focusRequester(focus)
                .semantics { contentDescription = "Mobile number" },
            decorationBox = { inner ->
                Box(contentAlignment = Alignment.CenterStart) {
                    if (value.isEmpty()) Text("10-digit number", fontSize = 16.sp, color = RColors.Muted)
                    inner()
                }
            },
        )
    }
    LaunchedEffect(Unit) { focus.requestFocus() }
}

// ---------------------------------------------------------------- 02 Verify OTP

private const val RESEND_SECONDS = 30

@Composable
fun OtpScreen(vm: AppViewModel, onBack: () -> Unit, onVerified: () -> Unit) {
    var code by rememberSaveable { mutableStateOf("") }
    var secondsLeft by rememberSaveable { mutableIntStateOf(RESEND_SECONDS) }
    var resendKey by remember { mutableIntStateOf(0) }
    val focus = remember { FocusRequester() }

    LaunchedEffect(resendKey) {
        while (secondsLeft > 0) {
            delay(1000)
            secondsLeft--
        }
    }
    LaunchedEffect(Unit) {
        vm.clearError()
        focus.requestFocus()
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.White)
            .safeDrawingPadding()
            .imePadding()
            .padding(start = 24.dp, end = 24.dp, top = 8.dp, bottom = 16.dp),
    ) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            NavIconButton(RIcons.ArrowBack, "Back", onBack, Modifier.offset(x = (-12).dp))

            Text(
                "Enter the code",
                style = androidx.compose.material3.MaterialTheme.typography.displaySmall,
                modifier = Modifier.padding(top = 24.dp),
            )
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                Text(
                    "Sent to ${vm.countryCode} ${vm.formattedPhone} · ",
                    style = androidx.compose.material3.MaterialTheme.typography.bodyLarge,
                    color = RColors.Muted,
                )
                TextButton(onClick = onBack, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 4.dp)) {
                    Text("Change", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
                }
            }

            OtpBoxes(
                code = code,
                onChange = {
                    code = it
                    vm.clearError()
                    if (it.length == 6) vm.verifyOtp(it, onVerified)
                },
                isError = vm.error != null,
                focus = focus,
                modifier = Modifier.padding(top = 28.dp),
            )
            vm.error?.let {
                Text(it, fontSize = 13.sp, color = RColors.Error, modifier = Modifier.padding(top = 10.dp))
            }

            Row(
                Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Didn't get it?", fontSize = 14.sp, color = RColors.Muted)
                if (secondsLeft > 0) {
                    Text(
                        "Resend in 0:%02d".format(secondsLeft),
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = RColors.Muted,
                        modifier = Modifier.padding(vertical = 12.dp),
                    )
                } else {
                    TextButton(onClick = {
                        vm.sendOtp {}
                        code = ""
                        secondsLeft = RESEND_SECONDS
                        resendKey++
                    }) { Text("Resend code", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark) }
                }
            }

            Row(
                Modifier
                    .padding(top = 20.dp)
                    .fillMaxWidth()
                    .background(RColors.Surface, RoundedCornerShape(14.dp))
                    .padding(horizontal = 16.dp, vertical = 14.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Icon(RIcons.Phone, null, tint = RColors.Brand, modifier = Modifier.size(20.dp))
                Text(
                    "The code fills in automatically when the SMS arrives on this phone.",
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    color = RColors.Ink2,
                )
            }
        }

        PrimaryButton(
            text = "Verify & continue",
            onClick = { vm.verifyOtp(code, onVerified) },
            enabled = code.length == 6,
            loading = vm.busy,
        )
    }
}

@Composable
private fun OtpBoxes(
    code: String,
    onChange: (String) -> Unit,
    isError: Boolean,
    focus: FocusRequester,
    modifier: Modifier = Modifier,
) {
    BasicTextField(
        value = code,
        onValueChange = { v -> onChange(v.filter { it.isDigit() }.take(6)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
        cursorBrush = SolidColor(Color.Transparent),
        textStyle = androidx.compose.ui.text.TextStyle(color = Color.Transparent),
        modifier = modifier
            .fillMaxWidth()
            .focusRequester(focus)
            .semantics { contentDescription = "6-digit verification code" },
        decorationBox = {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                repeat(6) { i ->
                    val active = i == code.length || (i == 5 && code.length == 6)
                    val borderColor = when {
                        isError -> RColors.Error
                        active -> RColors.Brand
                        else -> RColors.BorderStrong
                    }
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = if (active && !isError) RColors.BrandTint else Color.White,
                        border = BorderStroke(if (active) 2.dp else 1.5.dp, borderColor),
                        modifier = Modifier.weight(1f).height(56.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(code.getOrNull(i)?.toString() ?: "", fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            }
        },
    )
}
