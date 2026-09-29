package org.sih26168.app.replay

import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.Collections
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import kotlin.math.sqrt
import org.sih26168.contracts.enums.NavigationModeV1

class ReplayNavigationViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(ReplayUiState())
    val uiState: StateFlow<ReplayUiState> = _uiState.asStateFlow()
    private var latestCandidateInputs: List<MapCandidatePath> = emptyList()

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
            is SetMapMatcherStatusIntent -> setMapMatcherStatus(intent.status)
            is ToggleUncertaintyEllipse ->
                _uiState.update { it.copy(showUncertaintyEllipse = intent.visible) }
            is ToggleCandidateBranches ->
                _uiState.update { it.copy(showCandidateBranches = intent.visible) }
            is PresentPositionCovarianceIntent -> presentPositionCovariance(intent)
            is PresentMapCandidatesIntent -> presentMapCandidates(intent.candidates)
            is UpdateHealthStates -> updateHealthStates(intent)
            is NavigationModeChangedIntent -> updateNavigationMode(intent)
            ReplayIntent.Play -> _uiState.update {
                it.copy(isReplaying = true, replayEngineStatus = ReplayEngineStatus.PLAYING)
            }
            ReplayIntent.Pause -> _uiState.update {
                it.copy(isReplaying = false, replayEngineStatus = ReplayEngineStatus.PAUSED)
            }
            ReplayIntent.Step -> stepOnce()
            ReplayIntent.Reset -> reset()
            ReplayIntent.ToggleSimulatedOutage -> toggleSimulatedOutage()
            is ReplayIntent.SetSpeedMultiplier -> setSpeedMultiplier(intent.multiplier)
            is ReplayIntent.PresentTelemetry -> presentTelemetry(intent)
        }
    }

    private fun reset() {
        latestCandidateInputs = emptyList()
        _uiState.update { ReplayUiState(isMapReady = it.isMapReady) }
    }

    private fun updateHealthStates(intent: UpdateHealthStates) {
        _uiState.update { state ->
            val engine = intent.replayEngine ?: state.replayEngineStatus
            state.copy(
                gnssHealth = intent.gnss?.validatedFor(state) ?: state.gnssHealth,
                alignmentHealth = intent.alignment?.validated() ?: state.alignmentHealth,
                modelHealth = intent.model?.validated() ?: state.modelHealth,
                replayEngineStatus = engine,
                isReplaying = engine == ReplayEngineStatus.PLAYING,
            )
        }
    }

    private fun GnssHealthState.validatedFor(state: ReplayUiState): GnssHealthState {
        val valid = status != GnssFixStatus.OUTAGE_SIMULATED &&
            (satelliteCount == null || satelliteCount in 0..MAX_SATELLITES) &&
            (hdop == null || (hdop.isFinite() && hdop > 0.0 && hdop <= MAX_DOP)) &&
            (pdop == null || (pdop.isFinite() && pdop > 0.0 && pdop <= MAX_DOP)) &&
            (trustedFixTimestampNs == null ||
                trustedFixTimestampNs in 0L..state.currentTimestampNs)
        return if (valid) this else GnssHealthState()
    }

    private fun AlignmentHealthState.validated(): AlignmentHealthState {
        val valid = (uncertaintyDegrees == null ||
            (uncertaintyDegrees.isFinite() && uncertaintyDegrees in 0.0..180.0)) &&
            (convergenceProgress == null ||
                (convergenceProgress.isFinite() && convergenceProgress in 0.0..1.0))
        return if (valid) this else AlignmentHealthState()
    }

    private fun ModelHealthState.validated(): ModelHealthState {
        val valid = residualMagnitude == null ||
            (residualMagnitude.isFinite() && residualMagnitude in 0.0..MAX_RESIDUAL_MAGNITUDE)
        return if (valid) this else ModelHealthState()
    }

    private fun presentPositionCovariance(intent: PresentPositionCovarianceIntent) {
        val ellipse = calculateTwoSigmaCovarianceEllipse(
            center = intent.center,
            pxx = intent.pxxMetersSquared,
            pyy = intent.pyyMetersSquared,
            pxy = intent.pxyMetersSquared,
        )
        _uiState.update { it.copy(uncertaintyEllipse = ellipse) }
    }

    private fun presentMapCandidates(candidates: List<MapCandidatePath>) {
        latestCandidateInputs = candidates.mapNotNull { it.validatedCopy() }
            .distinctBy(MapCandidatePath::candidateId)
        _uiState.update { state ->
            state.copy(
                candidateTrajectories = gateMapCandidates(
                    state.mapMatcherStatus,
                    latestCandidateInputs,
                ),
            )
        }
    }

    private fun setMapMatcherStatus(status: MapMatcherStatus) {
        _uiState.update { state ->
            state.copy(
                mapMatcherStatus = status,
                candidateTrajectories = gateMapCandidates(status, latestCandidateInputs),
            )
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

    private fun MapCandidatePath.validatedCopy(): MapCandidatePath? {
        if (candidateId.isBlank() || !likelihoodScore.isFinite() || likelihoodScore < 0f) {
            return null
        }
        val path = coordinates.map { it.validatedCopy() ?: return null }
        if (path.size < 2) return null
        return copy(coordinates = Collections.unmodifiableList(ArrayList(path)))
    }

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
        const val MAX_SATELLITES = 128
        const val MAX_DOP = 50.0
        const val MAX_RESIDUAL_MAGNITUDE = 1_000_000.0
        val SUPPORTED_SPEED_MULTIPLIERS = listOf(0.5f, 1f, 2f)
    }

    private data class DisplayUpdate(
        val location: GeoCoordinate?,
        val recovery: DisplayRecoveryState?,
    )
}

