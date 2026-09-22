package org.sih26168.app.replay

import org.maplibre.android.geometry.LatLng

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
    val vehicleLocation: LatLng? = null,
    val headingDegrees: Double? = null,
    val isHeadingStable: Boolean = false,
    val isFollowingVehicle: Boolean = true,
    val isCourseUp: Boolean = false,
    val prefersCourseUp: Boolean = true,
    val isMapReady: Boolean = false,
    val lastTrustedGnssFix: LatLng? = null,
)
