package org.sih26168.app.replay

import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

class ReplayNavigationViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(ReplayUiState())
    val uiState: StateFlow<ReplayUiState> = _uiState.asStateFlow()

    fun onIntent(intent: ReplayIntent) {
        when (intent) {
            ReplayIntent.Play -> _uiState.update { it.copy(isReplaying = true) }
            ReplayIntent.Pause -> _uiState.update { it.copy(isReplaying = false) }
            ReplayIntent.Step -> stepOnce()
            ReplayIntent.Reset -> _uiState.value = ReplayUiState()
            ReplayIntent.ToggleSimulatedOutage ->
                _uiState.update { it.copy(isOutageActive = !it.isOutageActive) }
            is ReplayIntent.SetSpeedMultiplier -> setSpeedMultiplier(intent.multiplier)
            is ReplayIntent.PresentTelemetry -> presentTelemetry(intent)
        }
    }

    private fun stepOnce() {
        _uiState.update { state ->
            if (state.isReplaying) {
                state
            } else {
                state.copy(currentTimestampNs = state.currentTimestampNs + STEP_INTERVAL_NS)
            }
        }
    }

    private fun setSpeedMultiplier(multiplier: Float) {
        if (multiplier in SUPPORTED_SPEED_MULTIPLIERS) {
            _uiState.update { it.copy(speedMultiplier = multiplier) }
        }
    }

    private fun presentTelemetry(telemetry: ReplayIntent.PresentTelemetry) {
        val isValid = telemetry.timestampNs >= 0L &&
            telemetry.northMeters.isFinite() &&
            telemetry.eastMeters.isFinite() &&
            telemetry.speedMetersPerSecond.isFinite() &&
            telemetry.speedMetersPerSecond >= 0.0
        if (!isValid) return

        _uiState.update { state ->
            if (telemetry.timestampNs < state.currentTimestampNs) {
                state
            } else {
                state.copy(
                    currentTimestampNs = telemetry.timestampNs,
                    position = ReplayPositionMetrics(
                        northMeters = telemetry.northMeters,
                        eastMeters = telemetry.eastMeters,
                    ),
                    speedMetersPerSecond = telemetry.speedMetersPerSecond,
                )
            }
        }
    }

    companion object {
        const val STEP_INTERVAL_NS = 100_000_000L
        val SUPPORTED_SPEED_MULTIPLIERS = listOf(0.5f, 1f, 2f)
    }
}