/**
 * Converts an I-08 local east/north 2D covariance into a presentation-only 2σ ellipse.
 * Invalid, non-finite, overflowing, non-positive-semidefinite, or polar inputs fail closed with null.
 */
internal fun calculateTwoSigmaCovarianceEllipse(
    center: GeoCoordinate,
    pxx: Double,
    pyy: Double,
    pxy: Double,
): CovarianceEllipse? {
    if (!center.latitude.isFinite() || !center.longitude.isFinite() ||
        center.latitude !in -90.0..90.0 || center.longitude !in -180.0..180.0 ||
        !pxx.isFinite() || !pyy.isFinite() || !pxy.isFinite() ||
        pxx < 0.0 || pyy < 0.0
    ) {
        return null
    }

    val eigenSeparation = hypot(pxx - pyy, 2.0 * pxy)
    if (!eigenSeparation.isFinite()) return null

    val trace = pxx + pyy
    if (!trace.isFinite()) return null

    val lambdaMajor = (trace + eigenSeparation) / 2.0
    val lambdaMinorRaw = (trace - eigenSeparation) / 2.0
    if (!lambdaMajor.isFinite() || !lambdaMinorRaw.isFinite()) return null

    if (lambdaMajor < 0.0 || lambdaMinorRaw < 0.0) return null

    val semiMajor = TWO_SIGMA_SCALE * sqrt(lambdaMajor)
    val semiMinor = TWO_SIGMA_SCALE * sqrt(lambdaMinorRaw)
    if (!semiMajor.isFinite() || !semiMinor.isFinite()) return null

    val orientationRadians = 0.5 * atan2(2.0 * pxy, pxx - pyy)
    if (!orientationRadians.isFinite()) return null

    val latitudeRadians = Math.toRadians(center.latitude)
    val longitudeScale = EARTH_RADIUS_METERS * cos(latitudeRadians)
    if (!longitudeScale.isFinite() || kotlin.math.abs(longitudeScale) < MIN_LONGITUDE_SCALE_METERS) {
        return null
    }

    val boundary = ArrayList<GeoCoordinate>(ELLIPSE_SEGMENTS + 1)
    for (index in 0..ELLIPSE_SEGMENTS) {
        if (index == ELLIPSE_SEGMENTS) {
            boundary.add(boundary.first())
            break
        }
        val phase = 2.0 * Math.PI * index / ELLIPSE_SEGMENTS
        val eastMeters = semiMajor * cos(phase) * cos(orientationRadians) -
            semiMinor * sin(phase) * sin(orientationRadians)
        val northMeters = semiMajor * cos(phase) * sin(orientationRadians) +
            semiMinor * sin(phase) * cos(orientationRadians)
        if (!eastMeters.isFinite() || !northMeters.isFinite()) return null

        val deltaLat = Math.toDegrees(northMeters / EARTH_RADIUS_METERS)
        val deltaLon = Math.toDegrees(eastMeters / longitudeScale)
        if (!deltaLat.isFinite() || !deltaLon.isFinite() ||
            kotlin.math.abs(deltaLon) >= 180.0
        ) return null

        val latitude = center.latitude + deltaLat
        val unwrappedLongitude = center.longitude + deltaLon
        if (!latitude.isFinite() || latitude !in -90.0..90.0 ||
            !unwrappedLongitude.isFinite()
        ) return null
        val longitude = normalizeLongitudeDegrees(unwrappedLongitude)
        if (!longitude.isFinite()) return null

        boundary.add(GeoCoordinate(latitude, longitude))
    }

    return CovarianceEllipse(
        center = GeoCoordinate(center.latitude, center.longitude),
        semiMajorMeters = semiMajor,
        semiMinorMeters = semiMinor,
        orientationDegrees = Math.toDegrees(orientationRadians),
        polygonCoordinates = Collections.unmodifiableList(boundary),
    )
}

