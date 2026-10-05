package com.jei.stockradar;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.DecimalFormat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public class MainActivity extends Activity {

    static class Holding {
        final String code, name, market;
        final double cost;
        final int shares;
        double price = Double.NaN;
        double ref = Double.NaN;

        Holding(String code, String name, String market, double cost, int shares) {
            this.code = code;
            this.name = name;
            this.market = market;
            this.cost = cost;
            this.shares = shares;
        }
    }

    private final Holding[] holdings = new Holding[] {
        new Holding("1711", "永光", "tse", 52.674, 1000),
        new Holding("2478", "大毅", "tse", 127.681, 1000),
        new Holding("2609", "陽明", "tse", 63.690, 1000),
        new Holding("2748", "雲品", "tse", 99.341, 1000),
        new Holding("3162", "精確", "otc", 85.621, 1000),
        new Holding("3289", "宜特", "otc", 141.701, 1000),
        new Holding("3707", "漢磊", "otc", 73.104, 1000),
        new Holding("5347", "世界", "otc", 123.175, 1000),
        new Holding("5425", "台半", "otc", 102.145, 1000),
        new Holding("6150", "撼訊", "otc", 77.510, 2000),
        new Holding("7711", "永擎", "tse", 257.8665, 2000),
        new Holding("8070", "長華*", "tse", 58.383, 1000)
    };

    private LinearLayout holdingsBox;
    private TextView riskTitle, riskDetail, updateTime, totalPnl;
    private ProgressBar loading;
    private Button refreshButton;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final DecimalFormat priceFmt = new DecimalFormat("#,##0.00");
    private final DecimalFormat moneyFmt = new DecimalFormat("#,##0");

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        refreshQuotes();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(245,247,250));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(20), dp(18), dp(28));
        scroll.addView(root);

        TextView title = text("JEI 專屬選股雷達", 26, true, Color.rgb(18,24,38));
        root.addView(title);

        TextView sub = text("持股監控・異常下殺預警・即時損益", 14, false, Color.rgb(95,105,120));
        sub.setPadding(0, dp(4), 0, dp(16));
        root.addView(sub);

        LinearLayout riskCard = card();
        riskTitle = text("市場風險：資料更新中", 21, true, Color.DKGRAY);
        riskDetail = text("正在讀取大盤與持股即時資訊…", 14, false, Color.DKGRAY);
        riskDetail.setPadding(0, dp(7), 0, 0);
        riskCard.addView(riskTitle);
        riskCard.addView(riskDetail);
        root.addView(riskCard);

        LinearLayout pnlCard = card();
        TextView pnlLabel = text("持股即時估算損益", 13, false, Color.rgb(100,108,120));
        totalPnl = text("等待行情", 25, true, Color.rgb(20,28,40));
        totalPnl.setPadding(0, dp(5), 0, 0);
        pnlCard.addView(pnlLabel);
        pnlCard.addView(totalPnl);
        root.addView(pnlCard);

        LinearLayout toolRow = new LinearLayout(this);
        toolRow.setOrientation(LinearLayout.HORIZONTAL);
        toolRow.setGravity(Gravity.CENTER_VERTICAL);
        toolRow.setPadding(0, dp(4), 0, dp(12));

        refreshButton = new Button(this);
        refreshButton.setText("立即刷新");
        refreshButton.setAllCaps(false);
        refreshButton.setOnClickListener(v -> refreshQuotes());
        toolRow.addView(refreshButton, new LinearLayout.LayoutParams(0, dp(48), 1));

        loading = new ProgressBar(this);
        loading.setVisibility(View.GONE);
        LinearLayout.LayoutParams lpLoad = new LinearLayout.LayoutParams(dp(40), dp(40));
        lpLoad.setMargins(dp(10),0,0,0);
        toolRow.addView(loading, lpLoad);
        root.addView(toolRow);

        updateTime = text("尚未更新", 12, false, Color.rgb(110,118,128));
        updateTime.setPadding(0, 0, 0, dp(10));
        root.addView(updateTime);

        TextView holdingHeader = text("我的持股", 20, true, Color.rgb(18,24,38));
        holdingHeader.setPadding(0, dp(4), 0, dp(10));
        root.addView(holdingHeader);

        holdingsBox = new LinearLayout(this);
        holdingsBox.setOrientation(LinearLayout.VERTICAL);
        root.addView(holdingsBox);
        renderHoldings();

        TextView note = text("預警邏輯 V1：大盤當日跌幅＋持股同步下跌比例＋個股相對成本風險。這是風險雷達，不是保證獲利或自動交易訊號。", 12, false, Color.rgb(105,112,122));
        note.setPadding(0, dp(12), 0, 0);
        root.addView(note);

        return scroll;
    }

    private LinearLayout card() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(16), dp(15), dp(16), dp(15));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.WHITE);
        bg.setCornerRadius(dp(16));
        bg.setStroke(dp(1), Color.rgb(226,230,236));
        box.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.setMargins(0,0,0,dp(12));
        box.setLayoutParams(lp);
        return box;
    }

    private TextView text(String s, int sp, boolean bold, int color) {
        TextView tv = new TextView(this);
        tv.setText(s);
        tv.setTextSize(sp);
        tv.setTextColor(color);
        if (bold) tv.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return tv;
    }

    private void renderHoldings() {
        holdingsBox.removeAllViews();
        for (Holding h : holdings) {
            LinearLayout c = card();

            LinearLayout top = new LinearLayout(this);
            top.setOrientation(LinearLayout.HORIZONTAL);
            TextView name = text(h.name + "  " + h.code, 18, true, Color.rgb(28,34,44));
            TextView price = text(Double.isNaN(h.price) ? "—" : priceFmt.format(h.price), 19, true, Color.rgb(28,34,44));
            price.setGravity(Gravity.END);
            top.addView(name, new LinearLayout.LayoutParams(0,-2,1));
            top.addView(price, new LinearLayout.LayoutParams(-2,-2));
            c.addView(top);

            String info = "成本 " + trimCost(h.cost) + "　｜　" + h.shares + " 股";
            TextView base = text(info, 13, false, Color.rgb(105,112,122));
            base.setPadding(0, dp(7), 0, dp(4));
            c.addView(base);

            if (!Double.isNaN(h.price)) {
                double pct = (h.price / h.cost - 1.0) * 100.0;
                double pnl = (h.price - h.cost) * h.shares;
                int color = pct >= 0 ? Color.rgb(205,55,55) : Color.rgb(20,145,84);
                String advice = riskAdvice(pct);
                TextView p = text(String.format(Locale.TAIWAN, "%+.2f%%　估算損益 %s 元", pct, signedMoney(pnl)), 15, true, color);
                c.addView(p);
                TextView a = text(advice, 13, false, Color.rgb(65,74,88));
                a.setPadding(0, dp(5), 0, 0);
                c.addView(a);
            }
            holdingsBox.addView(c);
        }
    }

    private String riskAdvice(double pct) {
        if (pct <= -20) return "⚠ 成本風險高：列入優先檢視，不宜只因攤平而加碼";
        if (pct <= -10) return "注意：弱於成本區，觀察量價與市場風險是否同步惡化";
        if (pct >= 30) return "已有大幅獲利：留意爆量、長黑與主升段結束訊號";
        if (pct >= 12) return "獲利區：可續抱監控，出現市場紅色警報時優先保護獲利";
        return "中性監控：以趨勢與大盤風險為主";
    }

    private void refreshQuotes() {
        refreshButton.setEnabled(false);
        loading.setVisibility(View.VISIBLE);
        riskTitle.setText("市場風險：掃描中");
        riskDetail.setText("同步讀取台股大盤與 " + holdings.length + " 檔持股…");

        new Thread(() -> {
            try {
                StringBuilder ex = new StringBuilder("tse_t00.tw");
                for (Holding h : holdings) {
                    ex.append("|").append(h.market).append("_").append(h.code).append(".tw");
                }
                String endpoint = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=" + ex;
                HttpURLConnection conn = (HttpURLConnection) new URL(endpoint).openConnection();
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(12000);
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 JEIStockRadar/1.0");
                conn.setRequestProperty("Accept", "application/json");
                BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
                br.close();

                JSONObject obj = new JSONObject(sb.toString());
                JSONArray arr = obj.getJSONArray("msgArray");
                Map<String, JSONObject> map = new HashMap<>();
                JSONObject indexObj = null;
                for (int i=0;i<arr.length();i++) {
                    JSONObject q = arr.getJSONObject(i);
                    String c = q.optString("c", "");
                    if ("t00".equals(c) || q.optString("ch","").contains("t00")) indexObj = q;
                    else map.put(c, q);
                }

                for (Holding h : holdings) {
                    JSONObject q = map.get(h.code);
                    if (q != null) {
                        h.price = number(q.optString("z","-"));
                        h.ref = number(q.optString("y","-"));
                        if (Double.isNaN(h.price)) {
                            double bid = firstNumber(q.optString("b",""));
                            double ask = firstNumber(q.optString("a",""));
                            if (!Double.isNaN(bid) && !Double.isNaN(ask)) h.price = (bid + ask) / 2.0;
                            else if (!Double.isNaN(bid)) h.price = bid;
                            else if (!Double.isNaN(ask)) h.price = ask;
                            else h.price = h.ref;
                        }
                    }
                }

                final JSONObject idx = indexObj;
                main.post(() -> {
                    applyRisk(idx);
                    renderHoldings();
                    updateTotalPnl();
                    updateTime.setText("最後更新：" + new SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.TAIWAN).format(new Date()));
                    refreshButton.setEnabled(true);
                    loading.setVisibility(View.GONE);
                });
            } catch (Exception e) {
                main.post(() -> {
                    refreshButton.setEnabled(true);
                    loading.setVisibility(View.GONE);
                    riskTitle.setText("市場風險：暫時無法連線");
                    riskDetail.setText("行情來源連線失敗，可稍後按「立即刷新」。\n" + e.getClass().getSimpleName());
                    Toast.makeText(this, "即時行情讀取失敗", Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }

    private void applyRisk(JSONObject idx) {
        double idxPct = 0;
        if (idx != null) {
            double z = number(idx.optString("z","-"));
            double y = number(idx.optString("y","-"));
            if (!Double.isNaN(z) && !Double.isNaN(y) && y != 0) idxPct = (z/y - 1.0)*100.0;
        }

        int falling = 0;
        int valid = 0;
        for (Holding h : holdings) {
            if (!Double.isNaN(h.price) && !Double.isNaN(h.ref) && h.ref != 0) {
                valid++;
                if (h.price < h.ref) falling++;
            }
        }
        double fallingRatio = valid == 0 ? 0 : falling * 100.0 / valid;

        String level;
        int color;
        String detail;
        if (idxPct <= -2.5 || (idxPct <= -1.5 && fallingRatio >= 75)) {
            level = "🔴 紅色：大逃殺風險升高";
            color = Color.rgb(190,35,45);
            detail = String.format(Locale.TAIWAN, "大盤 %.2f%%，持股下跌比例 %.0f%%。優先檢查高槓桿／高波動持股與既有大額獲利。", idxPct, fallingRatio);
        } else if (idxPct <= -1.2 || fallingRatio >= 70) {
            level = "🟠 橘色：資金壓力偏高";
            color = Color.rgb(215,105,20);
            detail = String.format(Locale.TAIWAN, "大盤 %.2f%%，持股下跌比例 %.0f%%。避免追價，注意跌勢擴散。", idxPct, fallingRatio);
        } else if (idxPct <= -0.6 || fallingRatio >= 58) {
            level = "🟡 黃色：提高警戒";
            color = Color.rgb(180,135,0);
            detail = String.format(Locale.TAIWAN, "大盤 %.2f%%，持股下跌比例 %.0f%%。目前屬早期警戒區。", idxPct, fallingRatio);
        } else {
            level = "🟢 綠色：暫無逃殺訊號";
            color = Color.rgb(24,135,82);
            detail = String.format(Locale.TAIWAN, "大盤 %.2f%%，持股下跌比例 %.0f%%。未觸發 V1 高風險條件。", idxPct, fallingRatio);
        }
        riskTitle.setText(level);
        riskTitle.setTextColor(color);
        riskDetail.setText(detail);
    }

    private void updateTotalPnl() {
        double pnl = 0;
        double invested = 0;
        int valid = 0;
        for (Holding h : holdings) {
            if (!Double.isNaN(h.price)) {
                pnl += (h.price - h.cost) * h.shares;
                invested += h.cost * h.shares;
                valid++;
            }
        }
        if (valid == 0) {
            totalPnl.setText("等待行情");
            totalPnl.setTextColor(Color.rgb(20,28,40));
            return;
        }
        double pct = invested == 0 ? 0 : pnl / invested * 100.0;
        totalPnl.setText(signedMoney(pnl) + " 元　(" + String.format(Locale.TAIWAN, "%+.2f%%", pct) + ")");
        totalPnl.setTextColor(pnl >= 0 ? Color.rgb(205,55,55) : Color.rgb(20,145,84));
    }

    private double number(String s) {
        try {
            if (s == null || s.isEmpty() || "-".equals(s)) return Double.NaN;
            return Double.parseDouble(s.replace(",",""));
        } catch (Exception e) { return Double.NaN; }
    }

    private double firstNumber(String s) {
        if (s == null) return Double.NaN;
        String[] parts = s.split("_");
        return parts.length == 0 ? Double.NaN : number(parts[0]);
    }

    private String trimCost(double d) {
        String s = String.format(Locale.US, "%.4f", d);
        while (s.contains(".") && s.endsWith("0")) s = s.substring(0, s.length()-1);
        return s;
    }

    private String signedMoney(double d) {
        return (d >= 0 ? "+" : "-") + moneyFmt.format(Math.abs(d));
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
