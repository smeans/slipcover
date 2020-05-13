import uuid
import datetime
from functools import wraps

from . import log
from . import admin
from . import Unauthorized401

allow = ['_id', 'created']
deny = ['secret', 'confirm_id']

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

def handle_session_PUT_finish(req):
    if req.surl.doc_id or not req.req_json or not 'email' in req.req_json:
        confirm = {
            '_id': 'confirm:%s' % str(uuid.uuid4()),
            'session_id': req.surl.couchid,
            'secret': str(uuid.uuid4())
        }

        sdb = req.cc[req.surl.db]
        sdb.create_document(confirm)
        assert(sdb.exists())

def handle_confirm_GET_finish(req):
    if not (req.surl.doc_id and b'secret' in req.args):
        return

    sdb = req.cc[req.surl.db]

    if not req.surl.couchid in sdb:
        return

    cd = sdb[req.surl.couchid]

    session = sdb[cd['session_id']]

    if 'confirmed' in session:
        req.log.warn(session['_id'], 'session already confirmed')
        return

    secret = req.args[b'secret'][0].decode()
    if secret == cd['secret']:
        session['confirmed'] = datetime.datetime.now().isoformat()
        session['confirmed_by_ip'] = str(req.getClientIP())
        session.save()

        cd.fetch()

        cd['confirmed'] = datetime.datetime.now().isoformat()
        cd['confirmed_by_ip'] = str(req.getClientIP())
        cd.save()

        # !!!TBD!!! send redirect here to open the app on the mobile device

    req.resp_json = {}

def handle_session_GET_finish(req):
    d = {k: req.resp_json[k] for k in req.resp_json if not k in deny}

    if not req.session or req.session['_id'] != d['_id']:
        d = {k: d[k] for k in d if k in allow}
    else:
        d['is_admin'] = admin.is_admin(req.session['email'])

    req.resp_json = d
