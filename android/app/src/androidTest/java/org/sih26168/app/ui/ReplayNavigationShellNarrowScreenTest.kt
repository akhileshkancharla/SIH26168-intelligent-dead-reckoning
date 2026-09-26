package org.sih26168.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import org.junit.Rule
import org.junit.Test
import org.sih26168.app.replay.ReplayUiState

class ReplayNavigationShellNarrowScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun mandatoryReplayBadge_isVisibleWithoutHorizontalScrollingAt240Dp() {
        composeRule.setContent {
            MaterialTheme {
                Box(modifier = Modifier.size(width = 240.dp, height = 480.dp)) {
                    ReplayNavigationShell(
                        state = ReplayUiState(),
                        onIntent = {},
                        viewportContent = {},
                    )
                }
            }
        }

        composeRule.onNodeWithTag(ReplayGovernanceTags.MANDATORY_REPLAY_BADGE)
            .assertIsDisplayed()
    }

    @Test
    fun mandatoryOutageBadge_isVisibleWithoutHorizontalScrollingAt240Dp() {
        composeRule.setContent {
            MaterialTheme {
                Box(modifier = Modifier.size(width = 240.dp, height = 480.dp)) {
                    ReplayNavigationShell(
                        state = ReplayUiState(isOutageActive = true),
                        onIntent = {},
                        viewportContent = {},
                    )
                }
            }
        }

        composeRule.onNodeWithTag(ReplayGovernanceTags.MANDATORY_OUTAGE_BADGE)
            .assertIsDisplayed()
    }
}
