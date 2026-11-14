#!/usr/bin/env python3
"""Read-only LINE recipient diagnostic. Never sends a message or logs profiles."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.send_line_brief import quota_ok


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None  # Never forward a credential to another URL.


def diagnose(enabled,token,recipient,opener=None,*,check_quota=False):
    result={'status':'not_checked','profile_http_status':None,'attempts':0,
            'message_sent':False,'delivery_confirmed':False}
    if check_quota:
        result['quota_policy'] = 'not_checked'
    if str(enabled).lower() != 'true':
        result['status'] = 'disabled'
        return result
    issues = []
    if not token:
        issues.append('token_missing')
    if not recipient:
        issues.append('recipient_missing')
    elif not isinstance(recipient, str) or not re.fullmatch(r'U[0-9a-f]{32}', recipient):
        issues.append('recipient_format_invalid')
    if issues:
        result.update(status='configuration_missing_or_invalid', configuration_issues=issues)
        return result
    opener=opener or urllib.request.build_opener(NoRedirect())
    for attempt in range(1,3):
        result['attempts']=attempt
        result['profile_http_status']=None
        try:
            request=urllib.request.Request('https://api.line.me/v2/bot/profile/'+recipient,
                headers={'Authorization':'Bearer '+token,'Accept':'application/json'},method='GET')
            with opener.open(request,timeout=10) as response:
                status=response.status
                result['profile_http_status']=status
                if status!=200:
                    result['status']='unexpected_response';return result
                body=response.read(65537)
                if len(body)>65536:
                    result['status']='invalid_response';return result
                profile=json.loads(body)
                # Bind the response to the configured recipient in memory only.
                # No name, picture, user ID, URL, request ID or body is retained.
                result['status']=('profile_accessible' if isinstance(profile,dict)
                    and profile.get('userId')==recipient else 'profile_mismatch')
                if check_quota and result['status'] == 'profile_accessible':
                    try:
                        result['quota_policy'] = 'eligible' if quota_ok(token) else 'blocked'
                    except (OSError, ValueError, RuntimeError):
                        result['quota_policy'] = 'unavailable'
                return result
        except urllib.error.HTTPError as error:
            status=error.code
            result['profile_http_status']=status
            result['status']={400:'recipient_rejected',401:'token_rejected',
                403:'permission_denied',404:'recipient_unavailable',
                429:'rate_limited'}.get(status,'service_error' if 500<=status<600 else 'unexpected_response')
            # A 404 alone cannot distinguish consent, friendship, blocking or a
            # recipient from a different provider. Never label it "blocked".
            if not 500<=status<600 or attempt==2:return result
        except (OSError,TimeoutError):
            result['status']='network_error'
            if attempt==2:return result
        except (ValueError,TypeError,UnicodeDecodeError):
            result['status']='invalid_response';return result
        time.sleep(1)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-path', type=Path)
    parser.add_argument('--check-quota', action='store_true')
    args = parser.parse_args(argv)
    now=datetime.now(ZoneInfo('Asia/Taipei'))
    result=diagnose(os.getenv('JEI_LINE_ENABLED',''),
        os.getenv('JEI_LINE_CHANNEL_ACCESS_TOKEN',''),os.getenv('JEI_LINE_USER_ID',''), check_quota=args.check_quota)
    result['checked_at']=now.isoformat(timespec='seconds')
    payload = json.dumps(result, ensure_ascii=False)
    if args.result_path:
        args.result_path.parent.mkdir(parents=True, exist_ok=True)
        args.result_path.write_text(payload + '\n', encoding='utf-8')
    print(payload)


if __name__=='__main__':main()
