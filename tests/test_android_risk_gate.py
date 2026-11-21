"""Run the native risk gate body on a JVM; JSON adapter covers only used accessors.

This is a gate replay, not an Android notification/device delivery test.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index('    ' + signature)
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class AndroidRiskGateTests(unittest.TestCase):
    def test_native_gate_respects_market_suspensions(self):
        java = shutil.which('java')
        if not java:
            self.skipTest('Java compiler runtime required; available in Android CI')
        source = (ROOT / 'app/src/main/java/com/jei/stockradar/RiskWorker.java').read_text()
        signatures = ('private static SimpleDateFormat taipeiParser(',
                      'private static String taipeiFormat(',
                      'static boolean taipeiMarketOpen(',
                      'static boolean trustedLiveFeed(',
                      'static boolean trustedExecutedTrade(',
                      'static JSONObject lastExecution(',
                      'private static double toDouble(')
        bodies = '\n'.join(method(source, s) for s in signatures)
        # Compile the actual production freshness constant into the extracted
        # JVM harness rather than silently testing a separate threshold.
        constants = [line.strip() for line in source.splitlines()
                     if 'MAX_LIVE_LAG_MILLIS =' in line]
        self.assertEqual(len(constants), 1)
        bodies = constants[0] + '\n' + bodies
        harness = '''import java.text.*;
import java.util.*;
public class NativeRiskGateHarness {
  // Minimal adapter, not a replacement for Android org.json or its parser.
  static class JSONObject extends HashMap<String,Object> {
    JSONObject set(String k,Object v){put(k,v);return this;}
    Object opt(String k){return get(k);}
    JSONObject optJSONObject(String k){Object v=get(k);return v instanceof JSONObject?(JSONObject)v:null;}
    String optString(String k,String d){Object v=get(k);return v==null?d:v.toString();}
    boolean optBoolean(String k,boolean d){Object v=get(k);return v instanceof Boolean?(Boolean)v:
      "true".equalsIgnoreCase(String.valueOf(v))?true:"false".equalsIgnoreCase(String.valueOf(v))?false:d;}
  }
  METHODS
  static JSONObject feed(){return new JSONObject().set("data_date","2026-11-10")
    .set("updated_at","2026-11-10 10:00")
    .set("risk",new JSONObject().set("actionable",true).set("as_of","2026-11-10"))
    .set("market",new JSONObject().set("mode","盤中即時").set("stale",false)
      .set("live_valid",true).set("live_count",700).set("close_count",2000));}
  static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
  public static void main(String[] args)throws Exception{
    long now=taipeiParser("yyyy-MM-dd HH:mm").parse("2026-11-10 10:05").getTime();
    JSONObject valid=feed();check(trustedLiveFeed(valid,now),"valid feed rejected");
    JSONObject blocked=feed();blocked.optJSONObject("risk").set("actionable",false);
    check(!trustedLiveFeed(blocked,now),"risk.actionable=false still alerts");
    blocked=feed();blocked.optJSONObject("market").set("no_new_picks",true);
    check(!trustedLiveFeed(blocked,now),"market.no_new_picks=true still alerts");
    blocked=feed();blocked.remove("risk");check(!trustedLiveFeed(blocked,now),"missing risk still alerts");
    blocked=feed();blocked.set("risk","invalid");check(!trustedLiveFeed(blocked,now),"malformed risk still alerts");
    // Legacy risk objects remain compatible, as in LINE's explicit-stop policy.
    valid=feed();valid.optJSONObject("risk").remove("actionable");
    check(trustedLiveFeed(valid,now),"legacy risk object rejected");
    blocked=feed();blocked.optJSONObject("market").set("stale",true);
    check(!trustedLiveFeed(blocked,now),"stale snapshot still alerts");
    blocked=feed();blocked.optJSONObject("market").set("live_count",499);
    check(!trustedLiveFeed(blocked,now),"sparse snapshot still alerts");
    blocked=feed();blocked.optJSONObject("market").set("live_count",699).set("live_coverage_pct",100);
    check(!trustedLiveFeed(blocked,now),"reported coverage must not override the trade count");
    blocked=feed();blocked.optJSONObject("market").set("live_count",699.9);
    check(!trustedLiveFeed(blocked,now),"fractional trade count still alerts");
    blocked=feed();blocked.optJSONObject("market").set("live_count",2001);
    check(!trustedLiveFeed(blocked,now),"more live trades than listed symbols still alerts");
    blocked=feed();blocked.optJSONObject("market").remove("close_count");
    check(!trustedLiveFeed(blocked,now),"missing denominator still alerts");
    blocked=feed();blocked.optJSONObject("market").set("historical_readonly",true);
    check(!trustedLiveFeed(blocked,now),"historical feed still alerts");
    blocked=feed();blocked.optJSONObject("market").set("session_status","休市");
    check(!trustedLiveFeed(blocked,now),"closed exchange still alerts");
    blocked=feed();blocked.optJSONObject("market").set("actionable",false);
    check(!trustedLiveFeed(blocked,now),"market.actionable=false still alerts");
    valid=feed();valid.set("updated_at","2026-11-10 09:55");
    check(trustedLiveFeed(valid,now),"exact 10-minute snapshot rejected");
    blocked=feed();blocked.set("updated_at","2026-11-10 09:54");
    check(!trustedLiveFeed(blocked,now),"11-minute snapshot still alerts");
    blocked=feed();blocked.optJSONObject("risk").set("as_of","2026-11-09");
    check(!trustedLiveFeed(blocked,now),"yesterday risk in today's feed still alerts");
    blocked=feed();blocked.optJSONObject("risk").remove("as_of");
    check(!trustedLiveFeed(blocked,now),"undated risk still alerts");
    blocked=feed();blocked.set("updated_at","2026-11-10 09:00");
    check(!trustedLiveFeed(blocked,now),"old snapshot still alerts");
    blocked=feed();blocked.set("data_date","2026-11-09");
    check(!trustedLiveFeed(blocked,now),"yesterday still alerts");
    check(!trustedLiveFeed(feed(),taipeiParser("yyyy-MM-dd HH:mm").parse("2026-11-10 14:00").getTime()),"closed session still alerts");
    JSONObject trade=new JSONObject().set("d","20261110").set("t","10:04:00")
      .set("z","90").set("y","100").set("v","1234");
    check(trustedExecutedTrade(trade,now),"valid executed trade rejected");
    for(String volume:new String[]{"0","-1","-","NaN","Infinity","1e309",""}){
      trade.set("v",volume);
      check(!trustedExecutedTrade(trade,now),"unexecuted/nonfinite volume accepted: "+volume);
    }
    trade.remove("v");check(!trustedExecutedTrade(trade,now),"missing volume accepted");
    trade.set("v","1234");
    for(String field:new String[]{"z","y"}){
      String original=trade.optString(field,"");
      for(String price:new String[]{"0","-1","-","NaN","Infinity","1e309",""}){
        trade.set(field,price);
        check(!trustedExecutedTrade(trade,now),"invalid price accepted: "+field+"="+price);
      }
      trade.set(field,original);
    }
    trade.set("t","09:56:00");check(!trustedExecutedTrade(trade,now),"old execution accepted");
    trade.set("t","10:04:00").set("d","20261109");
    check(!trustedExecutedTrade(trade,now),"yesterday execution accepted");
    JSONObject book=new JSONObject().set("d","20261110").set("t","10:04:30")
      .set("z","-").set("y","100").set("v","99999")
      .set("trade",new JSONObject().set("t","10:04:00").set("z","90").set("v","1"));
    check(trustedExecutedTrade(book,now),"fresh nested execution skipped");
    check("90".equals(lastExecution(book).optString("z","")),"holding price not nested execution");
    JSONObject nested=book.optJSONObject("trade");
    nested.set("t","09:40:00");
    check(!trustedExecutedTrade(book,now),"old trade borrowed fresh book time");
    nested.set("t","10:04:40");
    check(!trustedExecutedTrade(book,now),"trade after book timestamp accepted");
    nested.set("t","10:04:00").set("d","20261109");
    check(!trustedExecutedTrade(book,now),"nested date mismatch accepted");
    nested.remove("d");nested.set("v","0");
    check(!trustedExecutedTrade(book,now),"nested zero volume borrowed book volume");
    nested.set("v","1").set("z","Infinity");
    check(!trustedExecutedTrade(book,now),"nonfinite nested price accepted");
    nested.set("z","90");book.set("z","NaN");
    check(!trustedExecutedTrade(book,now),"malformed primary price used nested fallback");
    book.set("z","-").set("t","99:00:00");
    check(!trustedExecutedTrade(book,now),"invalid book clock accepted");
    book.set("t","10:04:30");nested.set("t","08:59:00");
    long opening=taipeiParser("yyyy-MM-dd HH:mm").parse("2026-11-10 09:01").getTime();
    check(!trustedExecutedTrade(book,opening),"preopen trade accepted");
    nested.set("t","10:04:00");check(trustedExecutedTrade(book,now),"restored nested trade rejected");

    System.out.println("PASS native risk gate replays; no notification/network/device invoked");
  }
}'''.replace('METHODS', bodies)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'NativeRiskGateHarness.java'
            path.write_text(harness)
            result = subprocess.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main',
                                     '-d', tmp, str(path)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([java, '-cp', tmp, 'NativeRiskGateHarness'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
