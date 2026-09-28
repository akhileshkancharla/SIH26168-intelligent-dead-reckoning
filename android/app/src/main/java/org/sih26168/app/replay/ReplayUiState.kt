package org.sih26168.app.replay

import org.sih26168.contracts.enums.NavigationModeV1

/** Immutable replay-domain coordinate; MapLibre coordinates are created only by the viewport. */
data class GeoCoordinate(val latitude: Double, val longitude: Double)

enum class TrajectoryLayerType {
    RAW_GNSS,
    SCIENTIFIC_FUSED,
    MAP_MATCHED,
    REFERENCE_GROUND_TRUTH,
    DISPLAY_SMOOTHED,
    PLANNED_ROUTE,
}

enum class MapMatcherStatus {
    CLEAR,
    AMBIGUOUS,
    NO_CANDIDATE,
}

data class CovarianceEllipse(
    val center: GeoCoordinate,
    val semiMajorMeters: Double,
    val semiMinorMeters: Double,
    val orientationDegrees: Double,
    val polygonCoordinates: List<GeoCoordinate>,
)

data class MapCandidatePath(
    val candidateId: String,
    val coordinates: List<GeoCoordinate>,
    val likelihoodScore: Float,
    val isPrimary: Boolean,
)

data class DisplayRecoveryState(
    val start: GeoCoordinate,
    val target: GeoCoordinate,
    val startedAtNs: Long,
    val durationNs: Long,
)

object TrajectoryPresentationLabels {
    const val SEPARATION_FROM_LAST_TRUSTED_GNSS_FIX =
        "Separation from last trusted GNSS fix"
}

data class ReplayPositionMetrics(
    val northMeters: Double? = null,
    val eastMeters: Double? = null,
)

data class ReplayUiState(
    val provenanceDisplay: ReplayProvenanceDisplayState = ReplayProvenanceDisplayState(),
    val isReplaying: Boolean = false,
    val currentTimestampNs: Long = 0L,
    val speedMultiplier: Float = 1f,
    val isOutageActive: Boolean = false,
    val position: ReplayPositionMetrics = ReplayPositionMetrics(),
    val speedMetersPerSecond: Double? = null,
    val vehicleLocation: GeoCoordinate? = null,
    val headingDegrees: Double? = null,
    val isHeadingStable: Boolean = false,
    val isFollowingVehicle: Boolean = true,
    val isCourseUp: Boolean = false,
    val prefersCourseUp: Boolean = true,
    val isMapReady: Boolean = false,
    val lastTrustedGnssFix: GeoCoordinate? = null,
    val scientificFusedPath: List<GeoCoordinate> = emptyList(),
    val rawGnssPath: List<GeoCoordinate> = emptyList(),
    val mapMatchedPath: List<GeoCoordinate> = emptyList(),
    val referencePath: List<GeoCoordinate> = emptyList(),
    val displaySmoothedPath: List<GeoCoordinate> = emptyList(),
    val plannedRoutePath: List<GeoCoordinate> = emptyList(),
    val enabledLayers: Set<TrajectoryLayerType> = DEFAULT_TRAJECTORY_LAYERS,
    val mapMatcherStatus: MapMatcherStatus = MapMatcherStatus.NO_CANDIDATE,
    val navigationMode: NavigationModeV1 = NavigationModeV1.INITIALIZING,
    val displayVehicleLocation: GeoCoordinate? = null,
    val displayRecovery: DisplayRecoveryState? = null,
    val uncertaintyEllipse: CovarianceEllipse? = null,
    val candidateTrajectories: List<MapCandidatePath> = emptyList(),
    val showUncertaintyEllipse: Boolean = true,
    val showCandidateBranches: Boolean = false,
)

fun ReplayUiState.isTrajectoryLayerVisible(layer: TrajectoryLayerType): Boolean =
    layer in enabledLayers &&
        (layer != TrajectoryLayerType.MAP_MATCHED || mapMatcherStatus == MapMatcherStatus.CLEAR)

val ReplayUiState.isSeparationTetherVisible: Boolean
    get() = isOutageActive &&
        lastTrustedGnssFix != null &&
        (displayVehicleLocation ?: vehicleLocation) != null

val DEFAULT_TRAJECTORY_LAYERS: Set<TrajectoryLayerType> = setOf(
    TrajectoryLayerType.SCIENTIFIC_FUSED,
    TrajectoryLayerType.PLANNED_ROUTE,
)
