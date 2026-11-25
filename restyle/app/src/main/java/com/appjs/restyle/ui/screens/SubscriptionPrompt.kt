package com.appjs.restyle.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
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
import com.appjs.restyle.data.creditsLabel
import com.appjs.restyle.ui.components.Pill
import com.appjs.restyle.ui.components.PrimaryButton
import com.appjs.restyle.ui.components.SecondaryButton
import com.appjs.restyle.ui.theme.RColors
import com.appjs.restyle.ui.theme.RIcons
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Wording shared with the web app (restyle-web/src/lib/subscription.ts). */
private object PromptText {
    const val TITLE = "Set up your subscription"
    const val TRIAL_LEAD = "Start with a free trial. Pick monthly or yearly."
    const val PAID_LEAD = "Subscribe to get fresh credits every month."
    const val START_TRIAL = "Start free trial"
    const val LATER = "Maybe later"
    const val CLOSE = "Close"
    const val TRIAL_STARTED = "Your free trial is on"
    const val START_CREATING = "Start creating"
    fun trialLine(p: Plan) = "${p.trialDays}-day free trial · ${p.trialCredits} credits"
    fun trialNote(p: Plan) = "No payment needed. The trial ends after ${p.trialDays} days; your credits stay."
    fun subscribe(p: Plan) = "Subscribe · ${p.price}/${p.period}"
}

private fun periodLabel(period: String) = if (period == "year") "Yearly" else "Monthly"

/** Monthly / Yearly in the plans' order; with a trial on offer, only periods that have a trial plan. */
private fun periods(plans: List<Plan>, trial: Boolean) =
    plans.filter { !trial || it.trialEnabled }.map { it.period }.distinct()

/** The plan shown for a period: with a trial on offer one that has it; the badged one, else the first. */
private fun planFor(plans: List<Plan>, period: String?, trial: Boolean): Plan? {
    val ofPeriod = plans.filter { it.period == period && (!trial || it.trialEnabled) }
    return ofPeriod.firstOrNull { it.badge != null } ?: ofPeriod.firstOrNull()
}

private fun shortDate(iso: String?): String = runCatching {
    OffsetDateTime.parse(iso).format(DateTimeFormatter.ofPattern("d MMM", Locale.forLanguageTag("en-IN")))
}.getOrDefault("")

/**
 * Shown after sign-in while the user has no subscription: a free trial (Monthly / Yearly) when one is
 * on offer, else the plans. "Maybe later" hides it until the next launch or sign-in.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SubscriptionPrompt(vm: AppViewModel) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val trial = vm.trialOffered
    val options = periods(vm.plans, trial)
    var period by rememberSaveable { mutableStateOf<String?>(null) }
    val chosenPeriod = period?.takeIf { it in options } ?: options.firstOrNull()
    val plan = planFor(vm.plans, chosenPeriod, trial)

    ModalBottomSheet(
        onDismissRequest = vm::dismissSubscriptionPrompt,
        sheetState = sheet,
        containerColor = Color.White,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (vm.trialJustStarted) {
                Text(PromptText.TRIAL_STARTED, style = MaterialTheme.typography.headlineSmall)
                Text(
                    "You have ${creditsLabel(vm.credits)}. Your trial ends on ${shortDate(vm.periodEnd)}.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = RColors.Muted,
                )
                PrimaryButton(PromptText.START_CREATING, vm::dismissSubscriptionPrompt, Modifier.fillMaxWidth())
                return@Column
            }

            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(PromptText.TITLE, style = MaterialTheme.typography.headlineSmall)
                Text(
                    if (trial) PromptText.TRIAL_LEAD else PromptText.PAID_LEAD,
                    style = MaterialTheme.typography.bodyLarge,
                    color = RColors.Muted,
                )
            }

            if (options.size > 1) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(RColors.Field, RoundedCornerShape(14.dp))
                        .padding(4.dp)
                        .selectableGroup(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    options.forEach { p ->
                        val on = p == chosenPeriod
                        Box(
                            Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(10.dp))
                                .background(if (on) Color.White else Color.Transparent)
                                .selectable(selected = on, role = Role.RadioButton, onClick = {
                                    period = p
                                    vm.clearError()
                                })
                                .padding(vertical = 10.dp),
                            contentAlignment = Alignment.Center,
                        ) { Text(periodLabel(p), fontWeight = FontWeight.SemiBold, fontSize = 15.sp) }
                    }
                }
            }

            plan?.let { p ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(RColors.BrandTint)
                        .border(2.dp, RColors.Brand, RoundedCornerShape(18.dp))
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Row(
                            Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(p.title, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                            p.badge?.let { Pill(it, RColors.Ink, Color.White, height = 22.dp, fontSize = 11) }
                        }
                        Text(p.price, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text("/${p.period}", fontSize = 13.sp, color = RColors.Muted)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Icon(RIcons.Sparkles, null, tint = RColors.Muted, modifier = Modifier.size(13.dp))
                        Text("${p.creditsPerMonth} credits every month", fontSize = 13.sp, color = RColors.Muted)
                    }
                    if (trial) {
                        Text(PromptText.trialLine(p), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = RColors.Brand)
                    }
                }
            }

            vm.error?.let {
                Text(
                    it,
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    color = RColors.Ink2,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(RColors.BrandTint, RoundedCornerShape(14.dp))
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                )
            }

            plan?.let { p ->
                if (trial) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        PrimaryButton(PromptText.START_TRIAL, { vm.startTrial(p) }, Modifier.fillMaxWidth(), loading = vm.busy)
                        Text(
                            PromptText.trialNote(p),
                            fontSize = 12.sp,
                            lineHeight = 18.sp,
                            color = RColors.Muted,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    SecondaryButton(PromptText.subscribe(p), { vm.paymentsComingSoon(p) }, Modifier.fillMaxWidth())
                } else {
                    PrimaryButton(PromptText.subscribe(p), { vm.paymentsComingSoon(p) }, Modifier.fillMaxWidth())
                }
            }
            TextButton(onClick = vm::dismissSubscriptionPrompt, modifier = Modifier.fillMaxWidth()) {
                Text(
                    if (vm.error != null) PromptText.CLOSE else PromptText.LATER,
                    color = RColors.Brand,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 15.sp,
                )
            }
        }
    }
}
