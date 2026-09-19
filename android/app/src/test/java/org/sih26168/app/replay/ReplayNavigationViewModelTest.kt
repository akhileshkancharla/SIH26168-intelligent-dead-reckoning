package org.sih26168.app.replay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReplayNavigationViewModelTest {
    @Test
    fun initialState_isPausedAtReplayOriginWithUnavailableTelemetry() {
        val state = ReplayNavigationViewModel().uiState.value

        assertFalse(state.isReplaying)
        assertEquals(0L, state.currentTimestampNs)
        assertEquals(1f, state.speedMultiplier)
        assertFalse(state.isOutageActive)
        assertNull(state.position.northMeters)
        assertNull(state.position.eastMeters)
        assertNull(state.speedMetersPerSecond)
    }

    @Test
    fun playAndPause_updatePlaybackState() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.Play)
        assertTrue(viewModel.uiState.value.isReplaying)

        viewModel.onIntent(ReplayIntent.Pause)
        assertFalse(viewModel.uiState.value.isReplaying)
    }

    @Test
    fun step_advancesOneFixedIntervalOnlyWhilePaused() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.Step)
        assertEquals(
            ReplayNavigationViewModel.STEP_INTERVAL_NS,
            viewModel.uiState.value.currentTimestampNs,
        )

        viewModel.onIntent(ReplayIntent.Play)
        viewModel.onIntent(ReplayIntent.Step)
        assertEquals(
            ReplayNavigationViewModel.STEP_INTERVAL_NS,
            viewModel.uiState.value.currentTimestampNs,
        )
    }

    @Test
    fun speedMultiplier_acceptsOnlySupportedValues() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(2f))
        assertEquals(2f, viewModel.uiState.value.speedMultiplier)

        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(3f))
        assertEquals(2f, viewModel.uiState.value.speedMultiplier)
    }

    @Test
    fun simulatedOutage_toggleControlsDisclosureState() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        assertTrue(viewModel.uiState.value.isOutageActive)

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        assertFalse(viewModel.uiState.value.isOutageActive)
    }

    @Test
    fun telemetryPresentation_acceptsMonotonicFiniteValues() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(
            ReplayIntent.PresentTelemetry(
                timestampNs = 2_000_000_000L,
                northMeters = 12.5,
                eastMeters = -4.25,
                speedMetersPerSecond = 6.75,
            ),
        )

        val state = viewModel.uiState.value
        assertEquals(2_000_000_000L, state.currentTimestampNs)
        assertEquals(12.5, state.position.northMeters!!, 0.0)
        assertEquals(-4.25, state.position.eastMeters!!, 0.0)
        assertEquals(6.75, state.speedMetersPerSecond!!, 0.0)
    }

    @Test
    fun telemetryPresentation_rejectsRegressiveOrInvalidValues() {
        val viewModel = ReplayNavigationViewModel()
        val accepted = ReplayIntent.PresentTelemetry(
            timestampNs = 2_000_000_000L,
            northMeters = 12.5,
            eastMeters = -4.25,
            speedMetersPerSecond = 6.75,
        )
        viewModel.onIntent(accepted)

        viewModel.onIntent(accepted.copy(timestampNs = 1_000_000_000L))
        viewModel.onIntent(accepted.copy(timestampNs = 3_000_000_000L, northMeters = Double.NaN))
        viewModel.onIntent(accepted.copy(timestampNs = 3_000_000_000L, speedMetersPerSecond = -1.0))

        assertEquals(2_000_000_000L, viewModel.uiState.value.currentTimestampNs)
        assertEquals(12.5, viewModel.uiState.value.position.northMeters!!, 0.0)
    }

    @Test
    fun reset_restoresCompleteInitialState() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(ReplayIntent.Play)
        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(2f))

        viewModel.onIntent(ReplayIntent.Reset)

        assertEquals(ReplayUiState(), viewModel.uiState.value)
    }
}
