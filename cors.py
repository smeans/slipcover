import log
import uuid
import datetime

def handle_session_url(req):
    if req.method == b'OPTIONS':
        req.responseHeaders.setRawHeaders('access-control-allow-origin', [b'*'])
        req.responseHeaders.setRawHeaders('allow', [b'*'])
        req.responseHeaders.setRawHeaders('access-control-allow-methods', [b'POST, GET, PUT, DELETE, OPTIONS'])
        req.responseHeaders.setRawHeaders('access-control-allow-headers', [b'*'])

        req.setResponseCode(200, b'OK')
        req.responseHeaders.setRawHeaders('content-type', [b'application/json'])
        req.resp_data = b'{}'
        raise ValueError
