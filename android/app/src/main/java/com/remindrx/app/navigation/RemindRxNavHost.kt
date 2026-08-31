package com.remindrx.app.navigation

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FabPosition
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.remindrx.app.ui.components.RemindRxBottomBar
import com.remindrx.app.ui.components.OfflineBanner
import com.remindrx.app.ui.components.SosFab
import com.remindrx.app.ui.feature.auth.AuthViewModel
import com.remindrx.app.ui.feature.assistant.AssistantViewModel
import com.remindrx.app.ui.feature.patient.PatientViewModel
import com.remindrx.app.ui.feature.auth.ChangePinScreen
import com.remindrx.app.ui.feature.assistant.AssistantScreen
import com.remindrx.app.ui.feature.assistant.ChatHistoryScreen
import com.remindrx.app.ui.feature.patient.DashboardScreen
import com.remindrx.app.ui.feature.patient.AdherenceHistoryScreen
import com.remindrx.app.ui.feature.patient.AdherenceLogUi
import com.remindrx.app.ui.feature.patient.AdherenceSummaryUi
import com.remindrx.app.ui.feature.patient.CaregiverScreen
import com.remindrx.app.ui.feature.patient.CaregiverUi
import com.remindrx.app.ui.feature.auth.LoginScreen
import com.remindrx.app.ui.feature.patient.MedicationDetailScreen
import com.remindrx.app.ui.feature.patient.MedicationDetailUi
import com.remindrx.app.ui.feature.patient.OnboardingScreen
import com.remindrx.app.ui.feature.patient.PrescriptionScreen
import com.remindrx.app.ui.feature.patient.ReminderScreen
import com.remindrx.app.ui.feature.patient.SettingsScreen
import com.remindrx.app.ui.feature.patient.SosScreen
import com.remindrx.app.ui.feature.patient.SurveyScreen
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.launch

private object Routes {
    const val LOGIN = "login"
    const val SESSION_GATE = "session-gate"
    const val CHANGE_PIN = "change-pin"
    const val ONBOARDING = "onboarding"
    const val DASHBOARD = "dashboard"
    const val PRESCRIPTION = "prescription"
    const val MEDICATION_DETAIL = "medication/{prescriptionItemId}"
    const val ASSISTANT = "assistant"
    const val CHAT_HISTORY = "assistant/history"
    const val SURVEY = "survey"
    const val SETTINGS = "settings"
    const val CAREGIVERS = "settings/caregivers"
    const val ADHERENCE_HISTORY = "settings/adherence-history"
    const val SETTINGS_CHANGE_PIN = "settings/change-pin"
    const val SOS = "sos"
    const val REMINDER = "reminder/{doseId}"

    fun reminder(doseId: String) = "reminder/$doseId"
    fun medicationDetail(prescriptionItemId: String) =
        "medication/${Uri.encode(prescriptionItemId)}"
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
    val isOnline by patientViewModel.isOnline.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val coroutineScope = rememberCoroutineScope()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomChrome = currentRoute != null && currentRoute in BOTTOM_BAR_ROUTES
    val showSosFab = showBottomChrome && currentRoute != Routes.ASSISTANT

    LaunchedEffect(authState.session?.patientId) {
        val session = authState.session
        if (session == null) {
            patientViewModel.endSession()
            assistantViewModel.endSession()
        } else {
            patientViewModel.startSession(session.patientId)
            assistantViewModel.startSession(session.patientId)
        }
    }

