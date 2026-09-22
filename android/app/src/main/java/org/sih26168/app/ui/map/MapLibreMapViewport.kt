package org.sih26168.app.ui

import android.content.ComponentCallbacks2
import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.os.Bundle
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.savedstate.SavedStateRegistryOwner
import kotlin.math.cos
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.sin
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.gestures.MoveGestureDetector
import org.maplibre.android.gestures.StandardScaleGestureDetector
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapLibreMapOptions
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleOpacity
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillOpacity
import org.maplibre.android.style.layers.PropertyFactory.iconAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.iconImage
import org.maplibre.android.style.layers.PropertyFactory.iconRotate
import org.maplibre.android.style.layers.PropertyFactory.iconRotationAlignment
import org.maplibre.android.style.layers.PropertyFactory.iconSize
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineDasharray
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point
import org.maplibre.geojson.Polygon
import org.sih26168.app.replay.MapDraggedIntent
import org.sih26168.app.replay.MapReadyIntent
import org.sih26168.app.replay.RecenterMapIntent
import org.sih26168.app.replay.GeoCoordinate
import org.sih26168.app.replay.ReplayIntent
import org.sih26168.app.replay.ReplayUiState
import org.sih26168.app.replay.ToggleCameraModeIntent
import org.sih26168.app.replay.TrajectoryLayerType
import org.sih26168.app.replay.isTrajectoryLayerVisible

@Composable
fun BoxScope.MapLibreMapViewport(
    state: ReplayUiState,
    onIntent: (ReplayIntent) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val savedStateOwner = context.findSavedStateRegistryOwner()
    val restoredState = remember {
        savedStateOwner.savedStateRegistry.consumeRestoredStateForKey(MAP_SAVED_STATE_KEY)
    }
    val mapView = remember {
        MapLibre.getInstance(context.applicationContext)
        MapView(
            context,
            MapLibreMapOptions.createFromAttributes(context)
                .attributionEnabled(false)
                .compassEnabled(false)
                .logoEnabled(false)
                .zoomGesturesEnabled(true)
                .scrollGesturesEnabled(true)
                .rotateGesturesEnabled(false)
                .tiltGesturesEnabled(false),
        ).also { it.onCreate(restoredState) }
    }
    val controller = remember(mapView) { MapLibreViewportController(mapView) }

    SideEffect {
        controller.onIntent = onIntent
        controller.render(state)
    }

    DisposableEffect(mapView, lifecycleOwner, savedStateOwner) {
        val lifecycleBridge = MapViewLifecycleBridge(mapView)
        val memoryBridge = MapViewMemoryBridge(mapView)
        lifecycleOwner.lifecycle.addObserver(lifecycleBridge)
        context.applicationContext.registerComponentCallbacks(memoryBridge)
        savedStateOwner.savedStateRegistry.registerSavedStateProvider(MAP_SAVED_STATE_KEY) {
            Bundle().also(mapView::onSaveInstanceState)
        }
        controller.initialize()

        onDispose {
            savedStateOwner.savedStateRegistry.unregisterSavedStateProvider(MAP_SAVED_STATE_KEY)
            lifecycleOwner.lifecycle.removeObserver(lifecycleBridge)
            context.applicationContext.unregisterComponentCallbacks(memoryBridge)
            controller.destroy()
            lifecycleBridge.destroy()
        }
    }

    AndroidView(
        factory = { mapView },
        modifier = Modifier.fillMaxSize(),
        update = { controller.render(state) },
    )

    Column(
        modifier = Modifier
            .align(Alignment.TopEnd)
            .padding(12.dp),
        horizontalAlignment = Alignment.End,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ExtendedFloatingActionButton(
            onClick = { onIntent(ToggleCameraModeIntent) },
            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
            contentColor = MaterialTheme.colorScheme.onSurface,
        ) {
            Text(if (state.isCourseUp) "Course-up · 3D" else "North-up · 2D")
        }
        if (!state.isFollowingVehicle) {
            ExtendedFloatingActionButton(
                onClick = { onIntent(RecenterMapIntent) },
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            ) {
                Text("Re-center")
            }
        }
    }
}

private class MapLibreViewportController(private val mapView: MapView) {
    var onIntent: (ReplayIntent) -> Unit = {}

    private var map: MapLibreMap? = null
    private var style: Style? = null
    private var latestState = ReplayUiState()
    private var initialized = false
    private var destroyed = false
    private val renderedTrajectoryPaths = mutableMapOf<String, RenderedTrajectoryPath>()

