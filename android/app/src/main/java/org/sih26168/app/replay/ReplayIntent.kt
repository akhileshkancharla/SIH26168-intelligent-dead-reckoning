package org.sih26168.app.replay

import org.sih26168.contracts.enums.NavigationModeV1

data object RecenterMapIntent : ReplayIntent

data object ToggleCameraModeIntent : ReplayIntent

data object MapDraggedIntent : ReplayIntent

data object MapReadyIntent : ReplayIntent

data class LastTrustedGnssFixIntent(val fix: GeoCoordinate?) : ReplayIntent

data class ToggleTrajectoryLayerIntent(val layer: TrajectoryLayerType) : ReplayIntent

data class AppendTrajectoryPointIntent(
    val layer: TrajectoryLayerType,
    val coordinate: GeoCoordinate,
) : ReplayIntent

data class ReplaceTrajectoryPathIntent(
    val layer: TrajectoryLayerType,
    val coordinates: List<GeoCoordinate>,
) : ReplayIntent

data class SetMapMatcherStatusIntent(val status: MapMatcherStatus) : ReplayIntent

data class NavigationModeChangedIntent(
    val mode: NavigationModeV1,
    val acceptedFix: GeoCoordinate? = null,
) : ReplayIntent

sealed interface ReplayIntent {
    data object Play : ReplayIntent

    data object Pause : ReplayIntent

    data object Step : ReplayIntent

    data object Reset : ReplayIntent

    data object ToggleSimulatedOutage : ReplayIntent

    data class SetSpeedMultiplier(val multiplier: Float) : ReplayIntent

    /**
     * Read-only presentation telemetry supplied by the replay/scientific boundary.
     * This intent never feeds UI state back into C-07.
     */
    data class PresentTelemetry(
        val timestampNs: Long,
        val northMeters: Double,
        val eastMeters: Double,
        val speedMetersPerSecond: Double,
        val latitudeDegrees: Double? = null,
        val longitudeDegrees: Double? = null,
        val headingDegrees: Double? = null,
        val isHeadingStable: Boolean = false,
    ) : ReplayIntent
}
