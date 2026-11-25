package io.github.twentyfourbit7.transfer

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.MediaScannerConnection
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.os.PowerManager
import android.os.StatFs
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.EOFException
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.security.SecureRandom
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Takes files from 24bit7 over the WiFi while the app is open: a small HTTP server on port 47247, every request
 * carrying the code shown on the phone. It runs as a foreground service so pressing the power button doesn't stop
 * a copy (Android freezes apps that aren't), and stops when the app is closed.
 *
 * GET /info, GET /list?path=, GET /file?path=, PUT /file?path= (the body is the file), POST /mkdir?path=,
 * DELETE /file?path=. Paths are from the phone's shared storage ("Music/Seether/Disclaimer II/03 Broken.flac");
 * nothing outside it is reachable.
 */
class TransferService : Service() {
    private var server: ServerSocket? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val root: File get() = Environment.getExternalStorageDirectory().canonicalFile

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTE_ID, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (server == null) start()
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        stopSelf()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {   // Android 15 caps a data sync at six hours a day
        stopSelf()
    }

    override fun onDestroy() {
        try { server?.close() } catch (_: Exception) {}
        server = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wakeLock?.let { if (it.isHeld) it.release() }
        port = 0
        super.onDestroy()
    }

    private fun notification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.channel),
            NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.notification))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    private fun start() {
        ensureIdentity(this)
        val s = try { ServerSocket(PORT) } catch (e: IOException) { ServerSocket(0) }
        server = s
        port = s.localPort
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "24bit7:copy").also { it.acquire() }
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "24bit7:copy").also { it.acquire(6 * 3600 * 1000L) }
        thread(isDaemon = true, name = "24bit7-server") {
            while (!s.isClosed) {
                val c = try { s.accept() } catch (e: Exception) { break }
                thread(isDaemon = true) { handle(c) }
            }
        }
    }

    private fun resolve(rel: String): File? {
        val base = root
        val f = File(base, rel.trimStart('/')).canonicalFile
        return if (f.path == base.path || f.path.startsWith(base.path + File.separator)) f else null
    }

    private fun handle(c: Socket) {
        c.use { sock ->
            sock.soTimeout = 60000
            val input = BufferedInputStream(sock.getInputStream(), 1 shl 16)
            val out = sock.getOutputStream()
            try {
                val head = readHead(input) ?: return
                val lines = head.split("\r\n")
                val first = lines[0].split(" ")
                if (first.size < 2) return
                val method = first[0]
                val target = first[1]
                val headers = lines.drop(1).mapNotNull { l ->
                    val i = l.indexOf(':')
                    if (i > 0) l.substring(0, i).trim().lowercase() to l.substring(i + 1).trim() else null
                }.toMap()
                val path = target.substringBefore('?')
                // Who this is, without the code: only the id and the model, so 24bit7 can tell a phone that moved or
                // was reinstalled from one it has never seen. Nothing on the phone is read without the code.
                if (method == "GET" && path == "/hello") {
                    return reply(out, 200, JSONObject().put("id", installId(this)).put("name", Build.MODEL).put("version", VERSION))
                }
                if (headers["x-24bit7-code"] != code(this)) return reply(out, 401, JSONObject().put("error", "wrong code"))
                val query = target.substringAfter('?', "").split('&').filter { it.contains('=') }.associate {
                    URLDecoder.decode(it.substringBefore('='), "UTF-8") to URLDecoder.decode(it.substringAfter('='), "UTF-8")
                }
                if (method == "GET" && path == "/info") {
                    val st = StatFs(root.path)
                    return reply(out, 200, JSONObject().put("id", installId(this)).put("name", Build.MODEL)
                        .put("free", st.availableBytes).put("total", st.totalBytes).put("version", VERSION))
                }
                val file = query["path"]?.let { resolve(it) } ?: return reply(out, 400, JSONObject().put("error", "bad path"))
                when {
                    method == "GET" && path == "/list" -> list(out, file)
                    method == "GET" && path == "/file" -> send(out, file)
                    method == "PUT" && path == "/file" -> receive(out, input, file, headers["content-length"]?.toLongOrNull())
                    method == "POST" && path == "/mkdir" -> { file.mkdirs(); reply(out, 200, JSONObject().put("dir", file.isDirectory)) }
                    method == "DELETE" && path == "/file" -> delete(out, file)
                    else -> reply(out, 404, JSONObject().put("error", "no such request"))
                }
            } catch (e: Exception) {
                last = getString(R.string.problem, e.message ?: e.toString())
                try { reply(out, 500, JSONObject().put("error", e.toString())) } catch (_: Exception) {}
            }
        }
    }

    private fun list(out: OutputStream, dir: File) {
        if (!dir.isDirectory) return reply(out, 404, JSONObject().put("error", "not a folder"))
        val arr = JSONArray()
        dir.listFiles()?.sortedBy { it.name.lowercase() }?.forEach {
            arr.put(JSONObject().put("name", it.name).put("dir", it.isDirectory).put("size", if (it.isFile) it.length() else 0))
        }
        reply(out, 200, JSONObject().put("entries", arr))
    }

    private fun send(out: OutputStream, file: File) {
        if (!file.isFile) return reply(out, 404, JSONObject().put("error", "no such file"))
        out.write(("HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: ${file.length()}\r\n" +
            "Connection: close\r\n\r\n").toByteArray())
        file.inputStream().use { it.copyTo(out, 1 shl 16) }
        out.flush()
    }

    private fun receive(out: OutputStream, input: InputStream, file: File, length: Long?) {
        if (length == null) return reply(out, 411, JSONObject().put("error", "no length"))
        file.parentFile?.mkdirs()
        val part = File(file.path + ".part")
        FileOutputStream(part).use { fo ->
            val buf = ByteArray(1 shl 16)
            var left = length
            while (left > 0) {
                val n = input.read(buf, 0, minOf(buf.size.toLong(), left).toInt())
                if (n < 0) { part.delete(); throw EOFException("the file stopped short") }
                fo.write(buf, 0, n)
                left -= n
            }
        }
        if (file.exists()) file.delete()
        if (!part.renameTo(file)) throw IOException("couldn't name ${file.name}")
        MediaScannerConnection.scanFile(applicationContext, arrayOf(file.path), null, null)
        last = getString(R.string.got, file.name)
        reply(out, 201, JSONObject().put("size", length))
    }

    private fun delete(out: OutputStream, file: File) {
        if (file == root) return reply(out, 400, JSONObject().put("error", "won't delete the whole phone"))
        val gone = if (file.exists()) file.walkBottomUp().filter { it.isFile }.map { it.path }.toList() else emptyList()
        val ok = !file.exists() || file.deleteRecursively()
        if (gone.isNotEmpty()) MediaScannerConnection.scanFile(applicationContext, gone.toTypedArray(), null, null)
        last = getString(R.string.deleted, file.name)
        reply(out, if (ok) 200 else 500, JSONObject().put("deleted", ok).put("files", gone.size))
    }

    private fun readHead(input: InputStream): String? {
        val buf = ByteArrayOutputStream()
        var state = 0
        while (true) {
            val b = input.read()
            if (b < 0) return null
            buf.write(b)
            state = when {
                b == '\r'.code && (state == 0 || state == 2) -> state + 1
                b == '\n'.code && (state == 1 || state == 3) -> state + 1
                b == '\r'.code -> 1
                else -> 0
            }
            if (state == 4) return buf.toString("UTF-8")
            if (buf.size() > 16384) return null
        }
    }

    private fun reply(out: OutputStream, status: Int, json: JSONObject) {
        val body = json.toString().toByteArray()
        out.write(("HTTP/1.1 $status ${REASONS[status] ?: "OK"}\r\nContent-Type: application/json\r\n" +
            "Content-Length: ${body.size}\r\nConnection: close\r\n\r\n").toByteArray())
        out.write(body)
        out.flush()
    }

    companion object {
        const val PORT = 47247
        const val VERSION = 2          // the conversation 24bit7 and the app share (2: /hello, 25 Nov 2026)
        const val NOTE_ID = 1
        const val CHANNEL = "copy"
        val REASONS = mapOf(200 to "OK", 201 to "Created", 400 to "Bad Request", 401 to "Unauthorized",
            404 to "Not Found", 411 to "Length Required", 500 to "Internal Server Error")
        @Volatile var port = 0           // 0 while not listening
        @Volatile var last = ""          // the last thing done, shown under the code

        private fun prefs(c: Context) = c.getSharedPreferences("transfer", Context.MODE_PRIVATE)

        private fun mark() = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC), ".24bit7")

        /** Music/.24bit7's lines: the id, then the code (an app before 25 Nov 2026 wrote the id alone). */
        private fun marked(n: Int): String? = try {
            mark().takeIf { it.isFile }?.readLines()?.map { it.trim() }?.getOrNull(n)?.takeIf { it.isNotEmpty() }
        } catch (_: Exception) { null }

        /**
         * The four digits 24bit7 asks for once, kept for good: read back from Music/.24bit7 after a reinstall, so
         * 24bit7 doesn't have to ask again (Ben, 25 Nov 2026). An app on the phone that can read Music can already
         * write to it, so the file gives nothing away the code guards (others on the WiFi).
         */
        fun code(c: Context): String = prefs(c).getString("code", null)
            ?: (marked(1)?.takeIf { Regex("\\d{4}").matches(it) } ?: (1000 + SecureRandom().nextInt(9000)).toString())
                .also { prefs(c).edit().putString("code", it).apply() }

        /** This phone's id for 24bit7, read back from Music/.24bit7 after a reinstall so it stays the same phone. */
        fun installId(c: Context): String = prefs(c).getString("id", null)
            ?: (marked(0)?.takeIf { Regex("[0-9a-fA-F-]{8,64}").matches(it) } ?: UUID.randomUUID().toString())
                .also { prefs(c).edit().putString("id", it).apply() }

        /**
         * Music/.24bit7 holds this install's id and code, so 24bit7 knows the phone plugged in by USB is the one it
         * reaches over WiFi (one name, folder and limit for both), and a reinstall is still the same phone. Only
         * called once All files access is given, so an id from before is always read before a new one is made.
         */
        fun ensureIdentity(c: Context) {
            try {
                val f = mark()
                val text = installId(c) + "\n" + code(c) + "\n"
                if (!f.isFile || f.readText() != text) {
                    f.parentFile?.mkdirs()
                    f.writeText(text)
                }
            } catch (_: Exception) {
            }
        }
    }
}