    fun initialize() {
        if (initialized) return
        initialized = true
        mapView.getMapAsync { readyMap ->
            if (destroyed) return@getMapAsync
            map = readyMap
            configureGestures(readyMap)
            readyMap.setStyle(Style.Builder().fromUri(LOCAL_STYLE_URI)) { readyStyle ->
                if (destroyed) return@setStyle
                style = readyStyle
                installNavigationLayers(readyStyle)
                onIntent(MapReadyIntent)
                render(latestState)
            }
        }
    }

    fun render(state: ReplayUiState) {
        latestState = state
        updateNavigationSources(state)
        updateCamera(state)
    }

    fun destroy() {
        destroyed = true
        map = null
        style = null
        renderedTrajectoryPaths.clear()
    }

    private fun configureGestures(readyMap: MapLibreMap) {
        readyMap.uiSettings.apply {
            isZoomGesturesEnabled = true
            isScrollGesturesEnabled = true
            isRotateGesturesEnabled = false
            isTiltGesturesEnabled = false
            isCompassEnabled = false
            isAttributionEnabled = false
            isLogoEnabled = false
        }
        readyMap.addOnMoveListener(
            object : MapLibreMap.OnMoveListener {
                override fun onMoveBegin(detector: MoveGestureDetector) {
                    onIntent(MapDraggedIntent)
                }

                override fun onMove(detector: MoveGestureDetector) = Unit

                override fun onMoveEnd(detector: MoveGestureDetector) = Unit
            },
        )
        readyMap.addOnScaleListener(
            object : MapLibreMap.OnScaleListener {
                override fun onScaleBegin(detector: StandardScaleGestureDetector) {
                    onIntent(MapDraggedIntent)
                }

                override fun onScale(detector: StandardScaleGestureDetector) = Unit

                override fun onScaleEnd(detector: StandardScaleGestureDetector) = Unit
            },
        )
    }