    LaunchedEffect(
        authState.session?.patientId,
        authState.session?.mustChangePassword,
        authState.session?.needOnboarding,
        patientState.routineCheckCompleted,
        currentRoute,
    ) {
        if (currentRoute != Routes.SESSION_GATE) return@LaunchedEffect
        val destination = when {
            authState.session == null -> Routes.LOGIN
            authState.session?.mustChangePassword == true -> Routes.CHANGE_PIN
            authState.session?.needOnboarding == true -> Routes.ONBOARDING
            patientState.routineCheckCompleted -> Routes.DASHBOARD
            else -> null
        }
        destination?.let {
            navController.navigate(it) {
                popUpTo(Routes.SESSION_GATE) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    LaunchedEffect(authState.session, currentRoute) {
        if (authState.session == null && currentRoute != null && currentRoute != Routes.LOGIN) {
            navController.navigate(Routes.LOGIN) {
                popUpTo(navController.graph.id) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

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
        topBar = {
            if (showBottomChrome || currentRoute == Routes.SOS || currentRoute == Routes.REMINDER) {
                OfflineBanner(
                    isOnline = isOnline,
                    pendingSyncCount = patientState.pendingSyncCount,
                )
            }
        },
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
            startDestination = when {
                authState.session == null -> Routes.LOGIN
                else -> Routes.SESSION_GATE
            },
            modifier = Modifier.padding(padding),
        ) {
            composable(Routes.LOGIN) {
                LoginScreen(
                    isLoading = authState.isLoading,
                    error = authState.error,
                    shouldClearPin = authState.shouldClearLoginPin,
                    onInputChanged = authViewModel::clearError,
                    onPinCleared = authViewModel::consumeClearLoginPin,
                    onLogin = { phone, pin ->
                        authViewModel.login(phone, pin) { mustChangePassword ->
                            val destination = if (mustChangePassword) Routes.CHANGE_PIN else Routes.SESSION_GATE
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
                    onChangePin = { currentPin, newPin, confirmedPin ->
                        authViewModel.changePin(currentPin, newPin, confirmedPin) {
                            navController.navigate(Routes.SESSION_GATE) {
                                popUpTo(Routes.CHANGE_PIN) { inclusive = true }
                            }
                        }
                    },
                )
            }
            composable(Routes.ONBOARDING) {
                LaunchedEffect(patientState.routineSaveCompleted) {
                    if (patientState.routineSaveCompleted) {
                        patientViewModel.consumeRoutineSaveCompleted()
                        navController.navigate(Routes.DASHBOARD) {
                            popUpTo(Routes.ONBOARDING) { inclusive = true }
                        }
                    }
                }
                OnboardingScreen(
                    routine = patientState.routine,
                    isSaving = patientState.isSavingRoutine,
                    error = patientState.routineError ?: patientState.error,
                    onInputChanged = patientViewModel::clearRoutineError,
                    onSaveRoutine = patientViewModel::saveRoutine,
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
                        medication.prescriptionItemId?.let { itemId ->
                            navController.navigate(Routes.medicationDetail(itemId))
                        }
                    },
                    isRefreshing = patientState.isLoading,
                    onRefresh = patientViewModel::refresh,
                )
            }
            composable(
                Routes.MEDICATION_DETAIL,
                arguments = listOf(navArgument("prescriptionItemId") { type = NavType.StringType }),
            ) { entry ->
                val prescriptionItemId = Uri.decode(
                    entry.arguments?.getString("prescriptionItemId").orEmpty(),
                )
                val medication = patientState.medications.firstOrNull {
                    it.prescriptionItemId == prescriptionItemId
                }
                LaunchedEffect(medication?.medicationId) {
                    patientViewModel.loadMedicationDetail(medication?.medicationId)
                }
                MedicationDetailScreen(
                    medication = medication,
                    detail = patientState.medicationDetail?.toUi(),
                    isLoading = patientState.isLoadingMedicationDetail,
                    error = patientState.medicationDetailError,
                    onRetry = { patientViewModel.loadMedicationDetail(medication?.medicationId) },
                    onRefresh = {
                        patientViewModel.loadMedicationDetail(
                            medication?.medicationId,
                            forceRefresh = true,
                        )
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.ASSISTANT) {
                AssistantScreen(
                    state = assistantState,
                    onSend = assistantViewModel::sendMessage,
                    onOpenHistory = { navController.navigate(Routes.CHAT_HISTORY) },
                    onBack = { navController.popBackStack() },
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
                SurveyScreen(
                    isSubmitting = patientState.isSubmittingSurvey,
                    isSubmitted = patientState.isSurveySubmitted,
                    error = patientState.surveyError,
                    onInputChanged = patientViewModel::clearSurveyStatus,
                    onSubmit = patientViewModel::submitSurvey,
                )
            }
            composable(Routes.SESSION_GATE) {
                SessionGateScreen(
                    isLoading = patientState.isCheckingRoutine,
                    error = patientState.error,
                    onRetry = patientViewModel::retrySessionBootstrap,
                )
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
                    onOpenCaregivers = { navController.navigate(Routes.CAREGIVERS) },
                    onOpenAdherenceHistory = { navController.navigate(Routes.ADHERENCE_HISTORY) },
                    isLoggingOut = authState.isLoading,
                    onLogout = authViewModel::logout,
                )
            }
            composable(Routes.CAREGIVERS) {
                LaunchedEffect(Unit) { patientViewModel.loadCaregivers() }
                CaregiverScreen(
                    caregivers = patientState.caregivers.map { it.toUi() },
                    isLoading = patientState.isLoadingCaregivers,
                    isAdding = patientState.isAddingCaregiver,
                    deletingLinkId = patientState.deletingCaregiverId,
                    error = patientState.caregiverError,
                    createdTemporaryPin = patientState.createdCaregiverTemporaryPin,
                    onBack = { navController.popBackStack() },
                    onRetry = patientViewModel::loadCaregivers,
                    onInputChanged = patientViewModel::clearCaregiverError,
                    onAdd = patientViewModel::addCaregiver,
                    onDelete = patientViewModel::deleteCaregiver,
                )
            }
            composable(Routes.ADHERENCE_HISTORY) {
                LaunchedEffect(Unit) { patientViewModel.loadAdherenceHistory() }
                AdherenceHistoryScreen(
                    summary = patientState.historySummary?.toUi(),
                    logs = patientState.historyLogs.map { it.toUi() },
                    isLoading = patientState.isLoadingHistory,
                    error = patientState.historyError,
                    hasMore = patientState.historyHasMore,
                    isLoadingMore = patientState.isLoadingMoreHistory,
                    canGoNextWeek = patientState.historyWeekStart < java.time.LocalDate.now()
                        .with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY)),
                    onBack = { navController.popBackStack() },
                    onRetry = { patientViewModel.loadAdherenceHistory() },
                    onPreviousWeek = patientViewModel::previousAdherenceWeek,
                    onNextWeek = patientViewModel::nextAdherenceWeek,
                    onLoadMore = patientViewModel::loadMoreAdherenceHistory,
                )
            }
            composable(Routes.SETTINGS_CHANGE_PIN) {
                ChangePinScreen(
                    isLoading = authState.isLoading,
                    error = authState.error,
                    isRequired = false,
                    onInputChanged = authViewModel::clearError,
                    onChangePin = { currentPin, newPin, confirmedPin ->
                        authViewModel.changePin(currentPin, newPin, confirmedPin) {
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
                    sosStatus = patientState.sosStatus,
                    error = patientState.sosError,
                    onTriggered = patientViewModel::createSos,
                    onCancel = {
                        patientViewModel.clearSosStatus()
                        navController.popBackStack()
                    },
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

private fun com.remindrx.app.data.MedicationDetail.toUi() = MedicationDetailUi(
    id = id,
    name = name,
    composition = composition,
    manufacturer = manufacturer,
    uses = uses,
    sideEffects = sideEffects,
    imageUrl = imageUrl,
    sourceName = sourceName,
    isActive = isActive,
)

private fun com.remindrx.app.data.CaregiverLink.toUi() = CaregiverUi(
    linkId = id,
    relationship = relationship,
    phone = caregiverPhone,
    status = status,
    channels = channels,
)

private fun com.remindrx.app.data.AdherenceSummary.toUi() = AdherenceSummaryUi(
    fromDateLabel = fromDate.format(DateTimeFormatter.ofPattern("dd/MM/yyyy")),
    toDateLabel = toDate.format(DateTimeFormatter.ofPattern("dd/MM/yyyy")),
    adherenceRate = adherenceRate,
    totalDoses = totalDoses,
    takenDoses = takenDoses,
    skippedDoses = skippedDoses,
    missedDoses = missedDoses,
)

private fun com.remindrx.app.data.AdherenceLog.toUi() = AdherenceLogUi(
    id = id,
    action = action,
    performedAtLabel = runCatching {
        OffsetDateTime.parse(performedAt)
            .atZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"))
            .format(DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm"))
    }.getOrDefault(performedAt),
    takenLate = payload["taken_late"] == true,
    note = payload["note"] as? String,
)

@Composable
private fun SessionGateScreen(
    isLoading: Boolean,
    error: String?,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (isLoading || error == null) {
            CircularProgressIndicator()
            Text("Đang kiểm tra thói quen sinh hoạt…", modifier = Modifier.padding(top = 16.dp))
        } else {
            Text(error)
            Button(onClick = onRetry, modifier = Modifier.padding(top = 16.dp)) {
                Text("Thử lại")
            }
        }
    }
}
