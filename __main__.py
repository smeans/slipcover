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

from twisted.internet import reactor
from twisted.web import proxy, http

from cloudant.client import Cloudant

import log

cc = None
try:
    cc = Cloudant(os.environ['COUCHUSER'], os.environ['COUCHPASS'], url="http://localhost:5984", connect=True)
except KeyError:
    log.error('please configure the COUCHUSER and COUCHPASS environment variables')
    exit(1)
except requests.exceptions.HTTPError as e:
    log.error('unable to connect to CouchdB', e)
    exit(1)

cdb = cc['slipcover']
config = cdb['config']
handler_modules = [importlib.import_module(name) for name in config['handlers']]

def get_request_serial():
    return int(round(time.time() * 1000))

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
            return '/%s/%s:%s' % (self.db, self.doc_type, self.doc_id)

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
        super().__init__(channel, queued)
        self.request_serial = get_request_serial()
        self.cc = cc

    def process(self):
        try:
            self.http_method = self.method.decode()
            self.http_uri = self.uri.decode()

            self.content.seek(0, 0)
            self.req_data = self.content.read()

            log.info(self.request_serial, self.http_method, self.http_uri)
            self.surl = SlipcoverURL(self.http_uri)
            self.fireHandler('url')

            if self.requestHeaders.getRawHeaders('content-type', ['application/bin'])[0] == 'application/json':
                try:
                    self.req_json = json.loads(self.req_data.decode())
                except Exception as e:
                    log.debug('malformed JSON in request', e)

            self.fireHandler('pre')
            couchpath = self.surl.couchpath
            if couchpath:
                req_data = json.dumps(self.req_json).encode() if self.req_json else self.req_data
                headers = self.getAllHeaders().copy()
                headers[b'content-length'] = str(len(req_data)).encode('ascii')
                clientFactory = proxy.ProxyClientFactory(self.method, couchpath.encode('ascii'),
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
        except Exception as e:
            log.error("processing error", e)
            self.setResponseCode(500, b'Server Error')
            self.resp_data = b'{}'
            self.finish()

    def write(self, data):
        if not self.resp_data:
            self.resp_data = bytes(data)
        else:
            self.resp_data.extend(data)

    def finish(self):
        try:
            self.resp_json = json.loads(self.resp_data.decode())
        except Exception as e:
            log.debug('unable to parse resp_data', e)
            pass

        self.fireHandler('finish')

        data = json.dumps(self.resp_json).encode() if self.resp_json else self.resp_data
        self.responseHeaders.setRawHeaders('content-length', [str(len(data)).encode()])

        if data:
            super().write(data)

        self.fireHandler('final')
        log.info(self.request_serial, 'complete', self.code, self.code_message.decode())
        self.transport.loseConnection()

    def fireHandler(self, type):
        if self.surl.doc_type:
            fname = 'handle_%s_%s' % (self.surl.doc_type, type)
            [getattr(m, fname)(self) for m in handler_modules if hasattr(m, fname)]
            fname = 'handle_%s_%s_%s' % (self.surl.doc_type, self.method.decode(), type)
            [getattr(m, fname)(self) for m in handler_modules if hasattr(m, fname)]

class SlipcoverProxy(proxy.Proxy):
    requestFactory = SlipcoverProxyRequest

class SlipcoverProxyFactory(http.HTTPFactory):
    def buildProtocol(self, addr):
        return SlipcoverProxy()

if __name__ == '__main__':
    if 'http_port' in config['server_config']:
        reactor.listenTCP(config['server_config']['http_port'], SlipcoverProxyFactory())
    reactor.run()
