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
            RecenterMapIntent -> _uiState.update { it.copy(isFollowingVehicle = true) }
            ToggleCameraModeIntent -> toggleCameraMode()
            MapDraggedIntent -> _uiState.update { it.copy(isFollowingVehicle = false) }
            MapReadyIntent -> _uiState.update { it.copy(isMapReady = true) }
            is LastTrustedGnssFixIntent -> setLastTrustedGnssFix(intent.fix)
            ReplayIntent.Play -> _uiState.update { it.copy(isReplaying = true) }
            ReplayIntent.Pause -> _uiState.update { it.copy(isReplaying = false) }
            ReplayIntent.Step -> stepOnce()
            ReplayIntent.Reset ->
                _uiState.update { ReplayUiState(isMapReady = it.isMapReady) }
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
        val hasCompleteLocation =
            telemetry.latitudeDegrees != null && telemetry.longitudeDegrees != null
        val hasPartialLocation =
            (telemetry.latitudeDegrees == null) != (telemetry.longitudeDegrees == null)
        val isValid = telemetry.timestampNs >= 0L &&
            telemetry.northMeters.isFinite() &&
            telemetry.eastMeters.isFinite() &&
            telemetry.speedMetersPerSecond.isFinite() &&
            telemetry.speedMetersPerSecond >= 0.0 &&
            !hasPartialLocation &&
            (!hasCompleteLocation || isValidCoordinate(
                telemetry.latitudeDegrees!!,
                telemetry.longitudeDegrees!!,
            )) &&
            (telemetry.headingDegrees == null || telemetry.headingDegrees.isFinite())
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
                    vehicleLocation = if (hasCompleteLocation) {
                        org.maplibre.android.geometry.LatLng(
                            telemetry.latitudeDegrees!!,
                            telemetry.longitudeDegrees!!,
                        )
                    } else {
                        state.vehicleLocation
                    },
                    headingDegrees = telemetry.headingDegrees?.normalizeHeading(),
                    isHeadingStable = telemetry.isHeadingStable,
                    isCourseUp = state.prefersCourseUp && canUseCourseUp(telemetry),
                )
            }
        }
    }

    private fun toggleCameraMode() {
        _uiState.update { state ->
            val prefersCourseUp = !state.prefersCourseUp
            state.copy(
                prefersCourseUp = prefersCourseUp,
                isCourseUp = prefersCourseUp && canUseCourseUp(state),
            )
        }
    }

    private fun setLastTrustedGnssFix(fix: org.maplibre.android.geometry.LatLng?) {
        if (fix != null && !isValidCoordinate(fix.latitude, fix.longitude)) return
        _uiState.update { it.copy(lastTrustedGnssFix = fix) }
    }

    private fun canUseCourseUp(state: ReplayUiState): Boolean =
        state.speedMetersPerSecond?.let { it >= COURSE_UP_MIN_SPEED_METERS_PER_SECOND } == true &&
            state.isHeadingStable &&
            state.headingDegrees?.isFinite() == true

    private fun canUseCourseUp(telemetry: ReplayIntent.PresentTelemetry): Boolean =
        telemetry.speedMetersPerSecond >= COURSE_UP_MIN_SPEED_METERS_PER_SECOND &&
            telemetry.isHeadingStable &&
            telemetry.headingDegrees?.isFinite() == true

    private fun isValidCoordinate(latitude: Double, longitude: Double): Boolean =
        latitude.isFinite() && longitude.isFinite() &&
            latitude in -90.0..90.0 && longitude in -180.0..180.0

    private fun Double.normalizeHeading(): Double = ((this % 360.0) + 360.0) % 360.0

    companion object {
        const val STEP_INTERVAL_NS = 100_000_000L
        const val COURSE_UP_MIN_SPEED_METERS_PER_SECOND = 1.0
        val SUPPORTED_SPEED_MULTIPLIERS = listOf(0.5f, 1f, 2f)
    }
}
