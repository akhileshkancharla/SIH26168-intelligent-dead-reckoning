package org.sih26168.app.replay

import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.Collections
import org.sih26168.contracts.enums.NavigationModeV1

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
            is ToggleTrajectoryLayerIntent -> toggleTrajectoryLayer(intent.layer)
            is AppendTrajectoryPointIntent -> appendTrajectoryPoint(intent)
            is ReplaceTrajectoryPathIntent -> replaceTrajectoryPath(intent)
            is SetMapMatcherStatusIntent ->
                _uiState.update { it.copy(mapMatcherStatus = intent.status) }
            is NavigationModeChangedIntent -> updateNavigationMode(intent)
            ReplayIntent.Play -> _uiState.update { it.copy(isReplaying = true) }
            ReplayIntent.Pause -> _uiState.update { it.copy(isReplaying = false) }
            ReplayIntent.Step -> stepOnce()
            ReplayIntent.Reset ->
                _uiState.update { ReplayUiState(isMapReady = it.isMapReady) }
            ReplayIntent.ToggleSimulatedOutage -> toggleSimulatedOutage()
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
                val scientificLocation = if (hasCompleteLocation) {
                    GeoCoordinate(telemetry.latitudeDegrees!!, telemetry.longitudeDegrees!!)
                } else {
                    state.vehicleLocation
                }
                val displayUpdate = advanceDisplayRecovery(
                    state = state,
                    timestampNs = telemetry.timestampNs,
                    scientificLocation = scientificLocation,
                )
                state.copy(
                    currentTimestampNs = telemetry.timestampNs,
                    position = ReplayPositionMetrics(
                        northMeters = telemetry.northMeters,
                        eastMeters = telemetry.eastMeters,
                    ),
                    speedMetersPerSecond = telemetry.speedMetersPerSecond,
                    vehicleLocation = scientificLocation,
                    headingDegrees = telemetry.headingDegrees?.normalizeHeading(),
                    isHeadingStable = telemetry.isHeadingStable,
                    isCourseUp = state.prefersCourseUp && canUseCourseUp(telemetry),
                    displayVehicleLocation = displayUpdate.location,
                    displaySmoothedPath = appendDistinct(
                        state.displaySmoothedPath,
                        displayUpdate.location,
                    ),
                    displayRecovery = displayUpdate.recovery,
                )
            }
        }
    }

    private fun toggleTrajectoryLayer(layer: TrajectoryLayerType) {
        _uiState.update { state ->
            val enabled = state.enabledLayers.toMutableSet().apply {
                if (!add(layer)) remove(layer)
            }.toSet()
            state.copy(enabledLayers = enabled)
        }
    }

    private fun appendTrajectoryPoint(intent: AppendTrajectoryPointIntent) {
        val coordinate = intent.coordinate.validatedCopy() ?: return
        _uiState.update { state ->
            if (intent.layer == TrajectoryLayerType.RAW_GNSS && state.isOutageActive) {
                state
            } else {
                state.withTrajectoryPath(
                    intent.layer,
                    immutablePath(state.trajectoryPath(intent.layer) + coordinate),
                )
            }
        }
    }

    private fun replaceTrajectoryPath(intent: ReplaceTrajectoryPathIntent) {
        val coordinates = intent.coordinates.map { it.validatedCopy() ?: return }
        _uiState.update { state ->
            if (intent.layer == TrajectoryLayerType.RAW_GNSS && state.isOutageActive) {
                state
            } else if (
                intent.layer == TrajectoryLayerType.SCIENTIFIC_FUSED &&
                !coordinates.preservesScientificHistory(state.scientificFusedPath)
            ) {
                state
            } else {
                state.withTrajectoryPath(intent.layer, immutablePath(coordinates))
            }
        }
    }

    private fun toggleSimulatedOutage() {
        _uiState.update { state ->
            if (state.isOutageActive) {
                state.copy(isOutageActive = false)
            } else {
                state.copy(
                    isOutageActive = true,
                    lastTrustedGnssFix = state.lastTrustedGnssFix
                        ?: state.rawGnssPath.lastOrNull()
                        ?: state.vehicleLocation,
                )
            }
        }
    }

    private fun updateNavigationMode(intent: NavigationModeChangedIntent) {
        val acceptedFix = intent.acceptedFix?.validatedCopy()
        if (intent.acceptedFix != null && acceptedFix == null) return

        _uiState.update { state ->
            val isAcceptedRecovery = state.navigationMode == NavigationModeV1.REACQUIRING &&
                intent.mode == NavigationModeV1.GNSS_AIDED && acceptedFix != null
            if (!isAcceptedRecovery) {
                state.copy(navigationMode = intent.mode)
            } else {
                val start = state.displayVehicleLocation
                    ?: state.vehicleLocation
                    ?: state.scientificFusedPath.lastOrNull()
                state.copy(
                    navigationMode = intent.mode,
                    displayVehicleLocation = start ?: acceptedFix,
                    displayRecovery = start?.let {
                        DisplayRecoveryState(
                            start = it,
                            target = acceptedFix,
                            startedAtNs = state.currentTimestampNs,
                            durationNs = DISPLAY_RECOVERY_DURATION_NS,
                        )
                    },
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

    private fun setLastTrustedGnssFix(fix: GeoCoordinate?) {
        if (fix != null && !isValidCoordinate(fix.latitude, fix.longitude)) return
        _uiState.update { it.copy(lastTrustedGnssFix = fix) }
    }

    private fun advanceDisplayRecovery(
        state: ReplayUiState,
        timestampNs: Long,
        scientificLocation: GeoCoordinate?,
    ): DisplayUpdate {
        val recovery = state.displayRecovery
            ?: return DisplayUpdate(scientificLocation, null)
        val elapsedNs = (timestampNs - recovery.startedAtNs).coerceAtLeast(0L)
        val fraction = (elapsedNs.toDouble() / recovery.durationNs.toDouble()).coerceIn(0.0, 1.0)
        val activeScientificLocation = scientificLocation ?: recovery.target
        val remaining = 1.0 - fraction
        val latitudeOffset = recovery.start.latitude - recovery.target.latitude
        val longitudeOffset = normalizeLongitude(recovery.start.longitude - recovery.target.longitude)
        val location = GeoCoordinate(
            activeScientificLocation.latitude + latitudeOffset * remaining,
            normalizeLongitude(activeScientificLocation.longitude + longitudeOffset * remaining),
        )
        return DisplayUpdate(
            location = location,
            recovery = recovery.takeIf { fraction < 1.0 },
        )
    }

    private fun normalizeLongitude(longitude: Double): Double =
        ((longitude + 540.0) % 360.0) - 180.0

    private fun appendDistinct(
        path: List<GeoCoordinate>,
        coordinate: GeoCoordinate?,
    ): List<GeoCoordinate> {
        coordinate ?: return path
        return if (path.lastOrNull() == coordinate) path else immutablePath(path + coordinate)
    }

    private fun GeoCoordinate.validatedCopy(): GeoCoordinate? =
        takeIf { isValidCoordinate(latitude, longitude) }

    private fun immutablePath(path: List<GeoCoordinate>): List<GeoCoordinate> =
        Collections.unmodifiableList(ArrayList(path))

    private fun List<GeoCoordinate>.preservesScientificHistory(
        history: List<GeoCoordinate>,
    ): Boolean = size >= history.size && history.indices.all { index ->
        this[index] == history[index]
    }

    private fun ReplayUiState.trajectoryPath(layer: TrajectoryLayerType): List<GeoCoordinate> =
        when (layer) {
            TrajectoryLayerType.RAW_GNSS -> rawGnssPath
            TrajectoryLayerType.SCIENTIFIC_FUSED -> scientificFusedPath
            TrajectoryLayerType.MAP_MATCHED -> mapMatchedPath
            TrajectoryLayerType.REFERENCE_GROUND_TRUTH -> referencePath
            TrajectoryLayerType.DISPLAY_SMOOTHED -> displaySmoothedPath
            TrajectoryLayerType.PLANNED_ROUTE -> plannedRoutePath
        }

    private fun ReplayUiState.withTrajectoryPath(
        layer: TrajectoryLayerType,
        path: List<GeoCoordinate>,
    ): ReplayUiState = when (layer) {
        TrajectoryLayerType.RAW_GNSS -> copy(rawGnssPath = path)
        TrajectoryLayerType.SCIENTIFIC_FUSED -> copy(scientificFusedPath = path)
        TrajectoryLayerType.MAP_MATCHED -> copy(mapMatchedPath = path)
        TrajectoryLayerType.REFERENCE_GROUND_TRUTH -> copy(referencePath = path)
        TrajectoryLayerType.DISPLAY_SMOOTHED -> copy(displaySmoothedPath = path)
        TrajectoryLayerType.PLANNED_ROUTE -> copy(plannedRoutePath = path)
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
        const val DISPLAY_RECOVERY_DURATION_NS = 2_000_000_000L
        val SUPPORTED_SPEED_MULTIPLIERS = listOf(0.5f, 1f, 2f)
    }

    private data class DisplayUpdate(
        val location: GeoCoordinate?,
        val recovery: DisplayRecoveryState?,
    )
}