    private fun installNavigationLayers(readyStyle: Style) {
        readyStyle.addImage(VEHICLE_IMAGE_ID, createVehicleChevron())
        readyStyle.addSource(emptySource(PLANNED_ROUTE_SOURCE_ID))
        readyStyle.addSource(emptySource(REFERENCE_SOURCE_ID))
        readyStyle.addSource(emptySource(RAW_GNSS_SOURCE_ID))
        readyStyle.addSource(emptySource(MAP_MATCHED_SOURCE_ID))
        readyStyle.addSource(emptySource(SCIENTIFIC_FUSED_SOURCE_ID))
        readyStyle.addSource(emptySource(DISPLAY_SMOOTHED_SOURCE_ID))
        readyStyle.addSource(emptySource(HEADING_CONE_SOURCE_ID))
        readyStyle.addSource(emptySource(TETHER_SOURCE_ID))
        readyStyle.addSource(emptySource(ANCHOR_SOURCE_ID))
        readyStyle.addSource(emptySource(VEHICLE_SOURCE_ID))

        readyStyle.addLayer(
            LineLayer(PLANNED_ROUTE_LAYER_ID, PLANNED_ROUTE_SOURCE_ID).withProperties(
                lineColor(PLANNED_ROUTE_BLUE),
                lineWidth(3f),
            ),
        )
        readyStyle.addLayer(
            LineLayer(REFERENCE_LAYER_ID, REFERENCE_SOURCE_ID).withProperties(
                lineColor(REFERENCE_SILVER),
                lineWidth(2f),
                lineDasharray(arrayOf(3f, 2f)),
            ),
        )
        readyStyle.addLayer(
            LineLayer(RAW_GNSS_LAYER_ID, RAW_GNSS_SOURCE_ID).withProperties(
                lineColor(RAW_GNSS_ORANGE),
                lineWidth(3f),
                lineDasharray(arrayOf(0.5f, 1.5f)),
            ),
        )
        readyStyle.addLayer(
            LineLayer(MAP_MATCHED_LAYER_ID, MAP_MATCHED_SOURCE_ID).withProperties(
                lineColor(MAP_MATCHED_EMERALD),
                lineWidth(3.5f),
            ),
        )
        readyStyle.addLayer(
            LineLayer(SCIENTIFIC_FUSED_LAYER_ID, SCIENTIFIC_FUSED_SOURCE_ID).withProperties(
                lineColor(CYAN),
                lineWidth(4f),
            ),
        )
        readyStyle.addLayer(
            LineLayer(DISPLAY_SMOOTHED_LAYER_ID, DISPLAY_SMOOTHED_SOURCE_ID).withProperties(
                lineColor(DISPLAY_SMOOTHED_PURPLE),
                lineWidth(2.5f),
            ),
        )
        readyStyle.addLayer(
            FillLayer(HEADING_CONE_LAYER_ID, HEADING_CONE_SOURCE_ID).withProperties(
                fillColor(CYAN),
                fillOpacity(0.20f),
            ),
        )
        readyStyle.addLayer(
            LineLayer(TETHER_LAYER_ID, TETHER_SOURCE_ID).withProperties(
                lineColor(AMBER),
                lineWidth(2.5f),
                lineDasharray(arrayOf(2f, 2f)),
            ),
        )
        readyStyle.addLayer(
            CircleLayer(ANCHOR_LAYER_ID, ANCHOR_SOURCE_ID).withProperties(
                circleRadius(8f),
                circleColor(Color.TRANSPARENT),
                circleOpacity(1f),
                circleStrokeColor(AMBER),
                circleStrokeWidth(3f),
            ),
        )
        readyStyle.addLayer(
            SymbolLayer(VEHICLE_LAYER_ID, VEHICLE_SOURCE_ID).withProperties(
                iconImage(VEHICLE_IMAGE_ID),
                iconSize(0.8f),
                iconRotate(get(HEADING_PROPERTY)),
                iconRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP),
                iconAllowOverlap(true),
            ),
        )
    }

    private fun updateNavigationSources(state: ReplayUiState) {
        val readyStyle = style ?: return
        updateTrajectorySources(readyStyle, state)
        val location = state.displayVehicleLocation ?: state.vehicleLocation
        val heading = state.headingDegrees ?: 0.0

        readyStyle.source(VEHICLE_SOURCE_ID)?.setGeoJson(
            if (location == null) {
                emptyFeatureCollection()
            } else {
                FeatureCollection.fromFeature(
                    Feature.fromGeometry(location.toPoint()).apply {
                        addNumberProperty(HEADING_PROPERTY, heading)
                    },
                )
            },
        )
        readyStyle.source(HEADING_CONE_SOURCE_ID)?.setGeoJson(
            if (location == null || !state.isHeadingStable) {
                emptyFeatureCollection()
            } else {
                headingCone(location.toLatLng(), heading)?.let { polygon ->
                    FeatureCollection.fromFeature(Feature.fromGeometry(polygon))
                } ?: emptyFeatureCollection()
            },
        )

        val anchor = state.lastTrustedGnssFix.takeIf { state.isOutageActive }
        readyStyle.source(ANCHOR_SOURCE_ID)?.setGeoJson(
            anchor?.let { FeatureCollection.fromFeature(Feature.fromGeometry(it.toPoint())) }
                ?: emptyFeatureCollection(),
        )
        readyStyle.source(TETHER_SOURCE_ID)?.setGeoJson(
            if (anchor != null && location != null) {
                FeatureCollection.fromFeature(
                    Feature.fromGeometry(LineString.fromLngLats(listOf(anchor.toPoint(), location.toPoint()))),
                )
            } else {
                emptyFeatureCollection()
            },
        )
    }

    private fun updateTrajectorySources(readyStyle: Style, state: ReplayUiState) {
        updateTrajectorySource(
            readyStyle,
            PLANNED_ROUTE_SOURCE_ID,
            state.plannedRoutePath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.PLANNED_ROUTE),
        )
        updateTrajectorySource(
            readyStyle,
            SCIENTIFIC_FUSED_SOURCE_ID,
            state.scientificFusedPath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.SCIENTIFIC_FUSED),
        )
        updateTrajectorySource(
            readyStyle,
            RAW_GNSS_SOURCE_ID,
            state.rawGnssPath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.RAW_GNSS),
        )
        updateTrajectorySource(
            readyStyle,
            MAP_MATCHED_SOURCE_ID,
            state.mapMatchedPath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.MAP_MATCHED),
        )
        updateTrajectorySource(
            readyStyle,
            REFERENCE_SOURCE_ID,
            state.referencePath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.REFERENCE_GROUND_TRUTH),
        )
        updateTrajectorySource(
            readyStyle,
            DISPLAY_SMOOTHED_SOURCE_ID,
            state.displaySmoothedPath,
            state.isTrajectoryLayerVisible(TrajectoryLayerType.DISPLAY_SMOOTHED),
        )
    }

    private fun updateTrajectorySource(
        readyStyle: Style,
        sourceId: String,
        path: List<GeoCoordinate>,
        visible: Boolean,
    ) {
        val previous = renderedTrajectoryPaths[sourceId]
        if (previous?.visible == visible && previous.path === path) return

        readyStyle.source(sourceId)?.setGeoJson(
            if (visible && path.size >= 2) {
                FeatureCollection.fromFeature(
                    Feature.fromGeometry(LineString.fromLngLats(path.map(GeoCoordinate::toPoint))),
                )
            } else {
                emptyFeatureCollection()
            },
        )
        renderedTrajectoryPaths[sourceId] = RenderedTrajectoryPath(path, visible)
    }

    private fun updateCamera(state: ReplayUiState) {
        val readyMap = map ?: return
        if (!state.isFollowingVehicle) return

        val target = (state.displayVehicleLocation ?: state.vehicleLocation)?.toLatLng()
            ?: DEFAULT_CAMERA_TARGET
        val courseUp = state.isCourseUp && state.headingDegrees != null
        val topPadding = if (courseUp) mapView.height * VEHICLE_VERTICAL_OFFSET_FRACTION else 0.0
        val camera = CameraPosition.Builder()
            .target(target)
            .zoom(if (courseUp) COURSE_UP_ZOOM else NORTH_UP_ZOOM)
            .bearing(if (courseUp) state.headingDegrees!! else 0.0)
            .tilt(if (courseUp) COURSE_UP_TILT_DEGREES else 0.0)
            .padding(0.0, topPadding, 0.0, 0.0)
            .build()
        readyMap.moveCamera(CameraUpdateFactory.newCameraPosition(camera))
    }

    private fun Style.source(id: String): GeoJsonSource? = getSourceAs(id)

    private fun emptySource(id: String) = GeoJsonSource(id, emptyFeatureCollection())

    companion object {
        private const val LOCAL_STYLE_URI = "asset://map/style.json"
        private const val CYAN = "#00D9FF"
        private const val AMBER = "#F6B73C"
        private const val PLANNED_ROUTE_BLUE = "#5B8CFF"
        private const val RAW_GNSS_ORANGE = "#FF7A45"
        private const val MAP_MATCHED_EMERALD = "#24D18B"
        private const val REFERENCE_SILVER = "#E6EDF7"
        private const val DISPLAY_SMOOTHED_PURPLE = "#A78BFA"
        private const val VEHICLE_SOURCE_ID = "active-vehicle-source"
        private const val VEHICLE_LAYER_ID = "active-vehicle-layer"
        private const val VEHICLE_IMAGE_ID = "active-vehicle-chevron"
        private const val HEADING_PROPERTY = "heading"
        private const val PLANNED_ROUTE_SOURCE_ID = "planned-route-source"
        private const val PLANNED_ROUTE_LAYER_ID = "planned-route-layer"
        private const val SCIENTIFIC_FUSED_SOURCE_ID = "scientific-fused-source"
        private const val SCIENTIFIC_FUSED_LAYER_ID = "scientific-fused-layer"
        private const val RAW_GNSS_SOURCE_ID = "raw-gnss-source"
        private const val RAW_GNSS_LAYER_ID = "raw-gnss-layer"
        private const val MAP_MATCHED_SOURCE_ID = "map-matched-source"
        private const val MAP_MATCHED_LAYER_ID = "map-matched-layer"
        private const val REFERENCE_SOURCE_ID = "reference-ground-truth-source"
        private const val REFERENCE_LAYER_ID = "reference-ground-truth-layer"
        private const val DISPLAY_SMOOTHED_SOURCE_ID = "display-smoothed-source"
        private const val DISPLAY_SMOOTHED_LAYER_ID = "display-smoothed-layer"
        private const val HEADING_CONE_SOURCE_ID = "heading-cone-source"
        private const val HEADING_CONE_LAYER_ID = "heading-cone-layer"
        private const val ANCHOR_SOURCE_ID = "last-trusted-gnss-source"
        private const val ANCHOR_LAYER_ID = "last-trusted-gnss-layer"
        private const val TETHER_SOURCE_ID = "gnss-anchor-tether-source"
        private const val TETHER_LAYER_ID = "gnss-anchor-tether-layer"
        private const val COURSE_UP_TILT_DEGREES = 48.0
        private const val COURSE_UP_ZOOM = 17.5
        private const val NORTH_UP_ZOOM = 16.0
        private const val VEHICLE_VERTICAL_OFFSET_FRACTION = 0.28
        private val DEFAULT_CAMERA_TARGET = LatLng(0.0, 0.0)
    }

    private data class RenderedTrajectoryPath(
        val path: List<GeoCoordinate>,
        val visible: Boolean,
    )
}

