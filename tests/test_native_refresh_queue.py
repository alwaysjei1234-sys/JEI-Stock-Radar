"""Execute the actual Android bridge method bodies on a JVM with fake I/O.

No Android SDK, network, credentials or live WebView is needed. This verifies
admission before enqueueing, callback completion, and retry after failures.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JAVA_DIR = ROOT / 'app/src/main/java/com/jei/stockradar'


def method(source, name):
    start = source.index('    private void ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class NativeRefreshQueueTests(unittest.TestCase):
    def test_real_bridge_bursts_errors_and_retries(self):
        java = shutil.which('java')
        if not java:
            self.skipTest('Java compiler runtime is required (provided by Android CI)')
        source = (JAVA_DIR / 'MainActivity.java').read_text()
        bodies = '\n'.join(method(source, name) for name in
                           ('fetchSystem', 'fetchStaticJson', 'checkUpdate'))
        gate = ('private final RequestGate staticRequests = new RequestGate();'
                if 'RequestGate staticRequests' in source else '')
        harness = '''package com.jei.stockradar;
import java.util.*;
import java.util.concurrent.*;
public class BridgeQueueHarness {
  static class Queue implements Executor {
    final List<Runnable> pending = new ArrayList<>();
    boolean reject;
    public void execute(Runnable r) {
      if (reject) throw new RejectedExecutionException();
      pending.add(r);
    }
    void drain() { while (!pending.isEmpty()) pending.remove(0).run(); }
  }
  final Queue io = new Queue();
  static final String SYSTEM_JSON="system", DAILY_JSON="daily",
      PERFORMANCE_JSON="performance", UPDATE_JSON="update";
  int callbacks=0, calls=0;
  boolean fail;
  String getRemoteStatic(String url) throws Exception {
    calls++; if(fail)throw new Exception("synthetic offline"); return "{}";
  }
  void jsCall(String name,String value){ callbacks++; }
  void jsStatic(String name,String kind,String value){ callbacks++; }
  static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
  GATE
  METHODS
  public static void main(String[] args) {
    BridgeQueueHarness b = new BridgeQueueHarness();
    for(int i=0;i<100;i++){
      b.fetchSystem(); b.checkUpdate(); b.fetchStaticJson("daily");
      b.fetchStaticJson("performance"); b.fetchStaticJson("invalid");
    }
    check(b.io.pending.size()==4,"burst queued "+b.io.pending.size()+" tasks instead of 4");
    check(b.calls==0,"network work ran on submitting thread");
    b.io.drain(); check(b.calls==4 && b.callbacks==4,"completion callbacks missing");
    b.fail=true;
    b.fetchSystem();b.checkUpdate();b.fetchStaticJson("daily");b.fetchStaticJson("performance");
    b.io.drain();check(b.callbacks==8,"failure callbacks missing");
    b.fail=false;
    b.fetchSystem();b.checkUpdate();b.fetchStaticJson("daily");b.fetchStaticJson("performance");
    check(b.io.pending.size()==4,"failed request blocked retry");b.io.drain();
    b.io.reject=true;
    try{b.fetchSystem();throw new AssertionError("rejection expected");}
    catch(RejectedExecutionException expected){}
    b.io.reject=false;b.fetchSystem();
    check(b.io.pending.size()==1,"rejected request blocked retry");b.io.drain();
    List<Thread> callers = new ArrayList<>();
    for(int i=0;i<32;i++) callers.add(new Thread(b::fetchSystem));
    for(Thread t:callers)t.start();
    for(Thread t:callers)try{t.join();}catch(InterruptedException e){throw new AssertionError(e);}
    check(b.io.pending.size()==1,"concurrent duplicate requests queued");b.io.drain();
    System.out.println("PASS actual bridge: 400 calls -> 4 queued; errors/retries/rejection/races");
  }
}'''.replace('GATE', gate).replace('METHODS', bodies)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'BridgeQueueHarness.java'
            path.write_text(harness)
            files = [str(path)]
            if (JAVA_DIR / 'RequestGate.java').exists():
                files.append(str(JAVA_DIR / 'RequestGate.java'))
            compiled = subprocess.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main',
                                       '-d', tmp, *files], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([java, '-cp', tmp, 'com.jei.stockradar.BridgeQueueHarness'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
