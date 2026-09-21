package org.sih26168.app.replay

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
    ) : ReplayIntent
}
