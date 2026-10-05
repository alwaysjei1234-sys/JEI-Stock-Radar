package com.jei.stockradar;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;
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

public class RiskWorker extends Worker {
    private static final String SYSTEM_JSON =
            "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/system.json";
    private static final String UPDATE_JSON =
            "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/update.json";

    public RiskWorker(Context context, WorkerParameters params) {
        super(context, params);
    }

    @Override
    public Result doWork() {
        try {
            ensureChannels();
            checkRisk();
            checkAppUpdate();
            return Result.success();
        } catch (Exception e) {
            return Result.retry();
        }
    }

    private String get(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(url + "?bg=" + System.currentTimeMillis()).openConnection();
        c.setConnectTimeout(9000);
        c.setReadTimeout(12000);
        c.setRequestProperty("User-Agent", "JEIStockRadar-Background/3.1");
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
                    body, NotificationCompat.PRIORITY_HIGH);
        }

        p.edit()
                .putInt("bg_risk_score", score)
                .putString("bg_risk_level", level)
                .putString("bg_risk_stamp", updated)
                .apply();
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
                NotificationCompat.PRIORITY_DEFAULT);
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

        NotificationCompat.Builder b = new NotificationCompat.Builder(c, channel)
                .setSmallIcon(com.jei.stockradar.R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setPriority(priority);

        NotificationManager nm = (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.notify(id, b.build());
    }
}
