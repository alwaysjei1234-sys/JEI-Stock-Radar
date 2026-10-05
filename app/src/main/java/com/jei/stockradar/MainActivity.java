package com.jei.stockradar;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.content.pm.PackageManager;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String REMOTE_UI = "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/index.html";
    private static final String SYSTEM_JSON = "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/system.json";
    private static final String UPDATE_JSON = "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/update.json";
    private static final String PREFS = "jei_private";

    private WebView webView;
    private final ExecutorService io = Executors.newFixedThreadPool(3);
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        setupNotifications();
        scheduleRiskWorker();
        handleImportIntent(getIntent(), false);
        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " JEI-Stock-Radar/3.2");

        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            private boolean bootstrapped = false;
            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (!bootstrapped && url != null && url.startsWith("file:///android_asset/")) {
                    bootstrapped = true;
                    if (isOnline()) refreshRemoteUI(false);
                }
            }
        });
        webView.addJavascriptInterface(new NativeBridge(), "JEINative");

        webView.loadUrl("file:///android_asset/index.html");
    }

    private boolean handleImportIntent(Intent intent, boolean notifyUi) {
        try {
            if (intent == null) return false;
            Uri data = intent.getData();
            if (data == null || !"jeistock".equalsIgnoreCase(data.getScheme())
                    || !"import".equalsIgnoreCase(data.getHost())) return false;
            String encoded = data.getQueryParameter("data");
            if (encoded == null || encoded.length() < 8) return false;
            byte[] raw = Base64.decode(encoded, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
            JSONArray src = new JSONArray(new String(raw, StandardCharsets.UTF_8));
            JSONArray clean = new JSONArray();
            for (int i = 0; i < src.length(); i++) {
                JSONObject x = src.optJSONObject(i);
                if (x == null) continue;
                String code = x.optString("code", "").trim();
                String name = x.optString("name", code).trim();
                double cost = x.optDouble("cost", 0);
                long shares = x.optLong("shares", 0);
                if (!code.matches("[0-9A-Za-z]{2,8}") || cost <= 0 || shares <= 0) continue;
                JSONObject y = new JSONObject();
                y.put("code", code);
                y.put("name", name.isEmpty() ? code : name);
                y.put("cost", cost);
                y.put("shares", shares);
                clean.put(y);
            }
            if (clean.length() == 0) return false;
            prefs.edit().putString("holdings", clean.toString()).apply();
            if (notifyUi && webView != null) {
                runOnUiThread(() -> webView.evaluateJavascript(
                        "loadHoldings();refreshMarket();go('hold');toast('持股已匯入');", null));
            }
            runOnUiThread(() -> Toast.makeText(this,
                    "已匯入 " + clean.length() + " 檔持股", Toast.LENGTH_SHORT).show());
            return true;
        } catch (Exception e) {
            runOnUiThread(() -> Toast.makeText(this,
                    "持股匯入失敗", Toast.LENGTH_SHORT).show());
            return false;
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleImportIntent(intent, true);
    }

    private void setupNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = (NotificationManager)getSystemService(Context.NOTIFICATION_SERVICE);
            NotificationChannel risk = new NotificationChannel(
                    "jei_risk", "JEI 大逃殺與持股風險", NotificationManager.IMPORTANCE_HIGH);
            risk.setDescription("市場風險、急跌與重要持股警示");
            nm.createNotificationChannel(risk);
            NotificationChannel sys = new NotificationChannel(
                    "jei_system", "JEI 系統更新", NotificationManager.IMPORTANCE_DEFAULT);
            sys.setDescription("APP 新版本與系統更新通知");
            nm.createNotificationChannel(sys);
        }
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 9103);
        }
    }

    private void scheduleRiskWorker() {
        Constraints c = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();
        PeriodicWorkRequest req = new PeriodicWorkRequest.Builder(
                RiskWorker.class, 15, TimeUnit.MINUTES)
                .setConstraints(c)
                .build();
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
                "JEI_RISK_WATCH",
                ExistingPeriodicWorkPolicy.KEEP,
                req);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    private boolean isOnline() {
        try {
            ConnectivityManager cm = (ConnectivityManager)getSystemService(Context.CONNECTIVITY_SERVICE);
            Network n = cm.getActiveNetwork();
            if (n == null) return false;
            NetworkCapabilities c = cm.getNetworkCapabilities(n);
            return c != null && (c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                    || c.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)
                    || c.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET));
        } catch (Exception e) {
            return false;
        }
    }

    private String httpGet(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(url).openConnection();
        c.setConnectTimeout(9000);
        c.setReadTimeout(12000);
        c.setRequestMethod("GET");
        c.setRequestProperty("User-Agent", "Mozilla/5.0 JEIStockRadar/3.2");
        c.setRequestProperty("Accept", "application/json,text/html,*/*");
        c.setRequestProperty("Cache-Control", "no-cache");
        int status = c.getResponseCode();
        InputStream in = status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream();
        if (in == null) throw new Exception("HTTP " + status);
        BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) sb.append(line).append('\n');
        r.close();
        if (status < 200 || status >= 300) throw new Exception("HTTP " + status + ": " + sb);
        return sb.toString();
    }

    private void refreshRemoteUI(boolean userTriggered) {
        io.execute(() -> {
            try {
                String html = httpGet(REMOTE_UI + "?ts=" + System.currentTimeMillis());
                if (!html.contains("JEI_REMOTE_UI_V2") && !html.contains("JEI_REMOTE_UI_V3")) throw new Exception("remote ui signature missing");
                File f = new File(getFilesDir(), "jei_remote_index.html");
                try (FileOutputStream o = new FileOutputStream(f)) {
                    o.write(html.getBytes(StandardCharsets.UTF_8));
                }
                runOnUiThread(() -> webView.loadDataWithBaseURL(
                        "https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/",
                        html, "text/html", "UTF-8", null));
            } catch (Exception e) {
                if (userTriggered) runOnUiThread(() ->
                        Toast.makeText(this, "介面更新失敗，使用目前版本", Toast.LENGTH_SHORT).show());
            }
        });
    }

    private void jsCall(String function, String payload) {
        final String script = "window.JEI_NATIVE && window.JEI_NATIVE." + function + "(" + JSONObject.quote(payload) + ");";
        runOnUiThread(() -> webView.evaluateJavascript(script, null));
    }

    private void fetchSystem() {
        io.execute(() -> {
            try {
                jsCall("onSystemData", httpGet(SYSTEM_JSON + "?ts=" + System.currentTimeMillis()));
            } catch (Exception e) {
                jsCall("onSystemError", e.getMessage() == null ? "系統資料更新失敗" : e.getMessage());
            }
        });
    }

    private void checkUpdate() {
        io.execute(() -> {
            try {
                jsCall("onUpdateManifest", httpGet(UPDATE_JSON + "?ts=" + System.currentTimeMillis()));
            } catch (Exception e) {
                jsCall("onUpdateError", e.getMessage() == null ? "版本檢查失敗" : e.getMessage());
            }
        });
    }

    private void fetchMarket(String jsonCodes) {
        io.execute(() -> {
            try {
                JSONArray a = new JSONArray(jsonCodes);
                StringBuilder q = new StringBuilder();
                for (int i = 0; i < a.length(); i++) {
                    String code = a.getString(i).trim();
                    if (!code.matches("[0-9A-Za-z]{2,8}")) continue;
                    if (q.length() > 0) q.append('|');
                    q.append("tse_").append(code).append(".tw|otc_").append(code).append(".tw");
                }
                String url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch="
                        + q + "&json=1&delay=0&_=" + System.currentTimeMillis();
                jsCall("onMarketData", httpGet(url));
            } catch (Exception e) {
                jsCall("onMarketError", e.getMessage() == null ? "行情連線失敗" : e.getMessage());
            }
        });
    }

    public class NativeBridge {
        @JavascriptInterface public String getAppVersion() { return BuildConfig.VERSION_NAME; }
        @JavascriptInterface public int getAppVersionCode() { return BuildConfig.VERSION_CODE; }
        @JavascriptInterface public boolean isOnline() { return MainActivity.this.isOnline(); }
        @JavascriptInterface public void refreshRemoteUI() { MainActivity.this.refreshRemoteUI(true); }
        @JavascriptInterface public void refreshSystem() { MainActivity.this.fetchSystem(); }
        @JavascriptInterface public void checkForUpdates() { MainActivity.this.checkUpdate(); }
        @JavascriptInterface public void refreshMarketData(String codesJson) { MainActivity.this.fetchMarket(codesJson); }
        @JavascriptInterface public void saveHoldings(String json) {
            prefs.edit().putString("holdings", json).apply();
        }
        @JavascriptInterface public String loadHoldings() {
            return prefs.getString("holdings", "");
        }
        @JavascriptInterface public void saveSetting(String key, String value) {
            if (key != null && key.matches("[a-zA-Z0-9_]{1,32}"))
                prefs.edit().putString("s_" + key, value).apply();
        }
        @JavascriptInterface public String loadSetting(String key) {
            return prefs.getString("s_" + key, "");
        }
        @JavascriptInterface public void openUrl(String url) {
            try {
                Uri u = Uri.parse(url);
                if (!"https".equalsIgnoreCase(u.getScheme())) return;
                startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (Exception ignored) { }
        }
    }
}
