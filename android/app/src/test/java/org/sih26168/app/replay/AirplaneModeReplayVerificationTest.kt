package org.sih26168.app.replay

import java.io.File
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.sih26168.app.ReplayDisclosure
import org.sih26168.app.ui.OfflineMapAssets
import org.sih26168.app.ui.ReplayGovernanceLabels
import org.sih26168.app.ui.pinnedDisclosureLabels
import org.sih26168.app.replay.GnssFixDimension
import org.sih26168.contracts.enums.AlignmentStatusV1
import org.sih26168.contracts.enums.HealthIntegrityStateV1
import org.sih26168.contracts.enums.ModelStatusV1
import org.sih26168.contracts.enums.NavigationModeV1

/** Synthetic presentation-boundary checks; device radio isolation is verified separately. */
class AirplaneModeReplayVerificationTest {
    @Test
    fun primaryDisclosureSlotsRemainPinnedForNormalAndBlackoutPresentation() {
        val normal = ReplayUiState()
        val blackout = normal.copy(
            isOutageActive = true,
            navigationMode = NavigationModeV1.BLACKOUT_DR,
        )

        assertEquals(listOf("REPLAY"), pinnedDisclosureLabels(normal.isOutageActive))
        assertEquals(listOf("REPLAY", "SIMULATED OUTAGE"),
            pinnedDisclosureLabels(blackout.isOutageActive))
        // Instrumented Compose tests additionally measure these slots in 320dp/360dp roots.
    }

    @Test
    fun bundledStyleAndManifestDeclareOnlyLocalMapResources() {
        val main = appMainDirectory()
        val style = File(main, "assets/map/style.json").readText()
        val roads = File(main, "assets/map/local_roads.geojson")
        val manifest = File(main, "AndroidManifest.xml").readText()

        assertEquals("asset://map/style.json", OfflineMapAssets.STYLE_URI)
        assertTrue(style.contains("\"data\": \"asset://map/local_roads.geojson\""))
        assertTrue(roads.isFile)
        assertTrue(roads.readText().contains("\"FeatureCollection\""))
        assertFalse(style.contains(Regex("https?://", RegexOption.IGNORE_CASE)))
        // No remote glyph, sprite, tile, or style descriptor can be resolved at runtime.
        for (descriptor in listOf("glyphs", "sprite", "tiles", "url")) {
            assertFalse("Unexpected $descriptor descriptor", style.contains("\"$descriptor\""))
        }
        for (permission in listOf("INTERNET", "ACCESS_NETWORK_STATE", "ACCESS_WIFI_STATE")) {
            assertTrue(manifest.contains(
                "android.permission.$permission\" tools:node=\"remove\"",
            ))
        }
        assertEquals("SOURCE: DETERMINISTIC_REPLAY", ReplayGovernanceLabels.SOURCE)
        assertEquals("REPLAY MODE", ReplayGovernanceLabels.REPLAY_MODE)
        assertEquals("REPLAY", ReplayDisclosure.LABEL)
        assertEquals("© OpenStreetMap contributors", ReplayGovernanceLabels.OSM_ATTRIBUTION)
    }

