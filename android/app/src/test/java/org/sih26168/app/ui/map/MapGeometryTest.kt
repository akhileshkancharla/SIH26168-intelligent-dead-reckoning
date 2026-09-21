package org.sih26168.app.ui

import org.junit.Assert.assertTrue
import org.junit.Test
import org.maplibre.android.geometry.LatLng

class MapGeometryTest {
    @Test
    fun destinationRemainsFiniteAndBoundedAtPoles() {
        listOf(90.0, -90.0).forEach { latitude ->
            val result = destination(LatLng(latitude, 179.9999), 90.0, 35.0)
            assertTrue(result.latitude.isFinite())
            assertTrue(result.longitude.isFinite())
            assertTrue(result.latitude in -90.0..90.0)
            assertTrue(result.longitude in -180.0..180.0)
        }
    }

    @Test
    fun destinationNormalizesAcrossDateline() {
        val eastbound = destination(LatLng(0.0, 179.9999), 90.0, 35.0)
        val westbound = destination(LatLng(0.0, -179.9999), 270.0, 35.0)
        assertTrue(eastbound.longitude in -180.0..180.0)
        assertTrue(westbound.longitude in -180.0..180.0)
        assertTrue(eastbound.longitude < 0.0)
        assertTrue(westbound.longitude > 0.0)
    }
}
