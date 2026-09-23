package org.sih26168.app.replay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.sih26168.contracts.enums.NavigationModeV1
import org.sih26168.contracts.enums.AlignmentStatusV1
import androidx.compose.ui.graphics.Color
import org.sih26168.app.ui.alignmentHealthColor

class ReplayNavigationViewModelTest {
    @Test
    fun initialState_isPausedAtReplayOriginWithUnavailableTelemetry() {
        val state = ReplayNavigationViewModel().uiState.value

        assertFalse(state.isReplaying)
        assertEquals(0L, state.currentTimestampNs)
        assertEquals(1f, state.speedMultiplier)
        assertFalse(state.isOutageActive)
        assertNull(state.position.northMeters)
        assertNull(state.position.eastMeters)
        assertNull(state.speedMetersPerSecond)
        assertTrue(state.isFollowingVehicle)
        assertTrue(state.prefersCourseUp)
        assertFalse(state.isCourseUp)
        assertFalse(state.isMapReady)
        assertNull(state.lastTrustedGnssFix)
        assertEquals(GnssFixStatus.UNKNOWN, state.gnssHealth.status)
        assertEquals(AlignmentStatusV1.UNINITIALIZED, state.alignmentHealth.status)
        assertEquals(ModelStatus.UNKNOWN, state.modelHealth.status)
        assertEquals(ReplayEngineStatus.PAUSED, state.replayEngineStatus)
    }

    @Test
    fun healthTelemetry_ingestsNominalIndependentSubsystemStates() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(validMapTelemetry(timestampNs = 5_000_000_000L, headingDegrees = 0.0))
        viewModel.onIntent(UpdateHealthStates(
            gnss = GnssHealthState(GnssFixStatus.FIX_3D, 12, 0.8, 1.2, 4_000_000_000L),
            alignment = AlignmentHealthState(AlignmentStatusV1.VALID, 0.5, 1.0),
            model = ModelHealthState(ModelStatus.NOMINAL, 0.25,
                InnovationCovarianceStatus.VALID),
            replayEngine = ReplayEngineStatus.PLAYING,
        ))