    @Test
    fun syntheticOutageKeepsPlaybackAndScientificHistoryWhileRecoveryTracksMovingTarget() {
        val viewModel = ReplayNavigationViewModel()
        val origin = GeoCoordinate(0.0, 0.0)
        val firstScientific = GeoCoordinate(0.0, 0.0001)
        viewModel.onIntent(ReplayIntent.PresentTelemetry(0L, 0.0, 0.0, 2.0, 0.0, 0.0))
        viewModel.onIntent(AppendTrajectoryPointIntent(TrajectoryLayerType.RAW_GNSS, origin))
        viewModel.onIntent(AppendTrajectoryPointIntent(TrajectoryLayerType.SCIENTIFIC_FUSED, origin))
        viewModel.onIntent(ReplayIntent.Play)
        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        viewModel.onIntent(NavigationModeChangedIntent(NavigationModeV1.BLACKOUT_DR))

        val rawBeforeOutage = viewModel.uiState.value.rawGnssPath
        viewModel.onIntent(AppendTrajectoryPointIntent(
            TrajectoryLayerType.RAW_GNSS, GeoCoordinate(0.0, 0.0002),
        ))
        viewModel.onIntent(AppendTrajectoryPointIntent(
            TrajectoryLayerType.SCIENTIFIC_FUSED, firstScientific,
        ))
        viewModel.onIntent(ReplayIntent.PresentTelemetry(
            1_000_000_000L, 0.0, 11.0, 2.0, 0.0, 0.0001,
        ))
        viewModel.onIntent(PresentPositionCovarianceIntent(
            firstScientific, 16.0, 9.0, 0.0,
        ))
        val duringOutage = viewModel.uiState.value

        assertTrue(duringOutage.isReplaying)
        assertEquals(1_000_000_000L, duringOutage.currentTimestampNs)
        assertEquals(rawBeforeOutage, duringOutage.rawGnssPath)
        assertEquals(listOf(origin, firstScientific), duringOutage.scientificFusedPath)
        assertTrue(duringOutage.isSeparationTetherVisible)
        assertEquals("Separation from last trusted GNSS fix",
            TrajectoryPresentationLabels.SEPARATION_FROM_LAST_TRUSTED_GNSS_FIX)
        val ellipse = duringOutage.uncertaintyEllipse
        assertNotNull(ellipse)
        assertEquals(37, ellipse!!.polygonCoordinates.size)
        assertTrue(ellipse.polygonCoordinates.all { it.latitude in -90.0..90.0 &&
            it.longitude in -180.0..180.0 })
        viewModel.onIntent(PresentPositionCovarianceIntent(
            firstScientific, Double.MAX_VALUE, Double.MAX_VALUE, 0.0,
        ))
        assertNull(viewModel.uiState.value.uncertaintyEllipse)

        val candidates = (1..4).map { index ->
            MapCandidatePath("synthetic-$index",
                listOf(origin, GeoCoordinate(0.0, index * 0.0001)),
                (5 - index).toFloat(), false)
        }
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.AMBIGUOUS))
        viewModel.onIntent(PresentMapCandidatesIntent(candidates))
        val shownCandidates = viewModel.uiState.value.candidateTrajectories
        assertEquals(3, shownCandidates.size)
        assertEquals(1, shownCandidates.count { it.isPrimary })
        assertEquals("synthetic-1", shownCandidates.single { it.isPrimary }.candidateId)
        assertThrows(UnsupportedOperationException::class.java) {
            (shownCandidates as MutableList<MapCandidatePath>).clear()
        }

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        viewModel.onIntent(NavigationModeChangedIntent(NavigationModeV1.REACQUIRING))
        viewModel.onIntent(NavigationModeChangedIntent(
            NavigationModeV1.GNSS_AIDED, GeoCoordinate(0.0, 0.0010),
        ))
        viewModel.onIntent(ReplayIntent.PresentTelemetry(
            2_000_000_000L, 0.0, 166.0, 2.0, 0.0, 0.0015,
        ))
        val halfway = viewModel.uiState.value
        assertTrue(halfway.displayRecovery != null)
        assertTrue(halfway.displayVehicleLocation!!.longitude < halfway.vehicleLocation!!.longitude)
        assertEquals(duringOutage.scientificFusedPath, halfway.scientificFusedPath)

        viewModel.onIntent(ReplayIntent.PresentTelemetry(
            3_000_000_000L, 0.0, 222.0, 2.0, 0.0, 0.0020,
        ))
        val recovered = viewModel.uiState.value
        assertNull(recovered.displayRecovery)
        assertEquals(recovered.vehicleLocation!!.latitude,
            recovered.displayVehicleLocation!!.latitude, 1e-9)
        assertEquals(recovered.vehicleLocation.longitude,
            recovered.displayVehicleLocation.longitude, 1e-9)
        assertEquals(duringOutage.scientificFusedPath, recovered.scientificFusedPath)
    }

    @Test
    fun outageHealthPurgesStaleFixMetricsAndRetainsHonestAlignment() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(ReplayIntent.PresentTelemetry(2_000_000_000L, 0.0, 0.0, 2.0))
        viewModel.onIntent(UpdateHealthStates(
            gnss = GnssHealthState(
                integrity = HealthIntegrityStateV1.HEALTHY,
                fixDimension = GnssFixDimension.FIX_3D,
                satelliteCount = 12,
                hdop = 0.8,
                pdop = 1.2,
                trustedFixTimestampNs = 1_000_000_000L,
            ),
            alignment = AlignmentHealthState(AlignmentStatusV1.UNCERTAIN, 5.0, 0.5),
            model = ModelHealthState(ModelStatusV1.DISABLED),
        ))
        val sourceGnssHealth = viewModel.uiState.value.gnssHealth
        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        val outage = viewModel.uiState.value

        assertTrue(outage.isOutageSimulated)
        assertEquals(HealthIntegrityStateV1.HEALTHY, outage.gnssHealth.integrity)
        assertEquals(sourceGnssHealth, outage.gnssHealth)
        assertEquals(GnssFixDimension.FIX_3D, outage.gnssHealth.fixDimension)
        assertEquals(HealthIntegrityStateV1.HEALTHY, outage.displayGnssHealth.integrity)
        assertNull(outage.displayGnssHealth.fixDimension)
        assertNull(outage.displayGnssHealth.satelliteCount)
        assertNull(outage.displayGnssHealth.hdop)
        assertNull(outage.displayGnssHealth.pdop)
        assertEquals(ModelStatusV1.DISABLED, outage.modelHealth.status)
        assertEquals(1_000_000_000L, outage.trustedFixAgeNs)
        assertEquals(AlignmentStatusV1.UNCERTAIN, outage.alignmentHealth.status)
        assertEquals(AlignmentStatusV1.UNINITIALIZED,
            ReplayNavigationViewModel().uiState.value.alignmentHealth.status)
        assertNull(ReplayNavigationViewModel().uiState.value.uncertaintyEllipse)
        assertTrue(ReplayNavigationViewModel().uiState.value.candidateTrajectories.isEmpty())
    }

    @Test
    fun concurrentFrameIngestionPublishesImmutableIndependentSnapshots() {
        val viewModel = ReplayNavigationViewModel()
        val first = GeoCoordinate(0.0, 0.0)
        val mutableInput = mutableListOf(first, GeoCoordinate(0.0, 0.0001))
        viewModel.onIntent(ReplaceTrajectoryPathIntent(
            TrajectoryLayerType.SCIENTIFIC_FUSED, mutableInput,
        ))
        val firstSnapshot = viewModel.uiState.value
        mutableInput[0] = GeoCoordinate(1.0, 1.0)

        val workers = Executors.newFixedThreadPool(4)
        val start = CountDownLatch(1)
        try {
            val jobs = (1..40).map { index ->
                workers.submit(Callable {
                    start.await()
                    viewModel.onIntent(AppendTrajectoryPointIntent(
                        TrajectoryLayerType.SCIENTIFIC_FUSED,
                        GeoCoordinate(0.0, 0.0001 + index * 0.000001),
                    ))
                })
            }
            start.countDown()
            jobs.forEach { it.get(15, TimeUnit.SECONDS) }
        } finally {
            workers.shutdownNow()
        }

        val published = viewModel.uiState.value.scientificFusedPath
        assertEquals(42, published.size)
        assertEquals(first, firstSnapshot.scientificFusedPath.first())
        assertEquals(2, firstSnapshot.scientificFusedPath.size)
        assertEquals(42, published.distinct().size)
        assertThrows(UnsupportedOperationException::class.java) {
            (published as MutableList<GeoCoordinate>).clear()
        }
        assertEquals(42, viewModel.uiState.value.scientificFusedPath.size)
    }

    private fun appMainDirectory(): File {
        val cwd = File(requireNotNull(System.getProperty("user.dir")))
        return listOf(File(cwd, "src/main"), File(cwd, "app/src/main"))
            .firstOrNull { File(it, "assets/map/style.json").isFile }
            ?: error("Cannot locate bundled Android map assets from ${cwd.absolutePath}")
    }
}
