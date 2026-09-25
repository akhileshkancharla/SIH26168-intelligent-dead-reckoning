package org.sih26168.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import java.util.Locale
import org.sih26168.app.ReplayDisclosure
import org.sih26168.app.replay.ReplayIntent
import org.sih26168.contracts.enums.AlignmentStatusV1
import org.sih26168.app.replay.GnssFixStatus
import org.sih26168.app.replay.ModelStatus
import org.sih26168.app.replay.ReplayEngineStatus
import org.sih26168.app.replay.MapMatcherStatus
import org.sih26168.app.replay.ReplayNavigationViewModel
import org.sih26168.app.replay.ReplayUiState
import org.sih26168.app.replay.ToggleCandidateBranches
import org.sih26168.app.replay.ToggleTrajectoryLayerIntent
import org.sih26168.app.replay.ToggleUncertaintyEllipse
import org.sih26168.app.replay.TrajectoryLayerType
import org.sih26168.app.replay.TrajectoryPresentationLabels
import org.sih26168.app.replay.isSeparationTetherVisible
import org.sih26168.app.replay.displayGnssHealth
import org.sih26168.app.replay.trustedFixAgeNs

object ReplayGovernanceLabels {
    const val SOURCE = "SOURCE: DETERMINISTIC_REPLAY"
    const val DEMO = "DEMO"
    const val SIMULATED_OUTAGE = "SIMULATED OUTAGE"
    const val OSM_ATTRIBUTION = "© OpenStreetMap contributors"
    const val REPLAY_MODE = "REPLAY MODE"
}

/** Primary disclosures are rendered before all secondary metadata, without a scroll container. */
internal fun pinnedDisclosureLabels(isOutageActive: Boolean): List<String> =
    if (isOutageActive) {
        listOf(ReplayDisclosure.LABEL, ReplayGovernanceLabels.SIMULATED_OUTAGE)
    } else {
        listOf(ReplayDisclosure.LABEL)
    }

object GovernanceBadgeTags {
    const val FRAME = "governance-frame"
    const val REPLAY = "governance-replay"
    const val OUTAGE = "governance-outage"
}

@Composable
fun ReplayNavigationShell(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
    modifier: Modifier = Modifier,
    viewportContent: @Composable BoxScope.() -> Unit = {
        MapLibreMapViewport(state = state, onIntent = onIntent)
    },
) {
    Column(modifier = modifier.fillMaxSize()) {
        GovernanceFrame(state = state)
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .semantics { contentDescription = "Replay map viewport" },
            contentAlignment = Alignment.Center,
            content = viewportContent,
        )
        AttributionBanner()
        TelemetryAndControlSheet(state = state, onIntent = onIntent)
    }
}

