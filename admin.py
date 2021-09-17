import uuid
import datetime
from functools import wraps

import slipcover
from slipcover import log
from slipcover import sessions
from slipcover import FinishProcessing, Unauthorized401, Forbidden403
from slipcover import config

class AuthException(FinishProcessing):
    pass

def is_admin(email):
    return email in config['admins']

def admin_only(f):
    @wraps(f)
    def ao_wrapper(*args, **kwargs):
        req = args[0]
        if not hasattr(req, 'session'):
            req.session = sessions.authenticate(req)

        if not req.session:
            raise Unauthorized401()

        if not is_admin(req.session['email']):
            raise Forbidden403()

        return f(*args, **kwargs)

    return ao_wrapper

@admin_only
def handle_admin_url(req):
    pass

@admin_only
def handle_admin_POST_pre(req):
    # !!!TBD!!! create BadRequest exception
    req.setResponseCode(200, b'OK')

    if req.req_json['opcode'] == 'shutdown':
        slipcover.shutdown()

    req.responseHeaders.setRawHeaders('content-type', [b'application/json'])
    req.resp_data = b'{}'

    raise FinishProcessing(200)