        val state = viewModel.uiState.value
        assertEquals(GnssFixStatus.FIX_3D, state.displayGnssHealth.status)
        assertEquals(12, state.gnssHealth.satelliteCount)
        assertEquals(1_000_000_000L, state.trustedFixAgeNs)
        assertEquals(AlignmentStatusV1.VALID, state.alignmentHealth.status)
        assertEquals(1.0, state.alignmentHealth.convergenceProgress!!, 0.0)
        assertEquals(ModelStatus.NOMINAL, state.modelHealth.status)
        assertEquals(InnovationCovarianceStatus.VALID,
            state.modelHealth.innovationCovarianceStatus)
        assertEquals(ReplayEngineStatus.PLAYING, state.replayEngineStatus)
        assertTrue(state.isReplaying)
    }

    @Test
    fun malformedHealthTelemetry_failsClosedWithoutNonFiniteUiMetrics() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(UpdateHealthStates(
            gnss = GnssHealthState(GnssFixStatus.FIX_3D, -1, Double.NaN,
                Double.POSITIVE_INFINITY, 1L),
            alignment = AlignmentHealthState(AlignmentStatusV1.VALID,
                Double.NEGATIVE_INFINITY, 1.5),
            model = ModelHealthState(ModelStatus.NOMINAL, -0.1,
                InnovationCovarianceStatus.VALID),
        ))

        val state = viewModel.uiState.value
        assertEquals(GnssHealthState(), state.gnssHealth)
        assertEquals(AlignmentHealthState(), state.alignmentHealth)
        assertEquals(AlignmentStatusV1.UNINITIALIZED, state.alignmentHealth.status)
        assertEquals(ModelHealthState(), state.modelHealth)
        assertNull(state.trustedFixAgeNs)
    }

    @Test
    fun alignmentHealth_usesEveryContractStatusWithoutConflatingSlipAndUncertainty() {
        val viewModel = ReplayNavigationViewModel()
        for (status in listOf(
            AlignmentStatusV1.VALID,
            AlignmentStatusV1.UNCERTAIN,
            AlignmentStatusV1.SLIP_SUSPECTED,
        )) {
            viewModel.onIntent(UpdateHealthStates(
                alignment = AlignmentHealthState(status, 2.0, 0.5),
            ))
            assertEquals(status, viewModel.uiState.value.alignmentHealth.status)
        }

        viewModel.onIntent(UpdateHealthStates(
            alignment = AlignmentHealthState(
                AlignmentStatusV1.VALID,
                Double.MAX_VALUE,
                0.5,
            ),
        ))
        assertEquals(AlignmentStatusV1.UNINITIALIZED,
            viewModel.uiState.value.alignmentHealth.status)
        assertNull(viewModel.uiState.value.alignmentHealth.uncertaintyDegrees)
        assertNull(viewModel.uiState.value.alignmentHealth.convergenceProgress)
    }

    @Test
    fun alignmentHealth_badgeColorsDistinguishAllContractStatuses() {
        assertEquals(Color(0xFF24D18B), alignmentHealthColor(AlignmentStatusV1.VALID))
        assertEquals(Color(0xFFF6B73C), alignmentHealthColor(AlignmentStatusV1.UNCERTAIN))
        assertEquals(Color(0xFFC7353F), alignmentHealthColor(AlignmentStatusV1.SLIP_SUSPECTED))
        assertEquals(Color(0xFFADB5C0), alignmentHealthColor(AlignmentStatusV1.UNINITIALIZED))
    }

    @Test
    fun healthUpdates_preservePriorImmutableValuesAndOutageHonesty() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(UpdateHealthStates(
            gnss = GnssHealthState(GnssFixStatus.FIX_2D, 7, 2.0),
            alignment = AlignmentHealthState(AlignmentStatusV1.UNCERTAIN, 12.0, 0.4),
        ))
        val priorState = viewModel.uiState.value
        viewModel.onIntent(UpdateHealthStates(
            model = ModelHealthState(ModelStatus.RECOVERY_ACTIVE, 3.0,
                InnovationCovarianceStatus.DEGRADED),
            replayEngine = ReplayEngineStatus.BUFFERING,
        ))

        assertSame(priorState.gnssHealth, viewModel.uiState.value.gnssHealth)
        assertSame(priorState.alignmentHealth, viewModel.uiState.value.alignmentHealth)
        assertEquals(ModelStatus.UNKNOWN, priorState.modelHealth.status)
        assertEquals(ModelStatus.RECOVERY_ACTIVE, viewModel.uiState.value.modelHealth.status)
        assertFalse(viewModel.uiState.value.isReplaying)
        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        assertEquals(GnssFixStatus.OUTAGE_SIMULATED,
            viewModel.uiState.value.displayGnssHealth.status)
        assertNull(viewModel.uiState.value.displayGnssHealth.hdop)
        assertEquals(GnssFixStatus.FIX_2D, priorState.gnssHealth.status)
    }

    @Test
    fun playAndPause_updatePlaybackState() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.Play)
        assertTrue(viewModel.uiState.value.isReplaying)

        viewModel.onIntent(ReplayIntent.Pause)
        assertFalse(viewModel.uiState.value.isReplaying)
    }

    @Test
    fun step_advancesOneFixedIntervalOnlyWhilePaused() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.Step)
        assertEquals(
            ReplayNavigationViewModel.STEP_INTERVAL_NS,
            viewModel.uiState.value.currentTimestampNs,
        )

        viewModel.onIntent(ReplayIntent.Play)
        viewModel.onIntent(ReplayIntent.Step)
        assertEquals(
            ReplayNavigationViewModel.STEP_INTERVAL_NS,
            viewModel.uiState.value.currentTimestampNs,
        )
    }

    @Test
    fun speedMultiplier_acceptsOnlySupportedValues() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(2f))
        assertEquals(2f, viewModel.uiState.value.speedMultiplier)

        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(3f))
        assertEquals(2f, viewModel.uiState.value.speedMultiplier)
    }

    @Test
    fun simulatedOutage_toggleControlsDisclosureState() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        assertTrue(viewModel.uiState.value.isOutageActive)

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        assertFalse(viewModel.uiState.value.isOutageActive)
    }

    @Test
    fun telemetryPresentation_acceptsMonotonicFiniteValues() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(
            ReplayIntent.PresentTelemetry(
                timestampNs = 2_000_000_000L,
                northMeters = 12.5,
                eastMeters = -4.25,
                speedMetersPerSecond = 6.75,
            ),
        )

        val state = viewModel.uiState.value
        assertEquals(2_000_000_000L, state.currentTimestampNs)
        assertEquals(12.5, state.position.northMeters!!, 0.0)
        assertEquals(-4.25, state.position.eastMeters!!, 0.0)
        assertEquals(6.75, state.speedMetersPerSecond!!, 0.0)
    }

    @Test
    fun telemetryPresentation_rejectsRegressiveOrInvalidValues() {
        val viewModel = ReplayNavigationViewModel()
        val accepted = ReplayIntent.PresentTelemetry(
            timestampNs = 2_000_000_000L,
            northMeters = 12.5,
            eastMeters = -4.25,
            speedMetersPerSecond = 6.75,
        )
        viewModel.onIntent(accepted)

        viewModel.onIntent(accepted.copy(timestampNs = 1_000_000_000L))
        viewModel.onIntent(accepted.copy(timestampNs = 3_000_000_000L, northMeters = Double.NaN))
        viewModel.onIntent(accepted.copy(timestampNs = 3_000_000_000L, speedMetersPerSecond = -1.0))

        assertEquals(2_000_000_000L, viewModel.uiState.value.currentTimestampNs)
        assertEquals(12.5, viewModel.uiState.value.position.northMeters!!, 0.0)
    }

    @Test
    fun reset_restoresCompleteInitialState() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(ReplayIntent.Play)
        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        viewModel.onIntent(ReplayIntent.SetSpeedMultiplier(2f))

        viewModel.onIntent(ReplayIntent.Reset)

        assertEquals(ReplayUiState(), viewModel.uiState.value)
    }

    @Test
    fun reset_preservesLoadedMapCapability() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(MapReadyIntent)
        viewModel.onIntent(ReplayIntent.Play)

        viewModel.onIntent(ReplayIntent.Reset)

        assertEquals(ReplayUiState(isMapReady = true), viewModel.uiState.value)
    }

    @Test
    fun mapDragAndRecenter_updateFollowStateWithoutAutomaticSnapBack() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(MapDraggedIntent)
        assertFalse(viewModel.uiState.value.isFollowingVehicle)

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 1_000_000_000L, headingDegrees = 35.0),
        )
        assertFalse(viewModel.uiState.value.isFollowingVehicle)

        viewModel.onIntent(RecenterMapIntent)
        assertTrue(viewModel.uiState.value.isFollowingVehicle)
    }

    @Test
    fun validMovingStableHeading_enablesPreferredCourseUpMode() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 1_000_000_000L, headingDegrees = 370.0),
        )

        val state = viewModel.uiState.value
        assertTrue(state.isCourseUp)
        assertEquals(10.0, state.headingDegrees!!, 0.0)
        assertEquals(0.0, state.vehicleLocation!!.latitude, 0.0)
        assertEquals(0.0, state.vehicleLocation!!.longitude, 0.0)
    }

    @Test
    fun lowSpeedOrUnstableHeading_forcesNorthUpAndRestoresOnlyWhenCredible() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(validMapTelemetry(timestampNs = 1L, headingDegrees = 45.0))
        assertTrue(viewModel.uiState.value.isCourseUp)

        viewModel.onIntent(
            validMapTelemetry(
                timestampNs = 2L,
                headingDegrees = 46.0,
                speedMetersPerSecond = 0.99,
            ),
        )
        assertFalse(viewModel.uiState.value.isCourseUp)

        viewModel.onIntent(
            validMapTelemetry(
                timestampNs = 3L,
                headingDegrees = 47.0,
                isHeadingStable = false,
            ),
        )
        assertFalse(viewModel.uiState.value.isCourseUp)

        viewModel.onIntent(validMapTelemetry(timestampNs = 4L, headingDegrees = 48.0))
        assertTrue(viewModel.uiState.value.isCourseUp)
    }

    @Test
    fun cameraToggle_preservesNorthUpPreferenceAcrossTelemetryUpdates() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(validMapTelemetry(timestampNs = 1L, headingDegrees = 90.0))

        viewModel.onIntent(ToggleCameraModeIntent)
        assertFalse(viewModel.uiState.value.prefersCourseUp)
        assertFalse(viewModel.uiState.value.isCourseUp)

        viewModel.onIntent(validMapTelemetry(timestampNs = 2L, headingDegrees = 95.0))
        assertFalse(viewModel.uiState.value.isCourseUp)

        viewModel.onIntent(ToggleCameraModeIntent)
        assertTrue(viewModel.uiState.value.prefersCourseUp)
        assertTrue(viewModel.uiState.value.isCourseUp)
    }

    @Test
    fun mapReadyAndTrustedAnchorIntents_updatePresentationState() {
        val viewModel = ReplayNavigationViewModel()
        val anchor = GeoCoordinate(0.0, 0.0)

        viewModel.onIntent(MapReadyIntent)
        viewModel.onIntent(LastTrustedGnssFixIntent(anchor))

        assertTrue(viewModel.uiState.value.isMapReady)
        assertEquals(anchor, viewModel.uiState.value.lastTrustedGnssFix)
    }

    @Test
    fun invalidMapCoordinatesAndAnchor_areRejected() {
        val viewModel = ReplayNavigationViewModel()

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 1L, headingDegrees = 0.0).copy(
                latitudeDegrees = 91.0,
            ),
        )
        viewModel.onIntent(LastTrustedGnssFixIntent(GeoCoordinate(0.0, 181.0)))

        assertEquals(0L, viewModel.uiState.value.currentTimestampNs)
        assertNull(viewModel.uiState.value.vehicleLocation)
        assertNull(viewModel.uiState.value.lastTrustedGnssFix)
    }

    @Test
    fun trajectoryLayers_defaultToCleanViewAndToggleIndependently() {
        val viewModel = ReplayNavigationViewModel()

        assertEquals(DEFAULT_TRAJECTORY_LAYERS, viewModel.uiState.value.enabledLayers)
        assertEquals(
            setOf(TrajectoryLayerType.SCIENTIFIC_FUSED, TrajectoryLayerType.PLANNED_ROUTE),
            viewModel.uiState.value.enabledLayers,
        )

        viewModel.onIntent(ToggleTrajectoryLayerIntent(TrajectoryLayerType.RAW_GNSS))
        assertTrue(TrajectoryLayerType.RAW_GNSS in viewModel.uiState.value.enabledLayers)

        viewModel.onIntent(ToggleTrajectoryLayerIntent(TrajectoryLayerType.SCIENTIFIC_FUSED))
        assertFalse(TrajectoryLayerType.SCIENTIFIC_FUSED in viewModel.uiState.value.enabledLayers)
        assertTrue(TrajectoryLayerType.PLANNED_ROUTE in viewModel.uiState.value.enabledLayers)
    }

    @Test
    fun mapMatchedLayer_isVisibleOnlyWhenEnabledAndMatcherIsClear() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(ToggleTrajectoryLayerIntent(TrajectoryLayerType.MAP_MATCHED))

        assertFalse(
            viewModel.uiState.value.isTrajectoryLayerVisible(TrajectoryLayerType.MAP_MATCHED),
        )
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.AMBIGUOUS))
        assertFalse(
            viewModel.uiState.value.isTrajectoryLayerVisible(TrajectoryLayerType.MAP_MATCHED),
        )
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.CLEAR))
        assertTrue(
            viewModel.uiState.value.isTrajectoryLayerVisible(TrajectoryLayerType.MAP_MATCHED),
        )
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.NO_CANDIDATE))
        assertFalse(
            viewModel.uiState.value.isTrajectoryLayerVisible(TrajectoryLayerType.MAP_MATCHED),
        )
    }

    @Test
    fun trajectoryIngestion_copiesBuffersAndPreservesScientificHistoryDuringRecovery() {
        val viewModel = ReplayNavigationViewModel()
        val input = mutableListOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 0.001))
        viewModel.onIntent(
            ReplaceTrajectoryPathIntent(TrajectoryLayerType.SCIENTIFIC_FUSED, input),
        )
        input += GeoCoordinate(0.0, 0.002)
        val scientificHistory = viewModel.uiState.value.scientificFusedPath
        assertEquals(2, scientificHistory.size)

        viewModel.onIntent(
            ReplaceTrajectoryPathIntent(
                TrajectoryLayerType.SCIENTIFIC_FUSED,
                listOf(GeoCoordinate(1.0, 1.0)),
            ),
        )
        assertSame(scientificHistory, viewModel.uiState.value.scientificFusedPath)

        viewModel.onIntent(validMapTelemetry(timestampNs = 0L, headingDegrees = 90.0))
        viewModel.onIntent(NavigationModeChangedIntent(NavigationModeV1.REACQUIRING))
        viewModel.onIntent(
            NavigationModeChangedIntent(
                mode = NavigationModeV1.GNSS_AIDED,
                acceptedFix = GeoCoordinate(0.0, 0.002),
            ),
        )
        viewModel.onIntent(
            validMapTelemetry(timestampNs = 1_000_000_000L, headingDegrees = 90.0).copy(
                longitudeDegrees = 0.002,
            ),
        )

        val halfway = viewModel.uiState.value
        assertSame(scientificHistory, halfway.scientificFusedPath)
        assertEquals(0.001, halfway.displayVehicleLocation!!.longitude, 0.000_000_1)
        assertEquals(2, halfway.displaySmoothedPath.size)
        assertTrue(halfway.displayRecovery != null)

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 2_000_000_000L, headingDegrees = 90.0).copy(
                longitudeDegrees = 0.002,
            ),
        )
        val complete = viewModel.uiState.value
        assertSame(scientificHistory, complete.scientificFusedPath)
        assertEquals(0.002, complete.displayVehicleLocation!!.longitude, 0.000_000_1)
        assertNull(complete.displayRecovery)
    }

    @Test
    fun scientificHistoryCannotBeMutatedThroughPublishedState() {
        val viewModel = ReplayNavigationViewModel()
        val source = mutableListOf(GeoCoordinate(0.0, 0.0))
        viewModel.onIntent(
            ReplaceTrajectoryPathIntent(TrajectoryLayerType.SCIENTIFIC_FUSED, source),
        )
        val history = viewModel.uiState.value.scientificFusedPath
        source[0] = GeoCoordinate(1.0, 1.0)

        assertEquals(GeoCoordinate(0.0, 0.0), history.single())
        assertThrows(UnsupportedOperationException::class.java) {
            (history as MutableList<GeoCoordinate>)[0] = GeoCoordinate(2.0, 2.0)
        }
        assertEquals(GeoCoordinate(0.0, 0.0), viewModel.uiState.value.scientificFusedPath.single())
    }

    @Test
    fun displayRecoveryDecaysOffsetAgainstMovingScientificLocation() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(validMapTelemetry(timestampNs = 0L, headingDegrees = 90.0))
        viewModel.onIntent(NavigationModeChangedIntent(NavigationModeV1.REACQUIRING))
        viewModel.onIntent(
            NavigationModeChangedIntent(
                NavigationModeV1.GNSS_AIDED,
                acceptedFix = GeoCoordinate(0.0, 0.002),
            ),
        )

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 1_000_000_000L, headingDegrees = 90.0).copy(
                longitudeDegrees = 0.003,
            ),
        )
        val halfway = viewModel.uiState.value
        assertEquals(0.003, halfway.vehicleLocation!!.longitude, 1e-9)
        assertEquals(0.002, halfway.displayVehicleLocation!!.longitude, 1e-9)
        assertTrue(halfway.displayRecovery != null)

        viewModel.onIntent(
            validMapTelemetry(timestampNs = 2_000_000_000L, headingDegrees = 90.0).copy(
                longitudeDegrees = 0.004,
            ),
        )
        val complete = viewModel.uiState.value
        assertEquals(0.004, complete.displayVehicleLocation!!.longitude, 1e-9)
        assertNull(complete.displayRecovery)
    }

    @Test
    fun outageFreezesRawGnssAndUsesSeparationSemanticsForTether() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(validMapTelemetry(timestampNs = 1L, headingDegrees = 90.0))
        viewModel.onIntent(
            AppendTrajectoryPointIntent(
                TrajectoryLayerType.RAW_GNSS,
                GeoCoordinate(0.0, 0.0),
            ),
        )

        viewModel.onIntent(ReplayIntent.ToggleSimulatedOutage)
        val outageState = viewModel.uiState.value
        assertEquals(GeoCoordinate(0.0, 0.0), outageState.lastTrustedGnssFix)
        assertTrue(outageState.isSeparationTetherVisible)
        assertEquals(
            "Separation from last trusted GNSS fix",
            TrajectoryPresentationLabels.SEPARATION_FROM_LAST_TRUSTED_GNSS_FIX,
        )
        assertFalse(
            TrajectoryPresentationLabels.SEPARATION_FROM_LAST_TRUSTED_GNSS_FIX
                .contains("drift", ignoreCase = true),
        )

        viewModel.onIntent(
            AppendTrajectoryPointIntent(
                TrajectoryLayerType.RAW_GNSS,
                GeoCoordinate(0.0, 0.001),
            ),
        )
        assertEquals(1, viewModel.uiState.value.rawGnssPath.size)
    }

    @Test
    fun covarianceEllipse_calculatesTwoSigmaEigenAxesAndClosedBoundary() {
        val ellipse = calculateTwoSigmaCovarianceEllipse(
            center = GeoCoordinate(12.0, 77.0),
            pxx = 5.0,
            pyy = 5.0,
            pxy = 3.0,
        )!!

        assertEquals(2.0 * kotlin.math.sqrt(8.0), ellipse.semiMajorMeters, 1e-9)
        assertEquals(2.0 * kotlin.math.sqrt(2.0), ellipse.semiMinorMeters, 1e-9)
        assertEquals(45.0, ellipse.orientationDegrees, 1e-9)
        assertEquals(37, ellipse.polygonCoordinates.size)
        assertEquals(ellipse.polygonCoordinates.first(), ellipse.polygonCoordinates.last())
    }

    @Test
    fun covarianceEllipse_rejectsFiniteInputsWhoseDerivedValuesOverflow() {
        assertNull(calculateTwoSigmaCovarianceEllipse(
            GeoCoordinate(0.0, 0.0), Double.MAX_VALUE, Double.MAX_VALUE, 0.0,
        ))
        assertNull(calculateTwoSigmaCovarianceEllipse(
            GeoCoordinate(0.0, 0.0), Double.MAX_VALUE, 0.0, Double.MAX_VALUE,
        ))
        assertNull(calculateTwoSigmaCovarianceEllipse(
            GeoCoordinate(0.0, 0.0), 1e308, 0.0, 0.0,
        ))
    }

    @Test
    fun clearMatcherStatus_suppressesEveryAlternativeCandidate() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.CLEAR))
        viewModel.onIntent(PresentMapCandidatesIntent(candidateFixture()))

        val candidates = viewModel.uiState.value.candidateTrajectories
        assertEquals(1, candidates.size)
        assertTrue(candidates.single().isPrimary)
        assertEquals("primary", candidates.single().candidateId)
        assertEquals(1f, candidates.single().likelihoodScore)
    }

    @Test
    fun ambiguousMatcherStatus_retainsTopThreeNormalizedCandidateBranches() {
        val viewModel = ReplayNavigationViewModel()
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.AMBIGUOUS))
        viewModel.onIntent(PresentMapCandidatesIntent(candidateFixture()))

        val candidates = viewModel.uiState.value.candidateTrajectories
        assertEquals(3, candidates.size)
        assertTrue(candidates.any { !it.isPrimary })
        assertEquals(1.0, candidates.sumOf { it.likelihoodScore.toDouble() }, 1e-6)
        assertEquals(listOf("primary", "alternative-a", "alternative-b"), candidates.map { it.candidateId })
    }

    @Test
    fun ambiguousMatcherStatus_normalizesZeroAndMultiplePrimaries() {
        val noneMarked = gateMapCandidates(
            MapMatcherStatus.AMBIGUOUS,
            candidateFixture().map { it.copy(isPrimary = false) },
        )
        val allMarked = gateMapCandidates(
            MapMatcherStatus.AMBIGUOUS,
            candidateFixture().map { it.copy(isPrimary = true) },
        )
        for (candidates in listOf(noneMarked, allMarked)) {
            assertEquals(3, candidates.size)
            assertEquals(listOf("primary"), candidates.filter { it.isPrimary }.map { it.candidateId })
            assertEquals(2, candidates.count { !it.isPrimary })
            assertEquals(1.0, candidates.sumOf { it.likelihoodScore.toDouble() }, 1e-6)
        }
    }

    @Test
    fun candidateOutputCannotBeMutatedThroughPublishedState() {
        val viewModel = ReplayNavigationViewModel()
        val source = mutableListOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 0.001))
        viewModel.onIntent(SetMapMatcherStatusIntent(MapMatcherStatus.AMBIGUOUS))
        viewModel.onIntent(PresentMapCandidatesIntent(listOf(
            MapCandidatePath("primary", source, 1f, true),
        )))
        source[0] = GeoCoordinate(1.0, 1.0)
        val output = viewModel.uiState.value.candidateTrajectories
        assertEquals(GeoCoordinate(0.0, 0.0), output.single().coordinates.first())
        assertThrows(UnsupportedOperationException::class.java) {
            (output as MutableList<MapCandidatePath>).clear()
        }
        assertThrows(UnsupportedOperationException::class.java) {
            (output.single().coordinates as MutableList<GeoCoordinate>)[0] =
                GeoCoordinate(2.0, 2.0)
        }
    }

    @Test
    fun diagnosticOverlayToggles_updateVisibilityWithoutChangingScientificState() {
        val viewModel = ReplayNavigationViewModel()
        val scientificHistory = viewModel.uiState.value.scientificFusedPath

        viewModel.onIntent(ToggleUncertaintyEllipse(false))
        viewModel.onIntent(ToggleCandidateBranches(true))

        val state = viewModel.uiState.value
        assertFalse(state.showUncertaintyEllipse)
        assertTrue(state.showCandidateBranches)
        assertSame(scientificHistory, state.scientificFusedPath)
    }

    private fun candidateFixture(): List<MapCandidatePath> = listOf(
        MapCandidatePath(
            candidateId = "primary",
            coordinates = listOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 0.001)),
            likelihoodScore = 0.5f,
            isPrimary = true,
        ),
        MapCandidatePath(
            candidateId = "alternative-a",
            coordinates = listOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.001, 0.001)),
            likelihoodScore = 0.3f,
            isPrimary = false,
        ),
        MapCandidatePath(
            candidateId = "alternative-b",
            coordinates = listOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(-0.001, 0.001)),
            likelihoodScore = 0.15f,
            isPrimary = false,
        ),
        MapCandidatePath(
            candidateId = "alternative-c",
            coordinates = listOf(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.002, 0.001)),
            likelihoodScore = 0.05f,
            isPrimary = false,
        ),
    )

    private fun validMapTelemetry(
        timestampNs: Long,
        headingDegrees: Double,
        speedMetersPerSecond: Double = 5.0,
        isHeadingStable: Boolean = true,
    ) = ReplayIntent.PresentTelemetry(
        timestampNs = timestampNs,
        northMeters = 0.0,
        eastMeters = 0.0,
        speedMetersPerSecond = speedMetersPerSecond,
        latitudeDegrees = 0.0,
        longitudeDegrees = 0.0,
        headingDegrees = headingDegrees,
        isHeadingStable = isHeadingStable,
    )
}