@Composable
private fun GovernanceFrame(state: ReplayUiState) {
    Surface(modifier = Modifier.fillMaxWidth().testTag(GovernanceBadgeTags.FRAME),
        tonalElevation = 4.dp) {
        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                pinnedDisclosureLabels(state.isOutageActive).forEach { label ->
                    GovernanceBadge(
                        label,
                        prominent = true,
                        modifier = Modifier.weight(1f).testTag(
                            if (label == ReplayDisclosure.LABEL) {
                                GovernanceBadgeTags.REPLAY
                            } else {
                                GovernanceBadgeTags.OUTAGE
                            },
                        ),
                    )
                }
            }
            GovernanceBadge(ReplayGovernanceLabels.SOURCE,
                modifier = Modifier.fillMaxWidth())
            Row(modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GovernanceBadge(ReplayGovernanceLabels.DEMO, modifier = Modifier.weight(1f))
                GovernanceBadge(ReplayGovernanceLabels.REPLAY_MODE,
                    modifier = Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun GovernanceBadge(
    label: String,
    prominent: Boolean = false,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        color = if (prominent) {
            MaterialTheme.colorScheme.errorContainer
        } else {
            MaterialTheme.colorScheme.surfaceVariant
        },
        contentColor = if (prominent) {
            MaterialTheme.colorScheme.onErrorContainer
        } else {
            MaterialTheme.colorScheme.onSurfaceVariant
        },
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = MaterialTheme.shapes.small,
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = if (prominent) FontWeight.Bold else FontWeight.Medium,
        )
    }
}

@Composable
fun BoxScope.MapViewportPlaceholder() {
    Surface(
        modifier = Modifier
            .align(Alignment.Center)
            .fillMaxWidth()
            .heightIn(min = 180.dp)
            .padding(16.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = "LOCAL MAP VIEWPORT",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "MapLibre container reserved for WP-09.2",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun AttributionBanner() {
    var showAttribution by remember { mutableStateOf(false) }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { showAttribution = true }
            .semantics { contentDescription = "OpenStreetMap attribution details" },
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Text(
            text = ReplayGovernanceLabels.OSM_ATTRIBUTION,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelMedium,
        )
    }

    if (showAttribution) {
        AlertDialog(
            onDismissRequest = { showAttribution = false },
            title = { Text("Map attribution") },
            text = {
                Text(
                    "Map data © OpenStreetMap contributors. " +
                        "This offline replay uses only locally packaged map assets.",
                )
            },
            confirmButton = {
                TextButton(onClick = { showAttribution = false }) {
                    Text("Close")
                }
            },
        )
    }
}

@Composable
private fun TelemetryAndControlSheet(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
) {
    var healthExpanded by remember { mutableStateOf(false) }
    Surface(modifier = Modifier.fillMaxWidth(), tonalElevation = 6.dp) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(text = "Replay telemetry", style = MaterialTheme.typography.titleMedium)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                TelemetryValue("State", state.replayEngineStatus.name)
                TelemetryValue("Time", formatTimestamp(state.currentTimestampNs))
                TelemetryValue("North", formatDistance(state.position.northMeters))
                TelemetryValue("East", formatDistance(state.position.eastMeters))
                TelemetryValue("Speed", formatSpeed(state.speedMetersPerSecond))
            }
            if (state.isSeparationTetherVisible) {
                Text(
                    text = TrajectoryPresentationLabels
                        .SEPARATION_FROM_LAST_TRUSTED_GNSS_FIX,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }
            TrajectoryLayerFilters(state = state, onIntent = onIntent)
            DiagnosticOverlayFilters(state = state, onIntent = onIntent)
            TextButton(onClick = { healthExpanded = !healthExpanded }) {
                Text(if (healthExpanded) "Hide health diagnostics" else "Show health diagnostics")
            }
            if (healthExpanded) HealthDiagnostics(state)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(
                    onClick = { onIntent(ReplayIntent.Play) },
                    enabled = !state.isReplaying,
                ) { Text("Play") }
                Button(
                    onClick = { onIntent(ReplayIntent.Pause) },
                    enabled = state.isReplaying,
                ) { Text("Pause") }
                OutlinedButton(
                    onClick = { onIntent(ReplayIntent.Step) },
                    enabled = !state.isReplaying,
                ) { Text("Step") }
                OutlinedButton(
                    onClick = {
                        onIntent(
                            ReplayIntent.SetSpeedMultiplier(nextSpeed(state.speedMultiplier)),
                        )
                    },
                ) { Text("Speed ${formatMultiplier(state.speedMultiplier)}") }
                OutlinedButton(onClick = { onIntent(ReplayIntent.Reset) }) {
                    Text("Reset")
                }
                OutlinedButton(
                    onClick = { onIntent(ReplayIntent.ToggleSimulatedOutage) },
                ) {
                    Text(if (state.isOutageActive) "End outage" else "Start outage")
                }
            }
        }
    }
}

@Composable
private fun HealthDiagnostics(state: ReplayUiState) {
    val gnss = state.displayGnssHealth
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Subsystem health · presentation only", style = MaterialTheme.typography.labelLarge)
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            HealthBadge("GNSS", gnss.status.name, when (gnss.status) {
                GnssFixStatus.FIX_3D -> HEALTH_EMERALD
                GnssFixStatus.FIX_2D, GnssFixStatus.UNKNOWN -> HEALTH_AMBER
                GnssFixStatus.NO_FIX, GnssFixStatus.OUTAGE_SIMULATED -> HEALTH_CRIMSON
            })
            HealthBadge("Alignment", state.alignmentHealth.status.name,
                alignmentHealthColor(state.alignmentHealth.status))
            HealthBadge("Model", state.modelHealth.status.name,
                when (state.modelHealth.status) {
                    ModelStatus.NOMINAL -> HEALTH_EMERALD
                    ModelStatus.RECOVERY_ACTIVE, ModelStatus.UNKNOWN -> HEALTH_AMBER
                    ModelStatus.DIVERGING -> HEALTH_CRIMSON
                })
            HealthBadge("Replay", state.replayEngineStatus.name,
                when (state.replayEngineStatus) {
                    ReplayEngineStatus.PLAYING -> HEALTH_EMERALD
                    ReplayEngineStatus.PAUSED, ReplayEngineStatus.BUFFERING,
                    ReplayEngineStatus.SEEKING -> HEALTH_AMBER
                })
        }
        Text("REPLAY MODE · health indicators do not control the estimator",
            style = MaterialTheme.typography.labelMedium)
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            TelemetryValue("Satellites", gnss.satelliteCount?.toString() ?: "UNAVAILABLE")
            TelemetryValue("HDOP", formatHealthNumber(gnss.hdop))
            TelemetryValue("PDOP", formatHealthNumber(gnss.pdop))
            TelemetryValue("Fix age", state.trustedFixAgeNs?.let {
                String.format(Locale.US, "%.1f s", it / 1_000_000_000.0)
            } ?: "UNAVAILABLE")
            TelemetryValue("Align ±", state.alignmentHealth.uncertaintyDegrees?.let {
                String.format(Locale.US, "%.1f°", it)
            } ?: "UNAVAILABLE")
            TelemetryValue("Convergence", state.alignmentHealth.convergenceProgress?.let {
                String.format(Locale.US, "%.0f%%", it * 100.0)
            } ?: "UNAVAILABLE")
            TelemetryValue("Residual", formatHealthNumber(state.modelHealth.residualMagnitude))
            TelemetryValue("Innovation", state.modelHealth.innovationCovarianceStatus.name)
        }
    }
}

