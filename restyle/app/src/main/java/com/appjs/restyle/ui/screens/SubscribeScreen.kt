package com.appjs.restyle.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.appjs.restyle.AppViewModel
import com.appjs.restyle.data.Plan
import com.appjs.restyle.data.StyleTemplate
import com.appjs.restyle.data.Templates
import com.appjs.restyle.data.creditsLabel
import com.appjs.restyle.ui.components.NavIconButton
import com.appjs.restyle.ui.components.Pill
import com.appjs.restyle.ui.components.PrimaryButton
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons

/**
 * Shown when the user taps a style they can't afford (or asks for credits).
 * [forTemplate] is the style that sent them here, if any.
 */
@Composable
fun SubscribeScreen(
    vm: AppViewModel,
    forTemplate: StyleTemplate?,
    onClose: () -> Unit,
    onSubscribed: () -> Unit,
) {
    var selectedSlug by rememberSaveable { mutableStateOf<String?>(null) }
    val selected: Plan? = vm.plans.firstOrNull { it.slug == selectedSlug }
        ?: vm.plans.firstOrNull { it.badge != null } ?: vm.plans.firstOrNull()
    LaunchedEffect(Unit) { vm.clearError() }

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.White)
            .safeDrawingPadding()
            .padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 16.dp),
    ) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            NavIconButton(RIcons.Close, "Close", onClose, Modifier.offset(x = (-12).dp))

            Box(
                Modifier.padding(top = 8.dp).size(56.dp).background(RColors.Brand, RoundedCornerShape(16.dp)),
                contentAlignment = Alignment.Center,
            ) { Icon(RIcons.Sparkles, null, tint = Color.White, modifier = Modifier.size(28.dp)) }

            Text(
                "Get credits to create",
                style = MaterialTheme.typography.displaySmall,
                modifier = Modifier.padding(top = 20.dp),
            )
            Text(
                if (forTemplate != null) {
                    "${forTemplate.name} uses ${creditsLabel(forTemplate.credits)} per image. " +
                        "You have ${creditsLabel(vm.credits)}."
                } else {
                    "You have ${creditsLabel(vm.credits)}. Subscribe to get fresh credits every month."
                },
                style = MaterialTheme.typography.bodyLarge,
                color = RColors.Muted,
                modifier = Modifier.padding(top = 8.dp),
            )

            Column(
                Modifier.padding(top = 24.dp).selectableGroup(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (vm.plans.isEmpty()) {
                    Text("No plans are on offer right now.", fontSize = 14.sp, color = RColors.Muted)
                }
                vm.plans.forEach { p -> PlanCard(p, selected = p == selected, onSelect = { selectedSlug = p.slug }) }
            }

            Column(Modifier.padding(top = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                selected?.let { Benefit("${it.creditsPerMonth} credits every month") }
                Benefit("All ${Templates.all.size} styles, plus new ones as they're added")
                Benefit("Cancel anytime")
            }
        }

        vm.error?.let {
            Text(
                it,
                fontSize = 13.sp,
                lineHeight = 19.sp,
                color = RColors.Error,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
            )
        }
        if (vm.planName != null) {
            Text(
                "You're on the ${vm.planName} plan.",
                fontSize = 12.sp,
                color = RColors.Muted,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
            )
        }
        PrimaryButton(
            text = selected?.let { "Subscribe · ${it.price}/${it.period}" } ?: "Subscribe",
            onClick = { selected?.let { vm.subscribe(it, onSubscribed) } },
            enabled = selected != null,
            loading = vm.busy,
        )
        Text(
            "Payments are coming soon. Renews automatically; cancel anytime.",
            fontSize = 12.sp,
            lineHeight = 18.sp,
            color = RColors.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )
    }
}

@Composable
private fun PlanCard(plan: Plan, selected: Boolean, onSelect: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(if (selected) RColors.BrandTint else Color.White)
            .border(if (selected) 2.dp else 1.dp, if (selected) RColors.Brand else RColors.Border, RoundedCornerShape(18.dp))
            .selectable(selected = selected, role = Role.RadioButton, onClick = onSelect)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        // Radio indicator
        Box(
            Modifier
                .size(22.dp)
                .border(2.dp, if (selected) RColors.Brand else RColors.BorderStrong, CircleShape)
                .padding(5.dp)
                .background(if (selected) RColors.Brand else Color.Transparent, CircleShape),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(plan.title, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                plan.badge?.let { Pill(it, RColors.Ink, Color.White, height = 22.dp, fontSize = 11) }
            }
            Text(plan.note, fontSize = 13.sp, color = RColors.Muted)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(plan.price, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text("/${plan.period}", fontSize = 12.sp, color = RColors.Muted)
        }
    }
}

@Composable
private fun Benefit(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(24.dp).background(RColors.BrandSoft, CircleShape), contentAlignment = Alignment.Center) {
            Icon(RIcons.Check, null, tint = RColors.BrandDark, modifier = Modifier.size(14.dp))
        }
        Text(text, fontSize = 15.sp, color = RColors.Ink2)
    }
}
