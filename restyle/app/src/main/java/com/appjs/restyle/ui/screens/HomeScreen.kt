package com.appjs.restyle.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.layout
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.appjs.restyle.AppViewModel
import com.appjs.restyle.data.Creation
import com.appjs.restyle.data.StyleTemplate
import com.appjs.restyle.data.Templates
import com.appjs.restyle.data.creditsLabel
import com.appjs.restyle.ui.components.CreditsChip
import com.appjs.restyle.ui.components.HillsArt
import com.appjs.restyle.ui.components.Pill
import com.appjs.restyle.ui.components.PrimaryButton
import com.appjs.restyle.ui.components.SecondaryButton
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.DateFormat
import java.util.Calendar
import java.util.Date

enum class HomeTab(val label: String) { Templates("Templates"), Creations("My creations"), Profile("Profile") }

@Composable
fun HomeScreen(
    vm: AppViewModel,
    tab: HomeTab,
    onTabChange: (HomeTab) -> Unit,
    onPickTemplate: (StyleTemplate) -> Unit,
    onOpenCreation: (Creation) -> Unit,
    onGetCredits: () -> Unit,
    onLogout: () -> Unit,
) {
    Scaffold(
        containerColor = Color.White,
        bottomBar = {
            Column {
                Box(Modifier.fillMaxWidth().height(1.dp).background(RColors.Divider))
                NavigationBar(containerColor = Color.White, tonalElevation = 0.dp) {
                    HomeTab.entries.forEach { t ->
                        val icon = when (t) {
                            HomeTab.Templates -> RIcons.Grid
                            HomeTab.Creations -> RIcons.Image
                            HomeTab.Profile -> RIcons.Person
                        }
                        NavigationBarItem(
                            selected = tab == t,
                            onClick = { onTabChange(t) },
                            icon = { Icon(icon, null, modifier = Modifier.size(22.dp)) },
                            label = {
                                Text(
                                    t.label,
                                    fontSize = 12.sp,
                                    fontWeight = if (tab == t) FontWeight.SemiBold else FontWeight.Medium,
                                )
                            },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = RColors.BrandDark,
                                selectedTextColor = RColors.BrandDark,
                                indicatorColor = RColors.BrandSoft,
                                unselectedIconColor = RColors.Muted,
                                unselectedTextColor = RColors.Muted,
                            ),
                        )
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            when (tab) {
                HomeTab.Templates -> TemplatesTab(vm, onPickTemplate, onProfile = { onTabChange(HomeTab.Profile) }, onGetCredits = onGetCredits)
                HomeTab.Creations -> CreationsTab(vm, onOpenCreation, onBrowse = { onTabChange(HomeTab.Templates) })
                HomeTab.Profile -> ProfileTab(vm, onGetCredits, onLogout)
            }
        }
    }
}

// ---------------------------------------------------------------- 03 Templates

private fun greeting(): String = when (Calendar.getInstance().get(Calendar.HOUR_OF_DAY)) {
    in 5..11 -> "Good morning"
    in 12..16 -> "Good afternoon"
    else -> "Good evening"
}

@Composable
private fun TemplatesTab(vm: AppViewModel, onPick: (StyleTemplate) -> Unit, onProfile: () -> Unit, onGetCredits: () -> Unit) {
    var chip by rememberSaveable { mutableStateOf("All") }
    var query by rememberSaveable { mutableStateOf("") }
    val list = Templates.all.filter {
        (chip == "All" || it.category == chip) &&
            (query.isBlank() || it.name.contains(query.trim(), ignoreCase = true) || it.meta.contains(query.trim(), ignoreCase = true))
    }
    val trending = Templates.trending

    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 24.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        item(span = { GridItemSpan(2) }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(greeting(), fontSize = 13.sp, color = RColors.Muted)
                    Text("Pick a style", style = MaterialTheme.typography.headlineSmall)
                }
                CreditsChip(vm.credits, onClick = onGetCredits)
                Spacer(Modifier.width(8.dp))
                Surface(
                    onClick = onProfile,
                    shape = CircleShape,
                    color = RColors.BrandSoft,
                    contentColor = RColors.BrandDark,
                    modifier = Modifier.size(44.dp).semantics { contentDescription = "Profile" },
                ) {
                    Box(contentAlignment = Alignment.Center) { Avatar(vm.user?.initials, iconSize = 22.dp, fontSize = 15) }
                }
            }
        }

        item(span = { GridItemSpan(2) }) {
            Row(
                Modifier
                    .padding(top = 8.dp)
                    .fillMaxWidth()
                    .height(48.dp)
                    .background(RColors.Field, RoundedCornerShape(14.dp))
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(RIcons.Search, null, tint = RColors.Muted, modifier = Modifier.size(20.dp))
                BasicTextField(
                    value = query,
                    onValueChange = { query = it },
                    singleLine = true,
                    textStyle = MaterialTheme.typography.bodyLarge,
                    cursorBrush = SolidColor(RColors.Brand),
                    modifier = Modifier.weight(1f).semantics { contentDescription = "Search styles" },
                    decorationBox = { inner ->
                        Box(contentAlignment = Alignment.CenterStart) {
                            if (query.isEmpty()) Text("Search styles", fontSize = 15.sp, color = RColors.Muted)
                            inner()
                        }
                    },
                )
            }
        }

        item(span = { GridItemSpan(2) }) {
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(horizontal = 20.dp),
                modifier = Modifier.padding(horizontal = 0.dp).fillMaxWidth().layoutBleed(20.dp),
            ) {
                items(Templates.categories) { label ->
                    val on = chip == label
                    Surface(
                        onClick = { chip = label },
                        shape = RoundedCornerShape(50),
                        color = if (on) RColors.Ink else Color.White,
                        contentColor = if (on) Color.White else RColors.Ink2,
                        border = BorderStroke(1.dp, if (on) RColors.Ink else RColors.Border),
                        modifier = Modifier.height(40.dp),
                    ) {
                        Box(Modifier.padding(horizontal = 16.dp), contentAlignment = Alignment.Center) {
                            Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (on) Color.White else RColors.Ink2)
                        }
                    }
                }
            }
        }

        if (Templates.all.isEmpty()) {
            item(span = { GridItemSpan(2) }) {
                Column(Modifier.padding(vertical = 32.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        when {
                            vm.catalogLoading -> "Loading styles…"
                            vm.catalogError != null -> vm.catalogError!!
                            else -> "No styles yet. Check back soon."
                        },
                        fontSize = 14.sp,
                        color = RColors.Muted,
                    )
                    if (!vm.catalogLoading) SecondaryButton("Try again", { vm.refresh() }, height = 44.dp)
                }
            }
        } else if (chip == "All" && query.isBlank()) {
            item(span = { GridItemSpan(2) }) { TrendingCard(trending, onClick = { onPick(trending) }) }
        }

        item(span = { GridItemSpan(2) }) {
            Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.Bottom) {
                Text("All templates", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text("${list.size} styles", fontSize = 13.sp, color = RColors.Muted)
            }
        }

        if (list.isEmpty() && Templates.all.isNotEmpty()) {
            item(span = { GridItemSpan(2) }) {
                Text(
                    "No styles match \"${query.trim()}\".",
                    fontSize = 14.sp,
                    color = RColors.Muted,
                    modifier = Modifier.padding(vertical = 24.dp),
                )
            }
        }

        items(list, key = { it.id }) { t -> TemplateTile(t, onClick = { onPick(t) }) }
    }
}

