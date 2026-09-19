package org.sih26168.app.ui

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import java.util.Locale
import org.sih26168.app.ReplayDisclosure
import org.sih26168.app.replay.ReplayIntent
import org.sih26168.app.replay.ReplayNavigationViewModel
import org.sih26168.app.replay.ReplayUiState

object ReplayGovernanceLabels {
    const val SOURCE = "SOURCE: DETERMINISTIC_REPLAY"
    const val DEMO = "DEMO"
    const val SIMULATED_OUTAGE = "SIMULATED OUTAGE"
    const val OSM_ATTRIBUTION = "© OpenStreetMap contributors"
}

@Composable
fun ReplayNavigationShell(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
    modifier: Modifier = Modifier,
    viewportContent: @Composable BoxScope.() -> Unit = { MapViewportPlaceholder() },
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
        TelemetryAndControlSheet(state = state, onIntent = onIntent)
    }
}

@Composable
private fun GovernanceFrame(state: ReplayUiState) {
    Surface(modifier = Modifier.fillMaxWidth(), tonalElevation = 4.dp) {
        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                GovernanceBadge(ReplayGovernanceLabels.SOURCE)
                GovernanceBadge(ReplayGovernanceLabels.DEMO)
                GovernanceBadge(ReplayDisclosure.LABEL, prominent = true)
                if (state.isOutageActive) {
                    GovernanceBadge(
                        ReplayGovernanceLabels.SIMULATED_OUTAGE,
                        prominent = true,
                    )
                }
            }
            Text(
                text = ReplayGovernanceLabels.OSM_ATTRIBUTION,
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun GovernanceBadge(label: String, prominent: Boolean = false) {
    Surface(
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
private fun BoxScope.MapViewportPlaceholder() {
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
private fun TelemetryAndControlSheet(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
) {
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
                TelemetryValue("State", if (state.isReplaying) "PLAYING" else "PAUSED")
                TelemetryValue("Time", formatTimestamp(state.currentTimestampNs))
                TelemetryValue("North", formatDistance(state.position.northMeters))
                TelemetryValue("East", formatDistance(state.position.eastMeters))
                TelemetryValue("Speed", formatSpeed(state.speedMetersPerSecond))
            }
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

@Preview(showBackground = true, widthDp = 720, heightDp = 540)
@Composable
private fun ReplayNavigationShellPreview() {
    MaterialTheme {
        ReplayNavigationShell(state = ReplayUiState(), onIntent = {})
    }
}
