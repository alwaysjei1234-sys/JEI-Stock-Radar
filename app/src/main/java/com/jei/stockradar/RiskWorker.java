package com.jei.stockradar;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Calendar;
import java.util.TimeZone;
import java.util.HashSet;
import java.util.Locale;

public class RiskWorker extends Worker {
    private static final String SYSTEM_JSON =
            "https://jei-stock-radar.vercel.app/remote/system.json";
    private static final String UPDATE_JSON =
            "https://jei-stock-radar.vercel.app/remote/update.json";

    public RiskWorker(Context context, WorkerParameters params) {
        super(context, params);
    }

    @Override
    public Result doWork() {
        ensureChannels();
        try {
            JSONObject root = new JSONObject(getStaticFeed(SYSTEM_JSON));
            long now = System.currentTimeMillis();
            if (trustedLiveFeed(root, now)) {
                SharedPreferences prefs = getApplicationContext().getSharedPreferences("jei_private", Context.MODE_PRIVATE);
                String day = taipeiFormat("yyyyMMdd", now);
                checkRisk(root, prefs, day, now);
                checkHoldings(root, prefs, day, now);
            }
        } catch (Exception ignored) {
            // An unavailable/unverified feed must fail closed, never emit stale market warnings.
        }
        try { checkAppUpdate(); } catch (Exception ignored) {
            // Update notification checks must not reuse an invalid risk feed.
        }
        return Result.success();
    }

    private static SimpleDateFormat taipeiParser(String pattern) {
        SimpleDateFormat date = new SimpleDateFormat(pattern, Locale.US);
        date.setTimeZone(TimeZone.getTimeZone("Asia/Taipei"));
        date.setLenient(false);
        return date;
    }

    private static String taipeiFormat(String pattern, long millis) {
        return taipeiParser(pattern).format(new Date(millis));
    }

    static boolean taipeiMarketOpen(long millis) {
        Calendar clock = Calendar.getInstance(TimeZone.getTimeZone("Asia/Taipei"), Locale.US);
        clock.setTimeInMillis(millis);
        int day = clock.get(Calendar.DAY_OF_WEEK);
        int minute = clock.get(Calendar.HOUR_OF_DAY) * 60 + clock.get(Calendar.MINUTE);
        return day != Calendar.SATURDAY && day != Calendar.SUNDAY && minute >= 540 && minute < 810;
    }

    static boolean trustedLiveFeed(JSONObject root, long now) {
        if (!taipeiMarketOpen(now) || root == null) return false;
        JSONObject market = root.optJSONObject("market");
        if (market == null || market.optBoolean("stale", true) || !market.optBoolean("live_valid", false)
                || !"盤中即時".equals(market.optString("mode", ""))) return false;
        String today = taipeiFormat("yyyy-MM-dd", now);
        if (!today.equals(root.optString("data_date", ""))) return false;
        String updated = root.optString("updated_at", "");
        try {
            Date stamp = taipeiParser("yyyy-MM-dd HH:mm").parse(updated);
            if (stamp == null) return false;
            long lag = now - stamp.getTime();
            return lag >= -120000L && lag <= 35L * 60L * 1000L;
        } catch (Exception e) {
            return false;
        }
    }

    static boolean trustedExecutedTrade(JSONObject row, long now) {
        if (row == null || !taipeiMarketOpen(now)) return false;
        if (!taipeiFormat("yyyyMMdd", now).equals(row.optString("d", ""))) return false;
        if (!(toDouble(row.optString("z", "")) > 0) || !(toDouble(row.optString("y", "")) > 0)) return false;
        String clock = row.optString("t", "");
        if (!clock.matches("\\d{1,2}:\\d{2}(?::\\d{2})?")) return false;
        try {
            String fullTime = clock.length() == 5 ? clock + ":00" : clock;
            Date executed = taipeiParser("yyyyMMdd HH:mm:ss")
                    .parse(taipeiFormat("yyyyMMdd", now) + " " + fullTime);
            if (executed == null) return false;
            long lag = now - executed.getTime();
            return lag >= -120000L && lag <= 8L * 60L * 1000L;
        } catch (Exception e) {
            return false;
        }
    }

