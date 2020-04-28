import uuid
import datetime
from functools import wraps

from . import log
from . import admin

allow = ['_id', 'created']
deny = ['secret']

def get_auth_doc_id(req):
    try:
        aha = req.requestHeaders.getRawHeaders('authorization')
        if aha:
            token = aha[0].split(' ')[1]
            return token.split(':')[1]
    except Exception as e:
        return None

def authenticate(req):
    try:
        aha = req.requestHeaders.getRawHeaders('authorization')
        if not aha:
            return

        method, session_token = aha[0].split(' ')

        _, session_key = session_token.split(':')

        cid = 'session:%s' % session_key

        sdb = req.cc[req.surl.db]

        if not cid in sdb:
            return

        session = sdb[cid]
        session.is_admin = admin.is_admin(session['email'])

        if 'confirmed' in session:
            return session

    except:
        pass

    return None

def auth_only(f):
    @wraps(f)
    def ao_wrapper(*args, **kwargs):
        req = args[0]
        if not hasattr(req, 'session'):
            req.session = authenticate(req)

        if not req.session:
            raise Unauthorized401()

        return f(*args, **kwargs)

    return ao_wrapper

def handle_url(req):
    req.responseHeaders.setRawHeaders('access-control-allow-origin', [b'*'])

    req.session = authenticate(req)
    if req.session:
        log.info(req.request_serial, 'authenticated', req.session['email'])

def handle_session_url(req):
    if not req.surl.doc_id:
        doc_id = get_auth_doc_id(req)
        req.surl.doc_id = doc_id

def handle_session_PUT_pre(req):
    if req.surl.doc_id or not req.req_json or not 'email' in req.req_json:
        req.setResponseCode(403, b'Invalid Request')
        req.responseHeaders.setRawHeaders('content-type', [b'application/json'])
        req.resp_data = b'{}'
        raise ValueError

    req.surl.doc_id = str(uuid.uuid4())
    req.req_json['created'] = datetime.datetime.utcnow().isoformat()
    req.req_json['secret'] = str(uuid.uuid4())

def confirm_session(req, session):
    if 'confirmed' in session:
        return

    secret = req.args[b'secret'][0].decode()
    if secret == session['secret']:
        session['confirmed'] = datetime.datetime.now().isoformat()
        req.log.debug('session pre-save', session)
        session.save()

def handle_session_GET_pre(req):
    if not req.surl.doc_id:
        return

    if b'secret' in req.args:
        sdb = req.cc[req.surl.db]

        if not req.surl.couchid in sdb:
            return

        session = sdb[req.surl.couchid]
        confirm_session(req, session)

def handle_session_GET_finish(req):
    d = {k: req.resp_json[k] for k in req.resp_json if not k in deny}

    if not req.session or req.session['_id'] != d['_id']:
        d = {k: d[k] for k in d if k in allow}

    d['is_admin'] = admin.is_admin(req.session['email'])

    req.resp_json = d
