    package org.sih26168.app
    import android.app.Activity
    import android.os.Bundle
    import android.widget.TextView
    object ReplayDisclosure { const val LABEL = "REPLAY" }
    class MainActivity : Activity() {
        override fun onCreate(savedInstanceState: Bundle?) {
            super.onCreate(savedInstanceState)
            setContentView(TextView(this).apply { text = "${ReplayDisclosure.LABEL}\nSCAFFOLD — NOT IMPLEMENTED"; textSize = 28f })
        }
    }
