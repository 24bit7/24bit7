package io.github.twentyfourbit7.transfer

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView
import java.net.Inet4Address

/**
 * The whole app, as bare as it can be (Ben, 24 Nov 2026: "just open to start"; 24bit7 is the interface): one screen
 * saying it's ready, with the code 24bit7 asks for once. Open, it keeps the screen on and copies; closed, it stops.
 */
class MainActivity : Activity() {
    private lateinit var status: TextView
    private val ticker = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            show()
            ticker.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        status = TextView(this).apply {
            gravity = Gravity.CENTER
            textSize = 20f
            setPadding(56, 56, 56, 56)
            setBackgroundColor(Color.rgb(24, 24, 27))
            setTextColor(Color.WHITE)
            setLineSpacing(0f, 1.2f)
        }
        setContentView(status)
    }

    override fun onResume() {
        super.onResume()
        if (!Environment.isExternalStorageManager()) {
            status.text = getString(R.string.needs_access)
            status.setOnClickListener {
                startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:$packageName")))
            }
            return
        }
        status.setOnClickListener(null)
        startForegroundService(Intent(this, TransferService::class.java))
        ticker.post(tick)
    }

    override fun onPause() {
        ticker.removeCallbacks(tick)
        super.onPause()
    }

    override fun onDestroy() {
        if (isFinishing) stopService(Intent(this, TransferService::class.java))
        super.onDestroy()
    }

    private fun show() {
        val text = SpannableStringBuilder()
        fun add(s: String, size: Float = 1f, bold: Boolean = false) {
            val start = text.length
            text.append(s)
            text.setSpan(RelativeSizeSpan(size), start, text.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            if (bold) text.setSpan(StyleSpan(Typeface.BOLD), start, text.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        add(getString(R.string.ready) + "\n\n", 1.3f, true)
        add(getString(R.string.code) + "\n", 0.8f)
        add(TransferService.code(this) + "\n\n", 2.6f, true)
        val address = wifiAddress()
        add((address ?: getString(R.string.no_wifi)) + "\n", 0.7f)
        add(getString(R.string.keep_open), 0.7f)
        val last = TransferService.last
        if (last.isNotEmpty()) add("\n\n$last", 0.75f)
        status.text = text
    }

    private fun wifiAddress(): String? {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return null
        val caps = cm.getNetworkCapabilities(net) ?: return null
        if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return null
        return cm.getLinkProperties(net)?.linkAddresses?.map { it.address }?.firstOrNull { it is Inet4Address }?.hostAddress
    }
}