private class MapViewLifecycleBridge(private val mapView: MapView) : DefaultLifecycleObserver {
    private var destroyed = false

    override fun onStart(owner: LifecycleOwner) = mapView.onStart()

    override fun onResume(owner: LifecycleOwner) = mapView.onResume()

    override fun onPause(owner: LifecycleOwner) = mapView.onPause()

    override fun onStop(owner: LifecycleOwner) = mapView.onStop()

    override fun onDestroy(owner: LifecycleOwner) = destroy()

    fun destroy() {
        if (!destroyed) {
            destroyed = true
            mapView.onDestroy()
        }
    }
}

@Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
private class MapViewMemoryBridge(private val mapView: MapView) : ComponentCallbacks2 {
    override fun onConfigurationChanged(newConfig: Configuration) = Unit

    override fun onLowMemory() = mapView.onLowMemory()

    override fun onTrimMemory(level: Int) {
        if (level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL) {
            mapView.onLowMemory()
        }
    }
}

private fun Context.findSavedStateRegistryOwner(): SavedStateRegistryOwner {
    var current = this
    while (current is android.content.ContextWrapper) {
        if (current is SavedStateRegistryOwner) return current
        current = current.baseContext
    }
    check(current is SavedStateRegistryOwner) { "Map viewport requires a SavedStateRegistryOwner" }
    return current
}