/** Lets a row scroll edge-to-edge inside padded content. */
private fun Modifier.layoutBleed(bleed: androidx.compose.ui.unit.Dp) = layout { measurable, constraints ->
    val extra = bleed.roundToPx() * 2
    val placeable = measurable.measure(
        constraints.copy(minWidth = constraints.maxWidth + extra, maxWidth = constraints.maxWidth + extra),
    )
    layout(constraints.maxWidth, placeable.height) { placeable.place(-extra / 2, 0) }
}

@Composable
private fun TrendingCard(t: StyleTemplate, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(22.dp),
        color = t.color,
        modifier = Modifier.padding(top = 8.dp).fillMaxWidth().height(168.dp),
    ) {
        Box {
            HillsArt(Modifier.fillMaxSize(), sunRadiusFraction = 0.075f)
            Column(Modifier.fillMaxSize().padding(18.dp), verticalArrangement = Arrangement.SpaceBetween) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Pill("Trending", Color.White, t.color)
                    Pill(creditsLabel(t.credits), RColors.Ink, Color.White)
                }
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(t.name, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color.White, letterSpacing = (-0.3).sp)
                    Text(t.subtitle, fontSize = 13.sp, color = Color(0xFFE4EFE6))
                }
            }
        }
    }
}

@Composable
private fun TemplateTile(t: StyleTemplate, onClick: () -> Unit) {
    Column(
        Modifier.clip(RoundedCornerShape(18.dp)).clickable(onClick = onClick),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(4f / 5f).background(t.color, RoundedCornerShape(18.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(RIcons.ImageThin, null, tint = Color.White.copy(alpha = 0.55f), modifier = Modifier.size(56.dp))
            if (t.isNew) {
                Pill("New", Color.White, RColors.Ink, Modifier.align(Alignment.TopStart).padding(10.dp), height = 22.dp, fontSize = 11)
            }
            Pill(
                creditsLabel(t.credits), RColors.Ink, Color.White,
                Modifier.align(Alignment.TopEnd).padding(10.dp),
                icon = RIcons.Sparkle, height = 24.dp, fontSize = 11,
            )
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.padding(bottom = 4.dp)) {
            Text(t.name, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(t.meta, fontSize = 12.sp, color = RColors.Muted)
        }
    }
}

// ---------------------------------------------------------------- My creations

@Composable
private fun CreationsTab(vm: AppViewModel, onOpen: (Creation) -> Unit, onBrowse: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        Text("My creations", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 16.dp))
        if (vm.creations.isEmpty()) {
            Column(
                Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(Modifier.size(56.dp).background(RColors.BrandSoft, CircleShape), contentAlignment = Alignment.Center) {
                    Icon(RIcons.Image, null, tint = RColors.Brand, modifier = Modifier.size(26.dp))
                }
                Text("Nothing here yet", fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 16.dp))
                Text(
                    "Images you make will show up here.",
                    fontSize = 14.sp,
                    color = RColors.Muted,
                    modifier = Modifier.padding(top = 4.dp, bottom = 20.dp),
                )
                SecondaryButton("Browse styles", onBrowse, height = 48.dp)
            }
        } else {
            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                contentPadding = PaddingValues(top = 16.dp, bottom = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                items(vm.creations, key = { it.id }) { c -> CreationTile(c, onClick = { onOpen(c) }) }
            }
        }
    }
}

