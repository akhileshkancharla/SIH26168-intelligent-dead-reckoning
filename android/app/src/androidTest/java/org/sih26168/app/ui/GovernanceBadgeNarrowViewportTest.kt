package org.sih26168.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.sih26168.app.replay.ReplayUiState
import org.sih26168.contracts.enums.NavigationModeV1

/** Rendered disclosure containment at the narrow end of the supported phone width. */
@RunWith(AndroidJUnit4::class)
class GovernanceBadgeNarrowViewportTest {
    @get:Rule val composeRule = createComposeRule()

    @Test
    fun replayBadgeIsVisibleInside320dpViewportBeforeOutage() {
        assertPinnedBadges(ReplayUiState(), listOf(GovernanceBadgeTags.REPLAY))
    }

    @Test
    fun replayAndOutageBadgesAreVisibleInside320dpViewportDuringBlackout() {
        assertPinnedBadges(
            ReplayUiState(
                isOutageActive = true,
                navigationMode = NavigationModeV1.BLACKOUT_DR,
            ),
            listOf(GovernanceBadgeTags.REPLAY, GovernanceBadgeTags.OUTAGE),
        )
    }

    private fun assertPinnedBadges(state: ReplayUiState, badges: List<String>) {
        composeRule.setContent {
            MaterialTheme {
                Box(Modifier.width(320.dp).height(640.dp).testTag("narrow-root")) {
                    ReplayNavigationShell(
                        state = state,
                        onIntent = {},
                        viewportContent = {},
                    )
                }
            }
        }

        val root = composeRule.onNodeWithTag("narrow-root")
            .fetchSemanticsNode().boundsInRoot
        val frame = composeRule.onNodeWithTag(GovernanceBadgeTags.FRAME)
            .fetchSemanticsNode().boundsInRoot
        for (tag in badges) {
            val badge = composeRule.onNodeWithTag(tag).assertIsDisplayed()
                .fetchSemanticsNode().boundsInRoot
            assertTrue("$tag clipped left", badge.left >= root.left)
            assertTrue("$tag clipped right", badge.right <= root.right)
            assertTrue("$tag outside top banner", badge.top >= frame.top && badge.bottom <= frame.bottom)
        }
    }
}
