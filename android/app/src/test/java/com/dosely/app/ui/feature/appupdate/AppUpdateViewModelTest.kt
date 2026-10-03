package com.dosely.app.ui.feature.appupdate

import com.dosely.app.BuildConfig
import com.dosely.app.data.AppUpdateInfo
import com.dosely.app.data.repository.AppUpdateRepository
import com.dosely.app.testing.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AppUpdateViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `higher server version shows update banner once per session`() = runTest {
        val repository = FakeAppUpdateRepository(
            AppUpdateInfo(
                versionCode = BuildConfig.VERSION_CODE + 1,
                versionName = "1.5.0",
                downloadUrl = "https://example.test/downloads/dosely-demo.apk",
            ),
        )
        val viewModel = AppUpdateViewModel(repository)
        advanceUntilIdle()

        viewModel.checkForUpdate()
        advanceUntilIdle()

        assertEquals(1, repository.calls)
        assertEquals("1.5.0", viewModel.state.value.availableUpdate?.versionName)
    }

    @Test
    fun `equal or lower server versions do not show update banner`() = runTest {
        val equalViewModel = AppUpdateViewModel(
            FakeAppUpdateRepository(version(versionCode = BuildConfig.VERSION_CODE)),
        )
        val lowerViewModel = AppUpdateViewModel(
            FakeAppUpdateRepository(version(versionCode = BuildConfig.VERSION_CODE - 1)),
        )
        advanceUntilIdle()

        assertNull(equalViewModel.state.value.availableUpdate)
        assertNull(lowerViewModel.state.value.availableUpdate)
    }

    @Test
    fun `network failure is ignored without showing update banner`() = runTest {
        val viewModel = AppUpdateViewModel(FakeAppUpdateRepository(error = IllegalStateException("offline")))
        advanceUntilIdle()

        assertNull(viewModel.state.value.availableUpdate)
    }

    @Test
    fun `dismiss hides update banner for the current app session`() = runTest {
        val viewModel = AppUpdateViewModel(
            FakeAppUpdateRepository(version(versionCode = BuildConfig.VERSION_CODE + 1)),
        )
        advanceUntilIdle()

        viewModel.dismissUpdate()

        assertNull(viewModel.state.value.availableUpdate)
    }

    private fun version(versionCode: Int) = AppUpdateInfo(
        versionCode = versionCode,
        versionName = "1.5.0",
        downloadUrl = "https://example.test/downloads/dosely-demo.apk",
    )
}

private class FakeAppUpdateRepository(
    private val response: AppUpdateInfo? = null,
    private val error: Exception? = null,
) : AppUpdateRepository {
    var calls = 0

    override suspend fun getLatestVersion(): AppUpdateInfo {
        calls += 1
        error?.let { throw it }
        return checkNotNull(response)
    }
}
