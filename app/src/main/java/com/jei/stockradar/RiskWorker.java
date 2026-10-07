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
        try {
            ensureChannels();
            checkRisk();
            SharedPreferences p = getApplicationContext().getSharedPreferences("jei_private", Context.MODE_PRIVATE);
            checkHoldings(p.getInt("bg_risk_score", 0));
            checkAppUpdate();
            return Result.success();
        } catch (Exception e) {
            return Result.retry();
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

    private void checkRisk() throws Exception {
        JSONObject root = new JSONObject(get(SYSTEM_JSON));
        JSONObject risk = root.optJSONObject("risk");
        if (risk == null) return;

        String level = risk.optString("level", "green");
        int score = risk.optInt("score", 0);
        String label = risk.optString("label", "市場風險");
        String updated = root.optString("updated_at", "");

        SharedPreferences p = getApplicationContext().getSharedPreferences("jei_private", Context.MODE_PRIVATE);
        int oldScore = p.getInt("bg_risk_score", 0);
        String oldLevel = p.getString("bg_risk_level", "green");
        String oldStamp = p.getString("bg_risk_stamp", "");

        int severity = severity(level), oldSeverity = severity(oldLevel);
        boolean important = severity >= 2 || score >= 55;
        boolean worsened = severity > oldSeverity || score >= oldScore + 10;
        boolean fresh = !updated.equals(oldStamp);

        if (important && fresh && (worsened || severity >= 3)) {
            JSONArray reasons = risk.optJSONArray("reasons");
            String body = "風險 " + score + "/100";
            if (reasons != null && reasons.length() > 0) {
                body += "｜" + reasons.optString(0, "");
                if (reasons.length() > 1) body += "｜" + reasons.optString(1, "");
            }
            notify("jei_risk", 7301,
                    severity >= 3 ? "🔴 JEI 大逃殺警報：" + label :
                    severity == 2 ? "🟠 JEI 市場風險升高：" + label :
                    "🟡 JEI 市場轉弱：" + label,
                    body, Notification.PRIORITY_HIGH);
        }

        p.edit()
                .putInt("bg_risk_score", score)
                .putString("bg_risk_level", level)
                .putString("bg_risk_stamp", updated)
                .apply();
    }


    private void checkHoldings(int riskScore) throws Exception {
        SharedPreferences p = getApplicationContext().getSharedPreferences("jei_private", Context.MODE_PRIVATE);
        String raw = p.getString("holdings", "");
        if (raw == null || raw.trim().isEmpty()) return;

        JSONArray hs = new JSONArray(raw);
        if (hs.length() == 0) return;

        StringBuilder q = new StringBuilder();
        for (int i = 0; i < hs.length(); i++) {
            JSONObject h = hs.optJSONObject(i);
            if (h == null) continue;
            String code = h.optString("code", "").trim();
            if (!code.matches("[0-9A-Za-z]{2,8}")) continue;
            if (q.length() > 0) q.append("|");
            q.append("tse_").append(code).append(".tw|otc_").append(code).append(".tw");
        }
        if (q.length() == 0) return;

        String url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch="
                + q + "&json=1&delay=0&_=" + System.currentTimeMillis();
        JSONObject market = new JSONObject(get(url));
        JSONArray rows = market.optJSONArray("msgArray");
        if (rows == null || rows.length() == 0) return;

        JSONObject sys = new JSONObject(get(SYSTEM_JSON));
        JSONObject stockSectors = sys.optJSONObject("stock_sectors");
        JSONArray sectorRows = sys.optJSONArray("sectors");

        String day = new SimpleDateFormat("yyyyMMdd", Locale.US).format(new Date());
        JSONArray alerts = new JSONArray();

        for (int i = 0; i < rows.length(); i++) {
            JSONObject m = rows.optJSONObject(i);
            if (m == null) continue;
            String code = m.optString("c", "");
            String name = m.optString("n", code);
            if (code.isEmpty() || name.isEmpty()) continue;

            double price = toDouble(m.optString("z", ""));
            double prev = toDouble(m.optString("y", ""));
            if (!(price > 0)) {
                double bid = firstQuote(m.optString("b", ""));
                double ask = firstQuote(m.optString("a", ""));
                if (bid > 0 && ask > 0) price = (bid + ask) / 2.0;
                else if (bid > 0) price = bid;
                else if (ask > 0) price = ask;
                else price = prev;
            }
            if (!(price > 0) || !(prev > 0)) continue;

            JSONObject h = findHolding(hs, code);
            if (h == null) continue;
            double cost = h.optDouble("cost", 0);
            if (!(cost > 0)) continue;

            double ch = (price - prev) / prev * 100.0;
            double ret = (price - cost) / cost * 100.0;
            String sector = stockSectors == null ? "其他" : stockSectors.optString(code, "其他");
            int sectorScore = findSectorScore(sectorRows, sector);

            int severity = 0;
            String action = "";
            if ((riskScore >= 80 && ch < 0) || ch <= -7.0 || ret <= -15.0) {
                severity = 3;
                action = riskScore >= 80 ? "市場紅燈降部位" : "風控優先";
            } else if (ret >= 25.0 && (ch <= -3.0 || sectorScore < 45)) {
                severity = 2;
                action = "移動停利";
            } else if (ch <= -5.0 || ret <= -12.0 || (riskScore >= 65 && ch <= -3.0)) {
                severity = 2;
                action = "減碼防守";
            } else if ((ret >= 12.0 && ch <= -3.0) || (sectorScore < 40 && ch <= -2.0)) {
                severity = 1;
                action = ret >= 12.0 ? "鎖利觀察" : "族群轉弱";
            }

            String key = "bg_hold_" + day + "_" + code;
            int old = p.getInt(key, 0);
            if (severity > old) {
                JSONObject a = new JSONObject();
                a.put("code", code);
                a.put("name", name);
                a.put("change", ch);
                a.put("return", ret);
                a.put("action", action);
                a.put("sector", sector);
                a.put("sectorScore", sectorScore);
                a.put("severity", severity);
                alerts.put(a);
                p.edit().putInt(key, severity).apply();
            }
        }

        if (alerts.length() > 0) {
            StringBuilder body = new StringBuilder();
            int max = Math.min(3, alerts.length());
            for (int i = 0; i < max; i++) {
                JSONObject a = alerts.optJSONObject(i);
                if (i > 0) body.append("｜");
                body.append(a.optString("code")).append(" ")
                        .append(a.optString("name")).append(" ")
                        .append(String.format(Locale.US, "%.1f%%", a.optDouble("change")))
                        .append("／成本 ")
                        .append(String.format(Locale.US, "%+.1f%%", a.optDouble("return")))
                        .append(" ")
                        .append(a.optString("action"))
                        .append(" [").append(a.optString("sector")).append(" ")
                        .append(a.optInt("sectorScore", 50)).append("分]");
            }
            if (alerts.length() > max) body.append("｜另 ").append(alerts.length() - max).append(" 檔");
            notify("jei_risk", 7303,
                    "⚠ JEI 持股風控警示（" + alerts.length() + " 檔）",
                    body.toString(), Notification.PRIORITY_HIGH);
        }
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

    private double firstQuote(String levels) {
        if (levels == null || levels.isEmpty() || "-".equals(levels)) return 0;
        String[] parts = levels.split("_");
        for (String part : parts) {
            double v = toDouble(part);
            if (v > 0) return v;
        }
        return 0;
    }

    private double toDouble(String s) {
        try { return Double.parseDouble(s); }
        catch (Exception e) { return Double.NaN; }
    }

    private void checkAppUpdate() throws Exception {
        JSONObject j = new JSONObject(get(UPDATE_JSON));
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
