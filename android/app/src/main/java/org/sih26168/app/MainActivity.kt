package org.sih26168.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.sih26168.app.replay.ReplayNavigationViewModel
import org.sih26168.app.ui.ReplayNavigationShell

object ReplayDisclosure {
    const val LABEL = "REPLAY"
}

class MainActivity : ComponentActivity() {
    private val replayNavigationViewModel by viewModels<ReplayNavigationViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                val state by replayNavigationViewModel.uiState.collectAsStateWithLifecycle()
                ReplayNavigationShell(
                    state = state,
                    onIntent = replayNavigationViewModel::onIntent,
                )
            }
        }
    }
}
