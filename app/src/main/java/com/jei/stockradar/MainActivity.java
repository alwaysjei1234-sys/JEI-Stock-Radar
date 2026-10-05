package com.jei.stockradar;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

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
        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " JEI-Stock-Radar/3.0");

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
        c.setRequestProperty("User-Agent", "Mozilla/5.0 JEIStockRadar/3.0");
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