/**
 * Gates map-matcher candidate paths according to matcher status.
 * In AMBIGUOUS status, enforces singular primary cardinality: exactly the highest-likelihood
 * candidate is designated primary (`isPrimary = true`), and up to 2 alternative candidates are
 * designated non-primary (`isPrimary = false`).
 */
internal fun gateMapCandidates(
    status: MapMatcherStatus,
    candidates: List<MapCandidatePath>,
): List<MapCandidatePath> = when (status) {
    MapMatcherStatus.NO_CANDIDATE -> emptyList()
    MapMatcherStatus.CLEAR -> candidates
        .asSequence()
        .filter { it.isPrimary && it.isRenderableCandidate() }
        .sortedWith(compareByDescending<MapCandidatePath> { it.likelihoodScore }.thenBy { it.candidateId })
        .firstOrNull()
        ?.safePresentationCopy(isPrimary = true, score = 1f)
        ?.let(::listOf)
        .orEmpty()
    MapMatcherStatus.AMBIGUOUS -> {
        val validCandidates = candidates.filter(MapCandidatePath::isRenderableCandidate)
            .distinctBy(MapCandidatePath::candidateId)
        if (validCandidates.isEmpty()) {
            emptyList()
        } else {
            val topCandidates = validCandidates
                .sortedWith(compareByDescending<MapCandidatePath> { it.likelihoodScore }.thenBy { it.candidateId })
                .take(MAX_AMBIGUOUS_CANDIDATES)
            val scoreTotal = topCandidates.sumOf { it.likelihoodScore.toDouble() }
            Collections.unmodifiableList(topCandidates.mapIndexed { index, candidate ->
                candidate.safePresentationCopy(
                    isPrimary = (index == 0),
                    score = if (scoreTotal > 0.0) {
                        (candidate.likelihoodScore / scoreTotal).toFloat()
                    } else {
                        1f / topCandidates.size
                    },
                )
            })
        }
    }
}

private fun MapCandidatePath.isRenderableCandidate(): Boolean =
    candidateId.isNotBlank() && likelihoodScore.isFinite() && likelihoodScore >= 0f &&
        coordinates.size >= 2 && coordinates.all {
            it.latitude.isFinite() && it.longitude.isFinite() &&
                it.latitude in -90.0..90.0 && it.longitude in -180.0..180.0
        }

private fun MapCandidatePath.safePresentationCopy(
    isPrimary: Boolean,
    score: Float,
): MapCandidatePath = copy(
    coordinates = Collections.unmodifiableList(ArrayList(coordinates)),
    likelihoodScore = score,
    isPrimary = isPrimary,
)

private fun normalizeLongitudeDegrees(longitude: Double): Double =
    ((longitude + 540.0) % 360.0) - 180.0

private const val EARTH_RADIUS_METERS = 6_371_008.8
private const val MIN_LONGITUDE_SCALE_METERS = 1.0
private const val TWO_SIGMA_SCALE = 2.0
private const val ELLIPSE_SEGMENTS = 36
private const val MAX_AMBIGUOUS_CANDIDATES = 3