    private boolean canPostNotifications() {
        Context ctx = getApplicationContext();
        if (Build.VERSION.SDK_INT >= 33
                && ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) return false;
        NotificationManager manager = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        return manager != null && manager.areNotificationsEnabled();
    }

    private void recordRiskEvent(SharedPreferences prefs, String type, String headline, String detail, long now) {
        try {
            JSONArray existing = new JSONArray(prefs.getString("bg_alert_events", "[]"));
            JSONObject event = new JSONObject();
            event.put("at", taipeiFormat("yyyy-MM-dd HH:mm", now));
            event.put("type", type);
            event.put("title", headline);
            event.put("detail", detail);
            JSONArray history = new JSONArray();
            for (int i = Math.max(0, existing.length() - 39); i < existing.length(); i++)
                history.put(existing.opt(i));
            history.put(event);
            prefs.edit().putString("bg_alert_events", history.toString()).apply();
        } catch (Exception ignored) {
            // The alert must still work even if local history cannot be written.
        }
    }

    private String get(String url) throws Exception {
        String sep = url.contains("?") ? "&" : "?";
        HttpURLConnection c = (HttpURLConnection)new URL(url + sep + "bg=" + System.currentTimeMillis()).openConnection();
        c.setConnectTimeout(9000);
        c.setReadTimeout(12000);
        c.setRequestProperty("User-Agent", "JEIStockRadar-Background/3.7.1");
        int status = c.getResponseCode();
        InputStream in = status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream();
        if (in == null) throw new Exception("HTTP " + status);
        BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) sb.append(line);
        r.close();
        if (status < 200 || status >= 300) throw new Exception("HTTP " + status);
        return sb.toString();
    }

    // Only static public JEI files may use GitHub Raw as a read-only failover.
    private String getStaticFeed(String primaryUrl) throws Exception {
        if (!primaryUrl.equals(SYSTEM_JSON) && !primaryUrl.equals(UPDATE_JSON))
            throw new IllegalArgumentException("not a static JEI feed");
        try {
            String result = get(primaryUrl);
            JSONObject data = new JSONObject(result);
            if (primaryUrl.equals(SYSTEM_JSON) && !data.has("market"))
                throw new Exception("market feed unavailable");
            if (primaryUrl.equals(UPDATE_JSON) && !data.has("versionCode"))
                throw new Exception("update feed unavailable");
            return result;
        } catch (Exception primaryFailure) {
            String fileName = primaryUrl.substring(primaryUrl.lastIndexOf('/') + 1);
            return get("https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/"
                    + fileName);
        }
    }

    private void checkRisk(JSONObject root, SharedPreferences prefs, String day, long now) throws Exception {
        JSONObject risk = root.optJSONObject("risk");
        if (risk == null) return;
        String level = risk.optString("level", "green");
        int score = risk.optInt("score", 0);
        if (score < 0 || score > 100) return;
        int severity = severity(level);
        int oldScore = prefs.getInt("bg_risk_score", 0);
        int oldSeverity = severity(prefs.getString("bg_risk_level", "green"));
        boolean firstCriticalToday = severity >= 3 && !day.equals(prefs.getString("bg_risk_day", ""));
        boolean worsened = severity > oldSeverity || score >= oldScore + 10 || firstCriticalToday;
        if (canPostNotifications() && (severity >= 2 || score >= 55) && worsened) {
            JSONArray reasons = risk.optJSONArray("reasons");
            String body = "今日有效盤中資料｜市場風險 " + score + "/100";
            if (reasons != null && reasons.length() > 0) {
                body += "｜" + reasons.optString(0, "");
                if (reasons.length() > 1) body += "｜" + reasons.optString(1, "");
            }
            String title = severity >= 3 ? "🔴 JEI 市場風險紅燈"
                    : severity == 2 ? "🟠 JEI 市場風險升高" : "🟡 JEI 市場轉弱";
            notify("jei_risk", 7301, title, body, Notification.PRIORITY_HIGH);
            recordRiskEvent(prefs, "market", title, body, now);
        }
        // Never update alert baselines from stale or out-of-session feeds.
        prefs.edit().putInt("bg_risk_score", score)
                .putString("bg_risk_level", level)
                .putString("bg_risk_day", day)
                .putString("bg_risk_stamp", root.optString("updated_at", ""))
                .apply();
    }

    private void checkHoldings(JSONObject sys, SharedPreferences prefs, String day, long now) throws Exception {
        if (!canPostNotifications()) return;
        String raw = prefs.getString("holdings", "");
        if (raw == null || raw.trim().isEmpty()) return;
        JSONArray hs = new JSONArray(raw);
        if (hs.length() == 0) return;

        StringBuilder query = new StringBuilder();
        for (int i = 0; i < hs.length(); i++) {
            JSONObject holding = hs.optJSONObject(i);
            if (holding == null) continue;
            String code = holding.optString("code", "").trim();
            if (!code.matches("[0-9]{4,6}")) continue;
            if (query.length() > 0) query.append("|");
            query.append("tse_").append(code).append(".tw|otc_").append(code).append(".tw");
        }
        if (query.length() == 0) return;

        String url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch="
                + query + "&json=1&delay=0&_=" + System.currentTimeMillis();
        JSONArray quotes = new JSONObject(get(url)).optJSONArray("msgArray");
        if (quotes == null || quotes.length() == 0) return;

        JSONObject stockSectors = sys.optJSONObject("stock_sectors");
        JSONArray sectorRows = sys.optJSONArray("sectors");
        JSONObject risk = sys.optJSONObject("risk");
        int riskScore = risk == null ? 0 : risk.optInt("score", 0);
        JSONArray alerts = new JSONArray();
        HashSet<String> checked = new HashSet<>();

        for (int i = 0; i < quotes.length(); i++) {
            JSONObject quote = quotes.optJSONObject(i);
            if (!trustedExecutedTrade(quote, now)) continue;
            String code = quote.optString("c", "").trim();
            if (!code.matches("[0-9]{4,6}") || !checked.add(code)) continue;
            JSONObject holding = findHolding(hs, code);
            if (holding == null) continue;
            double cost = holding.optDouble("cost", 0);
            long shares = holding.optLong("shares", 0);
            if (!(cost > 0) || shares <= 0) continue;

            // A valid last execution (z) is required. Never substitute bid/ask or yesterday's close.
            double price = toDouble(quote.optString("z", ""));
            double prev = toDouble(quote.optString("y", ""));
            double ch = (price - prev) / prev * 100.0;
            double ret = (price - cost) / cost * 100.0;
            String sector = stockSectors == null ? "其他" : stockSectors.optString(code, "其他");
            int sectorScore = findSectorScore(sectorRows, sector);
            int severity = 0;
            String reason = "";
            if ((riskScore >= 80 && ch < 0) || ch <= -7 || ret <= -15) {
                severity = 3;
                reason = riskScore >= 80 && ch < 0 ? "大盤高風險共振" : "個股跌幅／成本風險";
            } else if (ret >= 25 && (ch <= -3 || sectorScore < 45)) {
                severity = 2;
                reason = "獲利保護觀察";
            } else if (ch <= -5 || ret <= -12 || (riskScore >= 65 && ch <= -3)) {
                severity = 2;
                reason = "個股弱勢防守";
            } else if ((ret >= 12 && ch <= -3) || (sectorScore < 40 && ch <= -2)) {
                severity = 1;
                reason = ret >= 12 ? "獲利回吐觀察" : "族群弱勢觀察";
            }
            if (severity == 0) continue;
            String key = "bg_hold_" + day + "_" + code;
            int old = prefs.getInt(key, 0);
            if (severity <= old) continue;
            JSONObject alert = new JSONObject();
            alert.put("code", code);
            alert.put("name", holding.optString("name", code));
            alert.put("change", ch);
            alert.put("return", ret);
            alert.put("reason", reason);
            alert.put("severity", severity);
            alerts.put(alert);
            prefs.edit().putInt(key, severity).apply();
        }

        if (alerts.length() == 0) return;
        StringBuilder body = new StringBuilder();
        for (int i = 0; i < Math.min(3, alerts.length()); i++) {
            JSONObject a = alerts.optJSONObject(i);
            if (a == null) continue;
            if (i > 0) body.append("｜");
            body.append(a.optString("code")).append(" ")
                    .append(a.optString("name")).append(" 較昨收 ")
                    .append(String.format(Locale.US, "%+.1f%%", a.optDouble("change")))
                    .append("／成本 ")
                    .append(String.format(Locale.US, "%+.1f%%", a.optDouble("return")))
                    .append("｜").append(a.optString("reason"));
        }
        if (alerts.length() > 3) body.append("｜另 ").append(alerts.length() - 3).append(" 檔");
        String title = "⚠ JEI 持股盤中風險（" + alerts.length() + " 檔）";
        notify("jei_risk", 7303, title, body.toString(), Notification.PRIORITY_HIGH);
        recordRiskEvent(prefs, "holding", title, body.toString(), now);
    }

    private int findSectorScore(JSONArray sectors, String name) {
        if (sectors == null || name == null) return 50;
        for (int i = 0; i < sectors.length(); i++) {
            JSONObject x = sectors.optJSONObject(i);
            if (x != null && name.equals(x.optString("name", ""))) return x.optInt("score", 50);
        }
        return 50;
    }

    private JSONObject findHolding(JSONArray hs, String code) {
        for (int i = 0; i < hs.length(); i++) {
            JSONObject h = hs.optJSONObject(i);
            if (h != null && code.equals(h.optString("code", ""))) return h;
        }
        return null;
    }

    private static double toDouble(String s) {
        try { return Double.parseDouble(s); }
        catch (Exception e) { return Double.NaN; }
    }

    private void checkAppUpdate() throws Exception {
        JSONObject j = new JSONObject(getStaticFeed(UPDATE_JSON));
        int remote = j.optInt("versionCode", 0);
        if (remote <= BuildConfig.VERSION_CODE) return;

        SharedPreferences p = getApplicationContext().getSharedPreferences("jei_private", Context.MODE_PRIVATE);
        int notified = p.getInt("bg_update_notified", 0);
        if (remote == notified) return;

        notify("jei_system", 7302, "JEI 選股雷達有新版",
                "版本 " + j.optString("versionName", "") + " 已可下載更新",
                Notification.PRIORITY_DEFAULT);
        p.edit().putInt("bg_update_notified", remote).apply();
    }

    private int severity(String level) {
        if ("red".equalsIgnoreCase(level)) return 3;
        if ("orange".equalsIgnoreCase(level)) return 2;
        if ("yellow".equalsIgnoreCase(level)) return 1;
        return 0;
    }

    private void ensureChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = (NotificationManager)getApplicationContext().getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel risk = new NotificationChannel("jei_risk",
                "JEI 大逃殺與持股風險", NotificationManager.IMPORTANCE_HIGH);
        risk.setDescription("市場風險、急跌與重要持股警示");
        nm.createNotificationChannel(risk);
        NotificationChannel sys = new NotificationChannel("jei_system",
                "JEI 系統更新", NotificationManager.IMPORTANCE_DEFAULT);
        nm.createNotificationChannel(sys);
    }

    private void notify(String channel, int id, String title, String body, int priority) {
        Context c = getApplicationContext();
        if (Build.VERSION.SDK_INT >= 33
                && c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        Intent i = new Intent(c, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(c, 0, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder b = new Notification.Builder(c, channel)
                .setSmallIcon(com.jei.stockradar.R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setPriority(priority);

        NotificationManager nm = (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.notify(id, b.build());
    }
}
