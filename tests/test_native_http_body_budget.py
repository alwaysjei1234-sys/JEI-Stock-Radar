"""Replay actual Android static HTTP reads against a local slow-body server.

Only the network URLs, 12-second read budget and 16-MiB size limit are scaled
in the JVM harness. No Android device, credentials or external API is used.
"""
import http.server
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

from test_native_refresh_queue import JAVA_DIR, method


class BodyServer(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        body = (b'x' * 40 if path == '/slow.html' else
                b'x' * 200 if path == '/large' else
                'JEI_REMOTE_UI_V3 台股\n'.encode())
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            if path == '/slow.html':
                # No newline: readLine cannot return while bytes keep arriving.
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(.05)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class NativeHttpBodyBudgetTests(unittest.TestCase):
    def test_trickling_primary_falls_back_and_oversized_body_is_rejected(self):
        java = shutil.which('java')
        if not java:
            self.skipTest('Java compiler runtime required; provided by Android CI')
        source = (JAVA_DIR / 'MainActivity.java').read_text()
        bodies = method(source, 'httpGet', 'String')
        if 'private String readStaticBody(' in source:
            bodies += '\n' + method(source, 'readStaticBody', 'String')
        bodies += '\n' + method(source, 'getRemoteStatic', 'String')
        # Scale only the actual runtime limits, never replace read/fallback logic.
        bodies = bodies.replace('12000', '300').replace('16 * 1024 * 1024', '64')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), BodyServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        bodies = bodies.replace(
            'https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/',
            base + '/fallback/')
        code = '''
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
public class NativeHttpBodyHarness {
  static final String REMOTE_UI="BASE/slow.html", SYSTEM_JSON="system",
    UPDATE_JSON="update", DAILY_JSON="daily", PERFORMANCE_JSON="performance",
    CASH_UI="cash", PAPER_UI="paper";
  boolean validStatic(String url,String body){return body.contains("JEI_REMOTE_UI_V3");}
  METHODS
  public static void main(String[] args) throws Exception {
    NativeHttpBodyHarness h=new NativeHttpBodyHarness();
    String good=h.httpGet("BASE/good");
    if(!good.contains("台股"))throw new AssertionError("UTF-8 payload changed");
    long started=System.nanoTime();
    String backup=h.getRemoteStatic(REMOTE_UI);
    long elapsed=(System.nanoTime()-started)/1000000;
    if(!backup.contains("JEI_REMOTE_UI_V3") || elapsed>1200)
      throw new AssertionError("trickling primary delayed fallback: "+elapsed+"ms");
    try {h.httpGet("BASE/large");throw new AssertionError("oversized body accepted");}
    catch(IOException expected){}
    if(!h.httpGet("BASE/good").contains("台股"))
      throw new AssertionError("failure prevented later request");
    System.out.println("PASS real HTTP: UTF-8, trickle fallback "+elapsed+"ms, size limit, retry");
  }
}'''.replace('BASE', base).replace('METHODS', bodies)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / 'NativeHttpBodyHarness.java'
                path.write_text(code)
                compiled = subprocess.run(
                    [java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-d', tmp, str(path)],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                run = subprocess.run([java, '-cp', tmp, 'NativeHttpBodyHarness'],
                                     capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stderr)
                print(run.stdout.strip())
        finally:
            server.shutdown()
            server.server_close()



class BackgroundBodyServer(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/slow.json':
            body = b'{"market":{},"source":"slow-primary","padding":"1234567890"}'
        elif path == '/large':
            body = b'x' * 200
        else:
            body = '{"market":{},"source":"backup","text":"台股"}'.encode()
        self.send_response(503 if path == '/unavailable' else 200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            if path == '/slow.json':
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(.04)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class BackgroundHttpBodyBudgetTests(unittest.TestCase):
    def test_background_trickle_releases_risk_and_update_fallback(self):
        java = shutil.which('java')
        if not java:
            self.skipTest('Java compiler runtime required; provided by Android CI')
        source = (JAVA_DIR / 'RiskWorker.java').read_text()
        bodies = method(source, 'get', 'String')
        if 'private String readBody(' in source:
            bodies += '\n' + method(source, 'readBody', 'String')
        bodies += '\n' + method(source, 'getStaticFeed', 'String')
        bodies = bodies.replace('12000', '300').replace('16 * 1024 * 1024', '64')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), BackgroundBodyServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        bodies = bodies.replace(
            'https://raw.githubusercontent.com/alwaysjei1234-sys/JEI-Stock-Radar/main/remote/',
            base + '/fallback/')
        harness = '''import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
public class BackgroundBodyHarness {
  // Only the has accessor is needed by the extracted production fallback.
  // This adapter is not an Android JSON parser/device test.
  static class JSONObject {
    final String text;
    JSONObject(String text){this.text=text;}
    boolean has(String key){return text.contains("\\\""+key+"\\\"");}
  }
  static final String SYSTEM_JSON="BASE/slow.json", UPDATE_JSON="BASE/update.json";
  METHODS
  public static void main(String[] args)throws Exception{
    BackgroundBodyHarness h=new BackgroundBodyHarness();
    long started=System.nanoTime();
    String result=h.getStaticFeed(SYSTEM_JSON);
    long elapsed=(System.nanoTime()-started)/1000000;
    if(!result.contains("backup") || !result.contains("台股") || elapsed>1200)
      throw new AssertionError("background slow body prevented fallback: "+elapsed+"ms");
    try{h.get("BASE/large");throw new AssertionError("oversized background body accepted");}
    catch(IOException expected){}
    try{h.get("BASE/unavailable");throw new AssertionError("503 accepted");}
    catch(Exception expected){if(!expected.getMessage().contains("HTTP 503"))throw expected;}
    if(!h.getStaticFeed(UPDATE_JSON).contains("台股"))
      throw new AssertionError("body failure prevented the next update check");
    System.out.println("PASS background real HTTP: trickle fallback "+elapsed+"ms, size bound, HTTP failure, next update read");
  }
}'''.replace('BASE',base).replace('METHODS',bodies)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path=pathlib.Path(tmp)/'BackgroundBodyHarness.java'
                path.write_text(harness)
                compiled=subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',tmp,str(path)],
                    capture_output=True,text=True,timeout=30)
                self.assertEqual(compiled.returncode,0,compiled.stderr)
                run=subprocess.run([java,'-cp',tmp,'BackgroundBodyHarness'],capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stderr)
                print(run.stdout.strip())
        finally:
            server.shutdown();server.server_close()


if __name__ == '__main__':
    unittest.main()
