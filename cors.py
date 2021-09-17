import uuid
import datetime

from slipcover import FinishProcessing
from slipcover import log

def handle_session_url(req):
    if req.method == b'OPTIONS':
        req.responseHeaders.setRawHeaders('access-control-allow-origin', [b'*'])
        req.responseHeaders.setRawHeaders('allow', [b'*'])
        req.responseHeaders.setRawHeaders('access-control-allow-methods', [b'POST, GET, PUT, DELETE, OPTIONS'])
        req.responseHeaders.setRawHeaders('access-control-allow-headers', [b'*'])

        raise FinishProcessing(200)
