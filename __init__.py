#!/usr/bin/env python3
# Derived from logging-proxy.py
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Slipcover is a twisted-driven pluggable proxy intended to sit in front of
CouchDB. It provides the capability to add authentication, access control,
document filtering, etc.
"""
from __future__ import print_function

import os, sys
sys.path.append(os.getcwd())

import time
import requests
import importlib
import json
import urllib

from twisted.internet import ssl, reactor
from twisted.web import proxy, http

from cloudant.client import Cloudant

from slipcover import log

class FinishProcessing(Exception):
    def __init__(self, status=500, message=None, resp_data=None):
        message = message or resources['http_status_codes'][str(status)]

        super().__init__(message)

        self.status = status
        self.message = message.encode()
        self.resp_data = resp_data or b'{}'

class BadRequest400(FinishProcessing):
    def __init__(self, message=None):
        super().__init__(400,  message)

class Unauthorized401(FinishProcessing):
    def __init__(self, message=None):
        super().__init__(401,  message)

class Forbidden403(FinishProcessing):
    def __init__(self, message=None):
        super().__init__(403, message)

class NotFound404(FinishProcessing):
    def __init__(self, message=None):
        super().__init__(404, message)

cc = None
couch_url = os.environ['COUCHURL'] if 'COUCHURL' in os.environ else "http://localhost:5984"

try:
    cc = Cloudant(os.environ['COUCHUSER'], os.environ['COUCHPASS'], url=couch_url, connect=True)
except KeyError:
    log.error('please configure the COUCHUSER and COUCHPASS environment variables')
    exit(1)
except requests.exceptions.HTTPError as e:
    log.error('unable to connect to CouchdB', e)
    exit(1)

cdb = cc['slipcover']
config = cdb['config:master']
resources = config['resources']

handler_modules = [importlib.import_module(name) for name in config['handlers']]

def get_request_serial():
    return int(round(time.time() * 1000))

def shutdown():
    reactor.callFromThread(reactor.stop)

class SlipcoverURL(object):
    db = None
    doc_type = None
    doc_id = None

    def __init__(self, url):
        url = url.split('?')[0]
        uc = list(filter(None, url.split('/')))

        if len(uc) == 1 and not uc[0].startswith('_'):
            self.db = config['default_db']

            ucc = uc[0].split(':')
            self.doc_type = ucc[0]
            if len(ucc) == 2:
                self.doc_id = ucc[1]
        elif len(uc) == 2:
            self.db = config['default_db']
            self.doc_type = uc[0]
            self.doc_id = uc[1]

    @property
    def couchpath(self):
        if self.db and self.doc_type and self.doc_id:
            return '/%s/%s:%s' % (self.db, self.doc_type, urllib.parse.quote(self.doc_id))

        return None

    @property
    def couchid(self):
        return '%s:%s' % (self.doc_type, self.doc_id)

    def __repr__(self):
        return "SlipcoverURL{db='%s', doc_type='%s', doc_id='%s'}" % (self.db, self.doc_type, self.doc_id)

class SlipcoverProxyRequest(proxy.ProxyRequest):
    req_data = None
    req_json = None
    resp_data = None
    resp_json = None

    def __init__(self, channel, queued=http._QUEUED_SENTINEL):
        class RequestLog(object):
            pass

        def _wrap_log_func(level):
            def wf(*args):
                getattr(log, level)(self.request_serial, *args)

            return wf

        self.log = RequestLog()

        for level in log.levels:
            setattr(self.log, level, _wrap_log_func(level))

        super().__init__(channel, queued)
        self.request_serial = get_request_serial()
        self.cc = cc

    def process(self):
        try:
            self.http_method = self.method.decode()
            self.http_uri = self.uri.decode()

            self.content.seek(0, 0)
            self.req_data = self.content.read()

            self.log.info(self.http_method, self.http_uri)
            self.surl = SlipcoverURL(self.http_uri)
            self.fireHandler('url')

            if self.requestHeaders.getRawHeaders('content-type', ['application/bin'])[0] == 'application/json':
                try:
                    self.req_json = json.loads(self.req_data.decode())
                except Exception as e:
                    self.log.debug('malformed JSON in request', e)

            self.fireHandler('pre')
            couchpath = self.surl.couchpath
            if couchpath:
                req_data = json.dumps(self.req_json).encode() if self.req_json else self.req_data
                headers = self.getAllHeaders().copy()
                headers[b'content-length'] = str(len(req_data)).encode('ascii')
                self.log.debug('PROXY: %s %s' % (self.http_method, couchpath))
                clientFactory = proxy.ProxyClientFactory(self.http_method.encode('ascii'), couchpath.encode('ascii'),
                        'http'.encode('ascii'), headers,
                        req_data, self)
                self.reactor.connectTCP('127.0.0.1', 5984, clientFactory)

                self.fireHandler('pending')
            else:
                self.setResponseCode(404, b'Not Found')
                self.resp_data = b'{}'
                self.finish()
        except ValueError as ve:
            self.finish()
        except FinishProcessing as fp:
            self.setResponseCode(fp.status, bytes(fp.message))

            if fp.resp_data:
                self.resp_data = fp.resp_data

            self.finish()
        except Exception as e:
            log.error("processing error", e)
            self.setResponseCode(500, b'Server Error')
            self.resp_data = b'{}'
            self.finish()

    def write(self, data):
        if not self.resp_data:
            self.resp_data = bytearray(data)
        else:
            self.resp_data.extend(data)

    def finish(self):
        try:
            self.resp_json = json.loads(self.resp_data.decode())
        except Exception as e:
            self.log.debug('unable to parse resp_data', e)

        self.fireHandler('finish')

        data = json.dumps(self.resp_json).encode() if not self.resp_json is None else self.resp_data
        self.responseHeaders.setRawHeaders('content-length', [str(len(data)).encode() if data else 0])

        if data:
            super().write(data)

        self.fireHandler('final')
        self.log.info('complete', self.code, self.code_message.decode())
        self.transport.loseConnection()

    def fireHandler(self, type):
        fname_list = ['handle_%s' % type]

        if self.surl.doc_type:
            fname_list.append('handle_%s_%s' % (self.surl.doc_type, type))
            fname_list.append('handle_%s_%s_%s' % (self.surl.doc_type, self.method.decode(), type))

        [[getattr(m, fname)(self) for m in handler_modules if hasattr(m, fname)] for fname in fname_list]

class SlipcoverProxy(proxy.Proxy):
    requestFactory = SlipcoverProxyRequest

class SlipcoverProxyFactory(http.HTTPFactory):
    def buildProtocol(self, addr):
        return SlipcoverProxy()

def start():
    endpoints = config['server_config']['endpoints']

    for endpoint in endpoints:
        log.info('slipcover: listening on port %s (%s)' % (endpoint['port'], endpoint['protocol']))
        port = endpoint['port']
        interface = endpoint['interface'] if 'interface' in endpoint else ''

        if endpoint['protocol'] == 'http':
            reactor.listenTCP(port, SlipcoverProxyFactory(), interface=interface)
        elif endpoint['protocol'] == 'https':
            reactor.listenSSL(endpoint['port'], SlipcoverProxyFactory(),
                          ssl.DefaultOpenSSLContextFactory(
                          'keys/server.key', 'keys/server.cert'),  interface=interface)
    reactor.run()
    log.info('slipcover: exiting')
