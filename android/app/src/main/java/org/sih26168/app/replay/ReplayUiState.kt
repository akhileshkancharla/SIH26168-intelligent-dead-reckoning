package org.sih26168.app.replay

import java.util.Collections
import org.sih26168.contracts.enums.AlignmentStatusV1
import org.sih26168.contracts.enums.HealthIntegrityStateV1
import org.sih26168.contracts.enums.ModelStatusV1
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

/** Fix dimensionality is telemetry, not an integrity or outage classification. */
enum class GnssFixDimension { FIX_3D, FIX_2D, NO_FIX }

data class GnssHealthState(
    val integrity: HealthIntegrityStateV1 = HealthIntegrityStateV1.UNAVAILABLE,
    val fixDimension: GnssFixDimension? = null,
    val satelliteCount: Int? = null,
    val hdop: Double? = null,
    val pdop: Double? = null,
    val trustedFixTimestampNs: Long? = null,
)

data class AlignmentHealthState(
    val status: AlignmentStatusV1 = AlignmentStatusV1.UNINITIALIZED,
    val uncertaintyDegrees: Double? = null,
    val convergenceProgress: Double? = null,
)

data class ModelHealthState(
    val status: ModelStatusV1 = ModelStatusV1.DISABLED,
    val residual: Double? = null,
    val innovationCovarianceTrace: Double? = null,
)

enum class ReplayEngineStatus { PLAYING, PAUSED, BUFFERING, SEEKING }

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
    val gnssHealth: GnssHealthState = GnssHealthState(),
    val alignmentHealth: AlignmentHealthState = AlignmentHealthState(),
    val modelHealth: ModelHealthState = ModelHealthState(),
    val replayEngineStatus: ReplayEngineStatus = ReplayEngineStatus.PAUSED,
) {
    /** I-14 disclosure state; independent of the underlying GNSS integrity record. */
    val isOutageSimulated: Boolean
        get() = isOutageActive
}

/**
 * Hide fix-specific metrics while the software mask is active. The source integrity
 * classification and underlying gnssHealth value are deliberately not rewritten.
 */
val ReplayUiState.displayGnssHealth: GnssHealthState
    get() = if (isOutageSimulated) {
        gnssHealth.copy(
            fixDimension = null,
            satelliteCount = null,
            hdop = null,
            pdop = null,
        )
    } else {
        gnssHealth
    }

val ReplayUiState.trustedFixAgeNs: Long?
    get() = gnssHealth.trustedFixTimestampNs?.let { trustedAt ->
        (currentTimestampNs - trustedAt).takeIf { it >= 0L }
    }

fun ReplayUiState.isTrajectoryLayerVisible(layer: TrajectoryLayerType): Boolean =
    layer in enabledLayers &&
        (layer != TrajectoryLayerType.MAP_MATCHED || mapMatcherStatus == MapMatcherStatus.CLEAR)

val ReplayUiState.isSeparationTetherVisible: Boolean
    get() = isOutageSimulated &&
        lastTrustedGnssFix != null &&
        (displayVehicleLocation ?: vehicleLocation) != null

val DEFAULT_TRAJECTORY_LAYERS: Set<TrajectoryLayerType> =
    Collections.unmodifiableSet(
        setOf(
            TrajectoryLayerType.SCIENTIFIC_FUSED,
            TrajectoryLayerType.PLANNED_ROUTE,
        ),
    )