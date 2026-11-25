package com.appjs.restyle

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavType
import androidx.navigation.navArgument
import com.appjs.restyle.data.Templates
import com.appjs.restyle.ui.screens.SubscribeScreen
import com.appjs.restyle.ui.screens.SubscriptionPrompt
import com.appjs.restyle.ui.screens.HomeScreen
import com.appjs.restyle.ui.screens.HomeTab
import com.appjs.restyle.ui.screens.LoginScreen
import com.appjs.restyle.ui.screens.OtpScreen
import com.appjs.restyle.ui.screens.ResultScreen
import com.appjs.restyle.ui.screens.UploadScreen
import com.appjs.restyle.ui.theme.RestyleTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent { RestyleTheme { RestyleApp() } }
    }
}

private object Routes {
    const val Login = "login"
    const val Otp = "otp"
    const val Home = "home"
    const val Upload = "upload"
    const val Result = "result"
    const val Subscribe = "subscribe?for={for}"
    fun subscribe(forTemplateId: String? = null) = if (forTemplateId == null) "subscribe" else "subscribe?for=$forTemplateId"
}

@Composable
fun RestyleApp(vm: AppViewModel = viewModel()) {
    val nav = rememberNavController()
    var homeTab by rememberSaveable { mutableStateOf(HomeTab.Templates) }

    fun NavHostController.toHome() = navigate(Routes.Home) {
        popUpTo(Routes.Home) { inclusive = true }
        launchSingleTop = true
    }

    // Balance, plan and styles can change on the server (e.g. an admin gives a plan): reload on resume.
    LifecycleResumeEffect(Unit) {
        vm.refresh()
        onPauseOrDispose { }
    }
    // The session ended (expired, blocked, signed out elsewhere): back to sign-in.
    LaunchedEffect(vm.isLoggedIn) {
        val route = nav.currentDestination?.route
        if (!vm.isLoggedIn && route != null && route != Routes.Login && route != Routes.Otp) {
            nav.navigate(Routes.Login) { popUpTo(0) { inclusive = true } }
        }
    }

    // After sign-in, while there's no subscription: offer the free trial or the plans (over Home).
    val route = nav.currentBackStackEntryAsState().value?.destination?.route
    if (route == Routes.Home && vm.showSubscriptionPrompt) SubscriptionPrompt(vm)

    NavHost(nav, startDestination = if (vm.isLoggedIn) Routes.Home else Routes.Login) {
        composable(Routes.Login) {
            LoginScreen(
                vm,
                onSignedIn = {
                    homeTab = HomeTab.Templates
                    nav.navigate(Routes.Home) { popUpTo(Routes.Login) { inclusive = true } }
                },
                onOtpSent = { nav.navigate(Routes.Otp) },
            )
        }
        composable(Routes.Otp) {
            OtpScreen(
                vm,
                onBack = { nav.popBackStack() },
                onVerified = {
                    homeTab = HomeTab.Templates
                    nav.navigate(Routes.Home) { popUpTo(Routes.Login) { inclusive = true } }
                },
            )
        }
        composable(Routes.Home) {
            HomeScreen(
                vm,
                tab = homeTab,
                onTabChange = { homeTab = it },
                onPickTemplate = {
                    vm.selectTemplate(it.id)
                    if (vm.credits < it.credits) nav.navigate(Routes.subscribe(it.id)) else nav.navigate(Routes.Upload)
                },
                onGetCredits = { nav.navigate(Routes.subscribe()) },
                onOpenCreation = {
                    vm.openCreation(it)
                    nav.navigate(Routes.Result)
                },
                onLogout = {
                    nav.navigate(Routes.Login) { popUpTo(0) { inclusive = true } }
                },
            )
        }
        composable(
            Routes.Subscribe,
            arguments = listOf(navArgument("for") { type = NavType.StringType; nullable = true; defaultValue = null }),
        ) { entry ->
            val forTemplate = Templates.byId(entry.arguments?.getString("for"))
            SubscribeScreen(
                vm,
                forTemplate = forTemplate,
                onClose = { nav.popBackStack() },
                onSubscribed = {
                    if (forTemplate != null && vm.credits >= forTemplate.credits) {
                        vm.selectTemplate(forTemplate.id)
                        nav.navigate(Routes.Upload) { popUpTo(Routes.Home) }
                    } else {
                        nav.popBackStack()
                    }
                },
            )
        }
        composable(Routes.Upload) {
            UploadScreen(
                vm,
                onBack = { if (!nav.popBackStack()) nav.toHome() },
                onChangeStyle = {
                    homeTab = HomeTab.Templates
                    if (!nav.popBackStack(Routes.Home, inclusive = false)) nav.toHome()
                },
                onGetCredits = { nav.navigate(Routes.subscribe(vm.templateId)) },
                onGenerated = {
                    nav.navigate(Routes.Result) { popUpTo(Routes.Home) }
                },
            )
        }
        composable(Routes.Result) {
            ResultScreen(
                vm,
                onClose = { if (!nav.popBackStack(Routes.Home, inclusive = false)) nav.toHome() },
                onRegenerate = {
                    vm.restyleCurrent()
                    nav.navigate(Routes.Upload) { popUpTo(Routes.Home) }
                },
                onTryStyle = { id ->
                    vm.restyleCurrent(id)
                    nav.navigate(Routes.Upload) { popUpTo(Routes.Home) }
                },
                onSeeAll = {
                    homeTab = HomeTab.Templates
                    if (!nav.popBackStack(Routes.Home, inclusive = false)) nav.toHome()
                },
            )
        }
    }
}