private fun LatLng.toPoint(): Point = Point.fromLngLat(longitude, latitude)

private fun GeoCoordinate.toPoint(): Point = Point.fromLngLat(longitude, latitude)

private fun GeoCoordinate.toLatLng(): LatLng = LatLng(latitude, longitude)

private fun emptyFeatureCollection(): FeatureCollection =
    FeatureCollection.fromFeatures(emptyArray())

/**
 * Builds presentation-only heading geometry. A cone that crosses the antimeridian is suppressed
 * instead of emitting a normalized GeoJSON ring that MapLibre could fill across the world.
 */
internal fun headingCone(origin: LatLng, headingDegrees: Double): Polygon? {
    val left = destination(origin, headingDegrees - 18.0, 35.0)
    val right = destination(origin, headingDegrees + 18.0, 35.0)
    val ring = listOf(origin, left, right, origin)
    val crossesAntimeridian = listOf(left, right).any { destination ->
        kotlin.math.abs(origin.longitude - destination.longitude) > 180.0
    } || ring.zipWithNext().any { (start, end) ->
        kotlin.math.abs(start.longitude - end.longitude) > 180.0
    }
    if (crossesAntimeridian) return null

    val longitudes = ring.map { it.longitude }
    val longitudeSpan = longitudes.maxOrNull()!! - longitudes.minOrNull()!!
    if (longitudeSpan >= MAX_HEADING_CONE_LONGITUDE_SPAN_DEGREES) return null

    return Polygon.fromLngLats(listOf(ring.map(LatLng::toPoint)))
}

internal fun destination(origin: LatLng, bearingDegrees: Double, distanceMeters: Double): LatLng {
    val bearingRadians = Math.toRadians(bearingDegrees)
    val angularDistance = distanceMeters / EARTH_RADIUS_METERS
    val latitudeRadians = Math.toRadians(origin.latitude)
    val longitudeRadians = Math.toRadians(origin.longitude)
    val destinationLatitude = asin(
        sin(latitudeRadians) * cos(angularDistance) +
            cos(latitudeRadians) * sin(angularDistance) * cos(bearingRadians),
    )
    val destinationLongitude = longitudeRadians + atan2(
        sin(bearingRadians) * sin(angularDistance) * cos(latitudeRadians),
        cos(angularDistance) - sin(latitudeRadians) * sin(destinationLatitude),
    )
    val normalizedLongitude =
        ((Math.toDegrees(destinationLongitude) + 540.0) % 360.0) - 180.0
    return LatLng(Math.toDegrees(destinationLatitude), normalizedLongitude)
}

private fun createVehicleChevron(): Bitmap {
    val bitmap = Bitmap.createBitmap(72, 72, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00D9FF")
        style = Paint.Style.FILL
    }
    val outline = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.STROKE
        strokeWidth = 4f
        strokeJoin = Paint.Join.ROUND
    }
    val path = android.graphics.Path().apply {
        moveTo(36f, 5f)
        lineTo(62f, 62f)
        lineTo(36f, 51f)
        lineTo(10f, 62f)
        close()
    }
    canvas.drawPath(path, fill)
    canvas.drawPath(path, outline)
    return bitmap
}

private const val EARTH_RADIUS_METERS = 6_371_008.8
private const val MAX_HEADING_CONE_LONGITUDE_SPAN_DEGREES = 1.0
private const val MAP_SAVED_STATE_KEY = "maplibre-map-viewport"
