package com.remindrx.app.navigation

import android.net.Uri
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FabPosition
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import com.remindrx.app.ui.AssistantViewModel
import com.remindrx.app.ui.PatientViewModel
import com.remindrx.app.ui.screens.ChangePinScreen
import com.remindrx.app.ui.screens.AssistantScreen
import com.remindrx.app.ui.screens.ChatHistoryScreen
import com.remindrx.app.ui.screens.DashboardScreen
import com.remindrx.app.ui.screens.LoginScreen
import com.remindrx.app.ui.screens.MedicationDetailScreen
import com.remindrx.app.ui.screens.OnboardingScreen
import com.remindrx.app.ui.screens.PrescriptionScreen
import com.remindrx.app.ui.screens.ReminderScreen
import com.remindrx.app.ui.screens.SettingsScreen
import com.remindrx.app.ui.screens.SosScreen
import com.remindrx.app.ui.screens.SurveyScreen
import kotlinx.coroutines.launch

private object Routes {
    const val LOGIN = "login"
    const val CHANGE_PIN = "change-pin"
    const val ONBOARDING = "onboarding"
    const val DASHBOARD = "dashboard"
    const val PRESCRIPTION = "prescription"
    const val MEDICATION_DETAIL = "medication/{medicationName}"
    const val ASSISTANT = "assistant"
    const val CHAT_HISTORY = "assistant/history"
    const val SURVEY = "survey"
    const val SETTINGS = "settings"
    const val SETTINGS_CHANGE_PIN = "settings/change-pin"
    const val SOS = "sos"
    const val REMINDER = "reminder/{doseId}"

    fun reminder(doseId: String) = "reminder/$doseId"
    fun medicationDetail(name: String) = "medication/${Uri.encode(name)}"
}

private val BOTTOM_BAR_ROUTES = setOf(
    Routes.DASHBOARD,
    Routes.PRESCRIPTION,
    Routes.ASSISTANT,
    Routes.SURVEY,
    Routes.SETTINGS,
)

@Composable
fun RemindRxApp() {
    val navController = rememberNavController()
    val authViewModel: AuthViewModel = hiltViewModel()
    val authState by authViewModel.state.collectAsStateWithLifecycle()
    val assistantViewModel: AssistantViewModel = hiltViewModel()
    val assistantState by assistantViewModel.state.collectAsStateWithLifecycle()
    val patientViewModel: PatientViewModel = hiltViewModel()
    val patientState by patientViewModel.state.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val coroutineScope = rememberCoroutineScope()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomChrome = currentRoute != null && currentRoute in BOTTOM_BAR_ROUTES
    val showSosFab = showBottomChrome && currentRoute != Routes.ASSISTANT

    LaunchedEffect(patientState.message) {
        patientState.message?.let { message ->
            snackbarHostState.showSnackbar(message)
            patientViewModel.clearMessage()
        }
    }

    LaunchedEffect(patientState.doses) {
        assistantViewModel.updateScheduleContext(patientState.doses)
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            if (showBottomChrome && currentRoute != Routes.ASSISTANT) {
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
            if (showSosFab) {
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
            composable(Routes.PRESCRIPTION) {
                PrescriptionScreen(
                    medications = patientState.medications,
                    onOpenMedication = { medication ->
                        navController.navigate(Routes.medicationDetail(medication.name))
                    },
                )
            }
            composable(
                Routes.MEDICATION_DETAIL,
                arguments = listOf(navArgument("medicationName") { type = NavType.StringType }),
            ) { entry ->
                val medicationName = Uri.decode(entry.arguments?.getString("medicationName").orEmpty())
                MedicationDetailScreen(
                    medication = patientState.medications.firstOrNull { it.name == medicationName },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.ASSISTANT) {
                AssistantScreen(
                    state = assistantState,
                    onSend = assistantViewModel::sendMessage,
                    onNewChat = assistantViewModel::startNewConversation,
                    onOpenHistory = { navController.navigate(Routes.CHAT_HISTORY) },
                    onStartRecording = assistantViewModel::startRecording,
                    onStopRecordingAndSend = assistantViewModel::stopRecordingAndSend,
                )
            }
            composable(Routes.CHAT_HISTORY) {
                ChatHistoryScreen(
                    conversations = assistantState.conversations,
                    onBack = { navController.popBackStack() },
                    onNewChat = {
                        assistantViewModel.startNewConversation()
                        navController.popBackStack(Routes.ASSISTANT, inclusive = false)
                    },
                    onOpenConversation = { conversationId ->
                        assistantViewModel.openConversation(conversationId)
                        navController.popBackStack(Routes.ASSISTANT, inclusive = false)
                    },
                )
            }
            composable(Routes.SURVEY) {
                SurveyScreen(onSubmit = patientViewModel::submitSurvey)
            }
            composable(Routes.SETTINGS) {
                SettingsScreen(
                    routine = patientState.routine,
                    isSavingRoutine = patientState.isSavingRoutine,
                    routineError = patientState.routineError,
                    onRoutineInputChanged = patientViewModel::clearRoutineError,
                    onSaveRoutine = patientViewModel::saveRoutine,
                    onChangePin = {
                        authViewModel.clearError()
                        navController.navigate(Routes.SETTINGS_CHANGE_PIN)
                    },
                )
            }
            composable(Routes.SETTINGS_CHANGE_PIN) {
                ChangePinScreen(
                    isLoading = authState.isLoading,
                    error = authState.error,
                    isRequired = false,
                    onInputChanged = authViewModel::clearError,
                    onChangePin = { newPin, confirmedPin ->
                        authViewModel.changePin(newPin, confirmedPin) {
                            navController.popBackStack()
                            coroutineScope.launch {
                                snackbarHostState.showSnackbar("Đã đổi mã PIN")
                            }
                        }
                    },
                )
            }
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
