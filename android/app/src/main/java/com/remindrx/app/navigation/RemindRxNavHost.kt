package com.remindrx.app.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FabPosition
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.remindrx.app.ui.components.RemindRxBottomBar
import com.remindrx.app.ui.components.SosFab
import com.remindrx.app.ui.AuthViewModel
import com.remindrx.app.ui.PatientViewModel
import com.remindrx.app.ui.screens.ChangePinScreen
import com.remindrx.app.ui.screens.DashboardScreen
import com.remindrx.app.ui.screens.LoginScreen
import com.remindrx.app.ui.screens.OnboardingScreen
import com.remindrx.app.ui.screens.PrescriptionScreen
import com.remindrx.app.ui.screens.ReminderScreen
import com.remindrx.app.ui.screens.SettingsScreen
import com.remindrx.app.ui.screens.SosScreen
import com.remindrx.app.ui.screens.SurveyScreen

private object Routes {
    const val LOGIN = "login"
    const val CHANGE_PIN = "change-pin"
    const val ONBOARDING = "onboarding"
    const val DASHBOARD = "dashboard"
    const val PRESCRIPTION = "prescription"
    const val SURVEY = "survey"
    const val SETTINGS = "settings"
    const val SOS = "sos"
    const val REMINDER = "reminder/{doseId}"

    fun reminder(doseId: String) = "reminder/$doseId"
}

private val BOTTOM_BAR_ROUTES = setOf(Routes.DASHBOARD, Routes.PRESCRIPTION, Routes.SURVEY, Routes.SETTINGS)

@Composable
fun RemindRxApp() {
    val navController = rememberNavController()
    val authViewModel: AuthViewModel = hiltViewModel()
    val authState by authViewModel.state.collectAsStateWithLifecycle()
    val patientViewModel: PatientViewModel = hiltViewModel()
    val patientState by patientViewModel.state.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomChrome = currentRoute != null && currentRoute in BOTTOM_BAR_ROUTES

    LaunchedEffect(patientState.message) {
        patientState.message?.let { message ->
            snackbarHostState.showSnackbar(message)
            patientViewModel.clearMessage()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            if (showBottomChrome) {
                RemindRxBottomBar(
                    currentRoute = currentRoute,
                    onNavigate = { route ->
                        navController.navigate(route) {
                            popUpTo(Routes.DASHBOARD) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                )
            }
        },
        floatingActionButton = {
            if (showBottomChrome) {
                SosFab(onClick = { navController.navigate(Routes.SOS) })
            }
        },
        floatingActionButtonPosition = FabPosition.End,
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Routes.LOGIN,
            modifier = Modifier.padding(padding),
        ) {
            composable(Routes.LOGIN) {
                LoginScreen(
                    isLoading = authState.isLoading,
                    error = authState.error,
                    onInputChanged = authViewModel::clearError,
                    onLogin = { phone, pin ->
                        authViewModel.login(phone, pin) { isFirstLogin ->
                            val destination = if (isFirstLogin) Routes.CHANGE_PIN else Routes.DASHBOARD
                            navController.navigate(destination) {
                                popUpTo(Routes.LOGIN) { inclusive = true }
                            }
                        }
                    },
                )
            }
            composable(Routes.CHANGE_PIN) {
                ChangePinScreen(
                    isLoading = authState.isLoading,
                    error = authState.error,
                    onInputChanged = authViewModel::clearError,
                    onChangePin = { newPin, confirmedPin ->
                        authViewModel.changePin(newPin, confirmedPin) {
                            navController.navigate(Routes.ONBOARDING) {
                                popUpTo(Routes.CHANGE_PIN) { inclusive = true }
                            }
                        }
                    },
                )
            }
            composable(Routes.ONBOARDING) {
                OnboardingScreen(
                    routine = patientState.routine,
                    isLoading = patientState.isLoading,
                    error = patientState.error,
                    onRetry = patientViewModel::refresh,
                    onDone = {
                        navController.navigate(Routes.DASHBOARD) { popUpTo(Routes.ONBOARDING) { inclusive = true } }
                    },
                )
            }
            composable(Routes.DASHBOARD) {
                DashboardScreen(
                    doses = patientState.doses,
                    adherenceRate = patientState.adherenceRate,
                    isLoading = patientState.isLoading,
                    error = patientState.error,
                    onRetry = patientViewModel::refresh,
                    onDoseAction = patientViewModel::recordDoseAction,
                    onOpenDose = { navController.navigate(Routes.reminder(it)) },
                )
            }
            composable(Routes.PRESCRIPTION) { PrescriptionScreen(medications = patientState.medications) }
            composable(Routes.SURVEY) {
                SurveyScreen(onSubmit = patientViewModel::submitSurvey)
            }
            composable(Routes.SETTINGS) { SettingsScreen() }
            composable(Routes.SOS) {
                SosScreen(
                    onTriggered = patientViewModel::createSos,
                    onCancel = { navController.popBackStack() },
                )
            }
            composable(
                Routes.REMINDER,
                arguments = listOf(navArgument("doseId") { type = NavType.StringType }),
            ) { entry ->
                val doseId = entry.arguments?.getString("doseId").orEmpty()
                ReminderScreen(
                    dose = patientState.doses.firstOrNull { it.id == doseId },
                    onAction = { id, action -> patientViewModel.recordDoseAction(id, action) },
                    onDone = { navController.popBackStack() },
                )
            }
        }
    }
}
