package org.sih26168.app.replay

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
)