@Composable
private fun HealthBadge(label: String, status: String, background: Color) {
    Surface(
        color = background,
        contentColor = if (background == HEALTH_CRIMSON) Color.White else Color.Black,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier.semantics { contentDescription = "$label health: $status" },
    ) {
        Text("$label: $status", modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
    }
}

private fun formatHealthNumber(value: Double?): String =
    value?.let { String.format(Locale.US, "%.2f", it) } ?: "UNAVAILABLE"

@Composable
private fun DiagnosticOverlayFilters(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = "Scientific and matcher diagnostics",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterChip(
                selected = state.showUncertaintyEllipse,
                onClick = {
                    onIntent(ToggleUncertaintyEllipse(!state.showUncertaintyEllipse))
                },
                label = { Text("2σ Covariance Ellipse") },
            )
            FilterChip(
                selected = state.showCandidateBranches,
                onClick = {
                    onIntent(ToggleCandidateBranches(!state.showCandidateBranches))
                },
                label = { Text("Top-K Candidates") },
            )
            MatcherStatusChip(state.mapMatcherStatus)
        }
    }
}

@Composable
private fun MatcherStatusChip(status: MapMatcherStatus) {
    val (background, foreground) = when (status) {
        MapMatcherStatus.CLEAR -> MATCHER_CLEAR to Color.Black
        MapMatcherStatus.AMBIGUOUS -> MATCHER_AMBIGUOUS to Color.Black
        MapMatcherStatus.NO_CANDIDATE -> MATCHER_NO_CANDIDATE to Color.White
    }
    Surface(
        color = background,
        contentColor = foreground,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = MaterialTheme.shapes.small,
    ) {
        Text(
            text = "Matcher: ${status.name}",
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun TrajectoryLayerFilters(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = "Map layers",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TrajectoryLayerType.entries.forEach { layer ->
                FilterChip(
                    selected = layer in state.enabledLayers,
                    onClick = { onIntent(ToggleTrajectoryLayerIntent(layer)) },
                    label = { Text(layer.filterLabel(state)) },
                )
            }
        }
    }
}

private fun TrajectoryLayerType.filterLabel(state: ReplayUiState): String = when (this) {
    TrajectoryLayerType.RAW_GNSS -> "Raw GNSS"
    TrajectoryLayerType.SCIENTIFIC_FUSED -> "Scientific [S]"
    TrajectoryLayerType.MAP_MATCHED -> "Map-matched (${state.mapMatcherStatus.name})"
    TrajectoryLayerType.REFERENCE_GROUND_TRUTH -> "Reference [R] · evaluation only"
    TrajectoryLayerType.DISPLAY_SMOOTHED -> "Display-smoothed [D] · diagnostics only"
    TrajectoryLayerType.PLANNED_ROUTE -> "Planned route"
}

@Composable
private fun TelemetryValue(label: String, value: String) {
    Column(modifier = Modifier.size(width = 112.dp, height = 48.dp)) {
        Text(text = label, style = MaterialTheme.typography.labelMedium)
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

private fun nextSpeed(current: Float): Float {
    val speeds = ReplayNavigationViewModel.SUPPORTED_SPEED_MULTIPLIERS
    val currentIndex = speeds.indexOf(current)
    return speeds[(currentIndex + 1).mod(speeds.size)]
}

private fun formatTimestamp(timestampNs: Long): String =
    String.format(Locale.US, "%.3f s", timestampNs / 1_000_000_000.0)

private fun formatDistance(value: Double?): String =
    value?.let { String.format(Locale.US, "%.2f m", it) } ?: "UNAVAILABLE"

private fun formatSpeed(value: Double?): String =
    value?.let { String.format(Locale.US, "%.2f m/s", it) } ?: "UNAVAILABLE"

private fun formatMultiplier(value: Float): String =
    if (value % 1f == 0f) "${value.toInt()}×" else "$value×"

private val MATCHER_CLEAR = Color(0xFF24D18B)
private val MATCHER_AMBIGUOUS = Color(0xFFFFB800)
private val MATCHER_NO_CANDIDATE = Color(0xFFC7353F)
private val HEALTH_EMERALD = Color(0xFF24D18B)
private val HEALTH_AMBER = Color(0xFFF6B73C)
private val HEALTH_CRIMSON = Color(0xFFC7353F)
private val HEALTH_NEUTRAL = Color(0xFFADB5C0)

internal fun alignmentHealthColor(status: AlignmentStatusV1): Color = when (status) {
    AlignmentStatusV1.VALID -> HEALTH_EMERALD
    AlignmentStatusV1.UNCERTAIN -> HEALTH_AMBER
    AlignmentStatusV1.SLIP_SUSPECTED -> HEALTH_CRIMSON
    AlignmentStatusV1.UNINITIALIZED -> HEALTH_NEUTRAL
}

@Preview(showBackground = true, widthDp = 720, heightDp = 540)
@Composable
private fun ReplayNavigationShellPreview() {
    MaterialTheme {
        ReplayNavigationShell(state = ReplayUiState(), onIntent = {})
    }
}
