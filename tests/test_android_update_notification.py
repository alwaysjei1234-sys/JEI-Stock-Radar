"""Replay the real Android update notification dedup logic on the JVM.

No device/permission grant or APK installation is simulated as successful.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RISK_WORKER = ROOT / "app/src/main/java/com/jei/stockradar/RiskWorker.java"


def method(source, signature):
    start = source.index("    " + signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class AndroidUpdateNotificationTests(unittest.TestCase):
    def test_update_reminder_waits_for_notification_permission(self):
        java = shutil.which("java")
        if not java:
            self.skipTest("Java toolchain required; Android build CI has Java 17")
        source = RISK_WORKER.read_text(encoding="utf-8")
        body = method(source, "private void checkAppUpdate(")
        code = r"""
public class UpdateReminderHarness {
    static final String UPDATE_JSON = "update";
    static class Context { static final int MODE_PRIVATE = 0; }
    static class BuildConfig { static final int VERSION_CODE = 42; }
    static class Notification { static final int PRIORITY_DEFAULT = 0; }
    static class JSONObject {
        private final int version;
        JSONObject(String raw) { version = Integer.parseInt(raw); }
        int optInt(String key, int defaultValue) {
            return "versionCode".equals(key) ? version : defaultValue;
        }
        String optString(String key, String defaultValue) {
            return "versionName".equals(key) ? "3.9.20" : defaultValue;
        }
    }
    static class SharedPreferences {
        int lastNotified = 0;
        int getInt(String key, int fallback) { return lastNotified; }
        Editor edit() { return new Editor(this); }
        static class Editor {
            private final SharedPreferences prefs;
            Editor(SharedPreferences prefs) { this.prefs = prefs; }
            Editor putInt(String key, int value) { prefs.lastNotified = value; return this; }
            void apply() {}
        }
    }
    static class FakeContext extends Context {
        final SharedPreferences preferences = new SharedPreferences();
        SharedPreferences getSharedPreferences(String name, int mode) {
            return preferences;
        }
    }
    final FakeContext ctx = new FakeContext();
    boolean canNotify;
    int remoteVersion = 43;
    int displayed = 0;
    FakeContext getApplicationContext() { return ctx; }
    boolean canPostNotifications() { return canNotify; }
    String getStaticFeed(String url) { return Integer.toString(remoteVersion); }
    void notify(String channel, int id, String title, String body, int priority) {
        if (!canNotify) throw new AssertionError("Attempted reminder without permission");
        displayed++;
    }
    METHOD
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        UpdateReminderHarness app = new UpdateReminderHarness();
        app.canNotify = false;
        app.checkAppUpdate();
        check(app.displayed == 0, "permission denied still notified");
        check(app.ctx.preferences.lastNotified == 0, "permission denied consumed reminder");

        app.canNotify = true;
        app.checkAppUpdate();
        check(app.displayed == 1, "permission grant did not retry reminder");
        check(app.ctx.preferences.lastNotified == 43, "successful reminder not recorded");
        app.checkAppUpdate();
        check(app.displayed == 1, "same version reminder repeated");

        app.remoteVersion = 44;
        app.canNotify = false;
        app.checkAppUpdate();
        check(app.ctx.preferences.lastNotified == 43, "disabled app consumed newer reminder");
        app.canNotify = true;
        app.checkAppUpdate();
        check(app.displayed == 2, "newer version not retried after enablement");
        check(app.ctx.preferences.lastNotified == 44, "newer successful reminder not recorded");
        System.out.println("PASS Android update notification replay; no device invoked");
    }
}
""".replace("METHOD", body)
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "UpdateReminderHarness.java"
            target.write_text(code, encoding="utf-8")
            compilation = subprocess.run(
                [java, "-m", "jdk.compiler/com.sun.tools.javac.Main",
                 "-d", tmp, str(target)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            execution = subprocess.run(
                [java, "-cp", tmp, "UpdateReminderHarness"],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(execution.returncode, 0, execution.stderr)


if __name__ == "__main__":
    unittest.main()
