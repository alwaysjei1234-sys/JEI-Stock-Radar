#!/usr/bin/env python3
"""Read-only LINE recipient diagnostic. Never sends a message or logs profiles."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None  # Never forward a credential to another URL.


def diagnose(enabled,token,recipient,opener=None):
    result={'status':'not_checked','profile_http_status':None,'attempts':0,
            'message_sent':False,'delivery_confirmed':False}
    if str(enabled).lower()!='true':
        result['status']='disabled';return result
    if not token or not isinstance(recipient,str) or not re.fullmatch(r'U[0-9a-f]{32}',recipient):
        result['status']='configuration_missing_or_invalid';return result
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


def main():
    now=datetime.now(ZoneInfo('Asia/Taipei'))
    result=diagnose(os.getenv('JEI_LINE_ENABLED',''),
        os.getenv('JEI_LINE_CHANNEL_ACCESS_TOKEN',''),os.getenv('JEI_LINE_USER_ID',''))
    result['checked_at']=now.isoformat(timespec='seconds')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
