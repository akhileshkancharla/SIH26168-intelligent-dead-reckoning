package org.sih26168.s1logger

import org.json.JSONArray
import org.json.JSONObject

object JsonUtil {
    fun objectOf(vararg pairs: Pair<String, Any?>): JSONObject {
        val out = JSONObject()
        pairs.forEach { (key, value) -> out.put(key, value ?: JSONObject.NULL) }
        return out
    }

    fun arrayOf(values: FloatArray): JSONArray = JSONArray().also { a ->
        values.forEach { a.put(it.toDouble()) }
    }
}