private val thumbCache = mutableStateMapOf<String, ImageBitmap>()

@Composable
private fun CreationTile(c: Creation, onClick: () -> Unit) {
    val t = Templates.byId(c.templateId)
    var thumb by remember(c.id) { mutableStateOf(thumbCache[c.id]) }
    LaunchedEffect(c.id) {
        if (thumb == null) {
            thumb = withContext(Dispatchers.IO) {
                val opts = android.graphics.BitmapFactory.Options().apply { inSampleSize = 4 }
                android.graphics.BitmapFactory.decodeFile(c.resultPath, opts)?.asImageBitmap()
            }?.also { thumbCache[c.id] = it }
        }
    }
    Column(
        Modifier.clip(RoundedCornerShape(18.dp)).clickable(onClick = onClick),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(4f / 5f).clip(RoundedCornerShape(18.dp)).background(t?.color ?: RColors.Placeholder),
        ) {
            thumb?.let { Image(it, contentDescription = t?.name, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize()) }
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.padding(bottom = 4.dp)) {
            Text(t?.name ?: "Creation", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(
                "${c.ratio.label} · " + DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(c.createdAt)),
                fontSize = 12.sp,
                color = RColors.Muted,
            )
        }
    }
}

// ---------------------------------------------------------------- Profile

@Composable
private fun ProfileTab(vm: AppViewModel, onGetCredits: () -> Unit, onLogout: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        Text("Profile", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 16.dp))

        Row(
            Modifier.padding(top = 20.dp).fillMaxWidth().background(RColors.Surface, RoundedCornerShape(18.dp)).padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            val user = vm.user
            Box(Modifier.size(52.dp).background(RColors.BrandSoft, CircleShape), contentAlignment = Alignment.Center) {
                Avatar(user?.initials, iconSize = 26.dp, fontSize = 18)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                when {
                    user?.email != null -> {
                        Text(user.name ?: "Google account", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                        Text(user.email, fontSize = 13.sp, color = RColors.Muted)
                        Text(
                            "Signed in with Google",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = RColors.BrandDark,
                        )
                    }
                    user?.phone != null -> {
                        Text("Mobile number", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = RColors.Muted)
                        Text("${vm.countryCode} ${vm.displayPhone(user.phone)}", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        Column(
            Modifier.padding(top = 12.dp).fillMaxWidth().background(RColors.BrandTint, RoundedCornerShape(18.dp)).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text("Balance", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = RColors.BrandDark)
            Text("${vm.credits} credits", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = RColors.Ink)
            Text(
                "${vm.creations.size} ${if (vm.creations.size == 1) "image" else "images"} made",
                fontSize = 13.sp,
                color = RColors.Ink2,
            )
            Spacer(Modifier.height(8.dp))
            vm.planName?.let { name ->
                Text(
                    "$name plan" + (vm.plan?.let { " · ${it.creditsPerMonth} credits/month" } ?: ""),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = RColors.BrandDark,
                )
            }
            PrimaryButton(if (vm.planName == null) "Subscribe for credits" else "Get more credits", onGetCredits, icon = RIcons.Plus)
        }

        Spacer(Modifier.weight(1f))
        SecondaryButton(
            "Log out",
            onClick = { vm.logout(context); onLogout() },
            icon = RIcons.Logout,
            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
        )
    }
}

/** Initials in the brand colour, or a person icon when there's no name. */
@Composable
private fun Avatar(initials: String?, iconSize: androidx.compose.ui.unit.Dp, fontSize: Int) {
    if (initials.isNullOrBlank()) {
        Icon(RIcons.Person, null, tint = RColors.BrandDark, modifier = Modifier.size(iconSize))
    } else {
        Text(initials, fontSize = fontSize.sp, fontWeight = FontWeight.Bold, color = RColors.BrandDark)
    }
}
