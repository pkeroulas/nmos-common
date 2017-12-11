# Copyright 2017 British Broadcasting Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import mock

from nmoscommon.webapi import *

from datetime import timedelta

import flask

class TestWebAPI(unittest.TestCase):

    @mock.patch("nmoscommon.webapi.Flask")
    @mock.patch("nmoscommon.webapi.Sockets")
    def initialise_webapi_with_method_using_decorator(self, mock_webapi_method, decorator, Sockets, Flask, oauth_userid=None, expect_paths_below=False, is_socket=False, on_websocket_connect=None):
        """Returns a pair of the wrapped function that would be sent to flask.app.route, and the parameters which would
        be passed to flask.app.route for it."""
        def TEST(self, *args, **kwargs):
            return mock_webapi_method(*args, **kwargs)

        class StubWebAPI(WebAPI):
            pass

        if on_websocket_connect is not None:
            def _on_websocket_connect(*args, **kwargs):
                return on_websocket_connect(*args, **kwargs)
            StubWebAPI.on_websocket_connect = _on_websocket_connect

        StubWebAPI.TEST = decorator(TEST)
        basemethod = StubWebAPI.TEST

        UUT = StubWebAPI()
        if oauth_userid is not None:
            UUT._oauth_config = { "loginserver" : "LOGINSERVER", "proxies" : { "http" : "HHTPPROXY", "https" : "HTTPSPROXY" }, 'access_whitelist' : [ oauth_userid, ] }
        Flask.assert_called_once_with('nmoscommon.webapi')
        app = Flask.return_value

        self.assertEqual(app.response_class, IppResponse)
        app.before_first_request.assert_called_once_with(mock.ANY)
        torun = app.before_first_request.call_args[0][0]
        Sockets.assert_called_once_with(app)

        if is_socket:
            Sockets.return_value.route.assert_called_once_with('/', endpoint="_TEST")
            Sockets.return_value.route.return_value.assert_called_once_with(mock.ANY)
            return (Sockets.return_value.route.return_value.call_args[0][0], UUT, [ (call[1], call[2]) for call in Sockets.return_value.route.mock_calls if call[0] == '' ])
        elif not expect_paths_below:
            app.route.assert_called_once_with('/',
                                            endpoint="_TEST",
                                            methods=mock.ANY)
            app.route.return_value.assert_called_once_with(mock.ANY)
        else:
            self.assertItemsEqual((call for call in app.route.mock_calls if call[0] == ''), [
                mock.call('/', endpoint="_TEST", methods=mock.ANY),
                mock.call('/<path:path>/', endpoint="_TEST_path", methods=mock.ANY), ])
            self.assertItemsEqual((call for call in app.route.return_value.mock_calls if call[0] == ''), [
                mock.call(mock.ANY),
                mock.call(mock.ANY), ])
        return (app.route.return_value.call_args[0][0], UUT, [ (call[1], call[2]) for call in app.route.mock_calls if call[0] == '' ])

    @mock.patch('nmoscommon.webapi.http.urlopen')
    @mock.patch('nmoscommon.webapi.http.install_opener')
    @mock.patch('nmoscommon.flask_cors.make_response', side_effect=lambda x:x)
    @mock.patch('nmoscommon.flask_cors.request')
    def assert_wrapped_route_method_returns(self, f, expected, request, make_response, install_opener, urlopen, method="GET", args=[], kwargs={}, best_mimetype='application/json', request_headers=None, oauth_userid=None, oauth_token=None, ignore_body=False):
        with mock.patch('nmoscommon.webapi.request', request):
            if oauth_userid is not None:
                # this method is called by the default_authorizer when oauth credentials are checked
                urlopen.return_value.read.return_value = json.dumps({ 'userid' : oauth_userid, 'token' : oauth_token })
                urlopen.return_value.code = 200
            request.method = method
            request.host = "example.com"
            if best_mimetype == TypeError:
                request.accept_mimetypes.best_match.side_effect = best_mimetype
            else:
                request.accept_mimetypes.best_match.return_value = best_mimetype
            if request_headers is not None:
                request.headers = request_headers
            else:
                request.headers = {}

            class TESTABORT(Exception):
                def __init__(self, code):
                    self.code = code
                    super(TESTABORT, self).__init__()

            def raise_code(n):
                raise TESTABORT(n)
            with mock.patch('nmoscommon.webapi.abort', side_effect=raise_code):
                try:
                    r = f(*args, **kwargs)
                except TESTABORT as e:
                    if isinstance(expected, int):
                        self.assertEqual(e.code,expected, msg="Expected abort with code %d, got abort with code %d" % (expected, e.code))
                    else:
                        self.fail(msg="Got unexpected abort with code %d when expecting a returned Response" % (e.code,))
                else:
                    if isinstance(expected, int):
                        self.fail(msg="Got unexpected Response object when expecting an abort with code %d" % (expected, ))
                    else:
                        if ignore_body:
                            expected.response = r.response
                            expected.headers['Content-Length'] = r.headers['Content-Length']
                        self.assertEqual(r, expected, msg="""

Expected IppResponse(response=%r,\n status=%r,\n headers=%r,\n mimetype=%r,\n content_type=%r\n, direct_passthrough=%r)

Got IppResponse(response=%r,\n status=%r,\n headers=%r,\n mimetype=%r,\n content_type=%r,\n direct_passthrough=%r)""" % (expected.get_data(),
                                                                                                                             expected.status,
                                                                                                                             dict(expected.headers),
                                                                                                                             expected.mimetype,
                                                                                                                             expected.content_type,
                                                                                                                             expected.direct_passthrough,
                                                                                                                             r.get_data(),
                                                                                                                             r.status,
                                                                                                                             dict(r.headers),
                                                                                                                             r.mimetype,
                                                                                                                             r.content_type,
                                                                                                                             r.direct_passthrough))

    def perform_test_on_decorator(self, data):
        """This method will take a mock method and wrap it with a specified decorator, then create a webapi class instance with that method as a member.
        It will check that the object automatically registers the 

        The format of the input is as dictionary, with several keys which must be provided, and many which may:

        Mandatory keys:

        'methods'     -- This is a list of strings which are the HTTP methods with which the route is expected to be registered with Flask.
        'path'        -- This is the path that is expected to be passed to Flask when the method is registered.
        'return_data' -- This is the value that will be returned by the wrapped method when it is called.
        'method'      -- This is the HTTP method which will be provided in the call that is made to the wrapped function for testing.
        'decorator'   -- This is the decorator we are testing, it must be a callable object which takes a single function as a parameter and returns a callable
        'expected'    -- This is the expected response which will be sent to the Flask subsystem for output by the wrapped method when it is called. If set to mock.ANY then
                         any result will be acceptable, if it is set to an integer then we expect 'abort' to be called with that status code.

        Optional Keys:

        'headers'         -- These headers will be included in the mock request when the wrapped method is called.
        'oauth_userid'    -- if present then the call will be performed in a mock Flask environment which implements oauth, and this value will be returned by the mock 
                             credentials server as an acceptable user id.
        'oauth_whitelist' -- if present when 'oauth_userid' is also specified then this value will be added to the mock whitelist of acceptable user ids. If not specified then
                             the value of 'oauth_userid' will be put on this whitelist instead.
        'oauth_token      -- if present when 'oauth_userid' is also specified then this value will be returned by the mock credentials server as an acceptable authorisation token.
        'best_type'       -- If the code attempts to determine what the best mime-type to use for a return format then it will be given this value,
                             alternatively set this to TypeError to mimick the behaviour when none of the acceptible types is available.
        'extract_path'    -- If this is included and set to true then the wrapped function will be called with this value as a parameter as if it were a path
        'ignore_body'     -- If this is set to true then the contents of the body of the 'expected' request will be forced to the same value as the body of the returned response
                             before a comparison is performed. Metadata, headers, etc ... are still compared.
"""
        method = mock.MagicMock(name="webapi", return_value=data['return_data'])

        (f, UUT, calls) = self.initialise_webapi_with_method_using_decorator(method, data['decorator'], oauth_userid=data.get('oauth_whitelist',data.get('oauth_userid', None)), expect_paths_below=('extract_path' in data))
        self.assertIn("_TEST", (kwargs['endpoint'] for (args, kwargs) in calls))
        self.assertTrue(all((kwargs['endpoint'].startswith("_TEST") for (args, kwargs) in calls)))
        for (args, kwargs) in calls:
            # Check that flask was given through the expected commands
            self.assertEqual(kwargs['methods'], data['methods'] + ["OPTIONS"])

        kwargs = {}
        if 'extract_path' in data:
            kwargs = { 'path' : data['extract_path'] }
        self.assert_wrapped_route_method_returns(f, data['expected'],
                                                     method=data.get('method',"GET"),
                                                     best_mimetype=data.get('best_type',None),
                                                     request_headers=data.get('headers',None),
                                                     oauth_userid=data.get('oauth_userid', None),
                                                     oauth_token=data.get('oauth_token',None),
                                                     kwargs=kwargs,
                                                     ignore_body=data.get('ignore_body', False))

    def test_secure_route__GET__json(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_secure_route__GET__without_specified_methods(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "HEAD"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, HEAD',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_secure_route__GET__without_specified_headers(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_secure_route__GET__with_TypeError_when_checking_best_mime_type(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : TypeError,
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(status=204,
                                            headers={'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age'      : u'21600',
                                                     'Cache-Control'               : u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Origin' : u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type'                : u'text/html; charset=utf-8'},
                                            mimetype=u'text/html',
                                            content_type=u'text/html; charset=utf-8',
                                            direct_passthrough=False),
            })

    def test_secure_route__GET__with_string_data(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : "POTATO",
                'method'      : "GET",
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Credentials': u'true',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
            })

    def test_secure_route__GET__with_wrapped_method_returning_IppResponse(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : IppResponse(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Credentials': u'true',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
                'method'      : "GET",
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Credentials': u'true',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
            })

    def test_secure_route__GET__with_wrapped_method_returning_Response(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : Response(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Credentials': u'true',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
                'method'      : "GET",
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Credentials': u'true',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
            })

    def test_secure_route__GET__html(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'text/html',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(    status=200,
                                                headers={    'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                             'Access-Control-Max-Age': u'21600',
                                                             'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                             'Access-Control-Allow-Origin': u'example.com',
                                                             'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                             'Content-Type': u'text/html; charset=utf-8'},
                                                mimetype=u'text/html',
                                                content_type=u'text/html; charset=utf-8',
                                                direct_passthrough=False),
                'ignore_body' : True
            })

    def test_secure_route__GET__with_wrapped_method_returning_list(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : [ 'foo', 'bar', 'baz', 'boop',],
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps([ 'foo', 'bar', 'baz', 'boop',], indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_secure_route__GET__with_good_userid_and_no_token(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'oauth_userid': "FAKE_USER_ID",
                'expected'    : IppResponse(status=401,
                                            headers={ 'Access-Control-Allow-Origin' : u'example.com',
                                                      'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                      'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                      'Access-Control-Max-Age'      : u'21600',
                                                      'Cache-Control'               : u'no-cache, must-revalidate, no-store',
                                                      'Content-Type'                : u'text/html; charset=utf-8' }),
            })

    def test_secure_route__GET__with_good_userid_and_bad_token(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'headers'     : { 'token' : "jkhndgkjsj.jkuhjhn" },
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'oauth_userid': "FAKE_USER_ID",
                'oauth_token' : None,
                'expected'    : IppResponse(status=401,
                                            headers={ 'Access-Control-Allow-Origin' : u'example.com',
                                                      'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                      'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                      'Access-Control-Max-Age'      : u'21600',
                                                      'Cache-Control'               : u'no-cache, must-revalidate, no-store',
                                                      'Content-Type'                : u'text/html; charset=utf-8' }),
            })

    def test_secure_route__GET__with_bad_userid_and_good_token(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'headers'     : { 'token' : "jkhndgkjsj.jkuhjhn" },
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'oauth_userid': "FAKE_USER_ID",
                'oauth_whitelist' : "OTHER_USER_ID",
                'oauth_token' : "jkhndgkjsj.jkuhjhn",
                'expected'    : IppResponse(status=401,
                                            headers={ 'Access-Control-Allow-Origin' : u'example.com',
                                                      'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                      'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                      'Access-Control-Max-Age'      : u'21600',
                                                      'Cache-Control'               : u'no-cache, must-revalidate, no-store',
                                                      'Content-Type'                : u'text/html; charset=utf-8' }),
            })

    def test_secure_route__GET__with_good_userid_and_good_token(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'headers'     : { 'token' : "jkhndgkjsj.jkuhjhn" },
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'oauth_userid': "FAKE_USER_ID",
                'oauth_token' : "jkhndgkjsj.jkuhjhn",
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                            status=200,
                                            headers= {'Content-Length': u'56',
                                                          'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                          'Access-Control-Max-Age': u'21600',
                                                          'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                          'Access-Control-Allow-Credentials': u'true',
                                                          'Access-Control-Allow-Origin': u'example.com',
                                                          'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                          'Content-Type': u'application/json'},
                                            mimetype=u'application/json',
                                            content_type=u'application/json',
                                            direct_passthrough=False),
            })

    def test_secure_route__GET__with_wrapped_method_returning_status_code(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : (201, { 'foo' : 'bar', 'baz' : ['boop',] }),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=201,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_secure_route__GET__with_wrapped_method_returning_status_code_and_headers(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : (201, { 'foo' : 'bar', 'baz' : ['boop',] }, {'X-A-HEADER' : 'AVALUE'}),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : secure_route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=201,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Credentials' : u'true',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE, TOKEN',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56,
                                                                              'X-A-HEADER'                       : 'AVALUE'},
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })


    def test_route__GET__json(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__without_autojson(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                status=200,
                                                                content_type=u'application/json'),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=False, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__without_autojson_or_methods(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "HEAD"],
                'path'        : '/',
                'return_data' : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                status=200,
                                                                content_type=u'application/json'),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', auto_json=False, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, HEAD',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__without_methods(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "HEAD"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, HEAD',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__without_headers(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__with_wrapped_method_returning_status(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : (201, { 'foo' : 'bar', 'baz' : ['boop',] }),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=201,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__with_wrapped_method_returning_status_and_headers(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : (201, { 'foo' : 'bar', 'baz' : ['boop',] }, {'X-A-HEADER' : 'AVALUE'}),
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=201,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'X-A-HEADER'                       : u'AVALUE',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__with_wrapped_method_returning_list(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : [ 'foo' , 'bar', 'baz' , 'boop', ],
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, origin="example.com"),
                'expected'    : IppResponse(response=json.dumps([ 'foo' , 'bar', 'baz' , 'boop', ], indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'example.com',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json'),
            })

    def test_route__GET__html(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : 'text/html',
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(    status=200,
                                                headers={    'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                             'Access-Control-Max-Age': u'21600',
                                                             'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                             'Access-Control-Allow-Origin': u'example.com',
                                                             'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                             'Content-Type': u'text/html; charset=utf-8'},
                                                mimetype=u'text/html',
                                                content_type=u'text/html; charset=utf-8',
                                                direct_passthrough=False),
                'ignore_body' : True
            })

    def test_route__GET__without_matching_type(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'best_type'   : TypeError,
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(status=204,
                                            headers={'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'},
                                            direct_passthrough=False)
            })

    def test_route__GET__with_string_data(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO"],
                'path'        : '/',
                'return_data' : "POTATO",
                'method'      : "GET",
                'decorator'   : route('/', methods=["GET", "POST", "POTATO"], auto_json=True, headers=["x-not-a-real-header",], origin="example.com"),
                'expected'    : IppResponse(response="POTATO",
                                            status=200,
                                            headers={'Content-Length': u'6',
                                                     'Access-Control-Allow-Headers': u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                     'Access-Control-Max-Age': u'21600',
                                                     'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                     'Access-Control-Allow-Origin': u'example.com',
                                                     'Access-Control-Allow-Methods': u'GET, POST, POTATO',
                                                     'Content-Type': u'text/html; charset=utf-8'}),
            })

    def test_basic_route__GET(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "HEAD"],
                'path'        : '/',
                'return_data' : Response(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                         status=200,
                                         mimetype=u'application/json',
                                         content_type=u'application/json'),
                'method'      : "GET",
                'decorator'   : basic_route('/'),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, HEAD, POST',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'*',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Type'                     : u'application/json',
                                                                              'Content-Length'                   : 56 },
                                                                    mimetype=u'application/json',
                                                                    content_type=u'application/json',
                                                                    direct_passthrough=True),
            })

    def test_file_route__GET(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'content' : "POJNDCJSL", 'filename' : "afile", "type" : 'zog' },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : file_route('/', methods=["GET", "POST", "POTATO"], headers=["x-not-a-real-header",]),
                'expected'    : IppResponse(response="POJNDCJSL",
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'*',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                                              'Content-Disposition'              : u'attachment; filename=afile.zog' }),
            })

    def test_file_route__GET_with_content_type(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'content' : "POJNDCJSL", 'filename' : "afile", "type" : 'zog', "content-type" : "application/zog" },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : file_route('/', methods=["GET", "POST", "POTATO"], headers=["x-not-a-real-header",]),
                'expected'    : IppResponse(response="POJNDCJSL",
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'*',
                                                                              'Access-Control-Allow-Headers'     : u'X-NOT-A-REAL-HEADER, CONTENT-TYPE',
                                                                              'Content-Disposition'              : u'attachment; filename=afile.zog',
                                                                              'Content-Type'                     : u'application/zog' }),
            })

    def test_file_route__GET_without_methods(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "HEAD",],
                'path'        : '/',
                'return_data' : { 'content' : "POJNDCJSL", 'filename' : "afile", "type" : 'zog' },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : file_route('/'),
                'expected'    : IppResponse(response="POJNDCJSL",
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, HEAD',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'*',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Disposition'              : u'attachment; filename=afile.zog' }),
            })

    def test_file_route__GET_without_headers(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'content' : "POJNDCJSL", 'filename' : "afile", "type" : 'zog' },
                'method'      : "GET",
                'best_type'   : 'application/json',
                'decorator'   : file_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response="POJNDCJSL",
                                                                    status=200,
                                                                    headers={ 'Access-Control-Allow-Methods'     : u'GET, POST, POTATO',
                                                                              'Access-Control-Max-Age'           : u'21600',
                                                                              'Cache-Control'                    : u'no-cache, must-revalidate, no-store',
                                                                              'Access-Control-Allow-Origin'      : u'*',
                                                                              'Access-Control-Allow-Headers'     : u'CONTENT-TYPE',
                                                                              'Content-Disposition'              : u'attachment; filename=afile.zog' }),
            })

    def test_resource_route__GET(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop',] }, indent=4),
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_resource_route__GET_subpath(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "foo",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response='"bar"',
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_resource_route__GET_subpath_with_list(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "baz",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response=json.dumps([ "boop" ], indent=4),
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_resource_route__GET_subpath_with_list_and_subpath(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "baz/0",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response=json.dumps("boop", indent=4),
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_resource_route__GET_subpath_with_unknown_subpath(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "tubular",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })

    def test_resource_route__GET_subpath_with_unknown_subpath(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "tubular",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })

    def test_resource_route__GET_subpath_with_unknown_noninteger_list_index(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "baz/coop",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })

    def test_resource_route__GET_subpath_with_list_index_too_large(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop',] },
                'method'      : "GET",
                'extract_path': "baz/1",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })
        
    def test_resource_route__GET_subpath_with_non_jsonic_data(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop', mock.sentinel.BAD_PARAM ] },
                'method'      : "GET",
                'extract_path': "baz/1",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })

    def test_resource_route__GET_subpath_with_non_jsonic_data_and_subindex(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop', mock.sentinel.BAD_PARAM ] },
                'method'      : "GET",
                'extract_path': "baz/1/tree",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : 404,
            })

    def test_resource_route__GET_subpath_with_empty_object(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop', {} ] },
                'method'      : "GET",
                'extract_path': "baz/1",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response=json.dumps([], indent=4),
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_resource_route__PUT(self):
        self.perform_test_on_decorator({
                'methods'     : ["GET", "POST", "POTATO",],
                'path'        : '/',
                'return_data' : { 'foo' : 'bar', 'baz' : ['boop', {} ] },
                'method'      : "PUT",
                'extract_path': "baz/1",
                'decorator'   : resource_route('/', methods=["GET", "POST", "POTATO"]),
                'expected'    : IppResponse(response=json.dumps({ 'foo' : 'bar', 'baz' : ['boop', {} ] }, indent=4),
                                            status=200,
                                            headers={
                                                'Access-Control-Allow-Headers': u'CONTENT-TYPE, API-KEY',
                                                'Access-Control-Max-Age': u'21600',
                                                'Cache-Control': u'no-cache, must-revalidate, no-store',
                                                'Access-Control-Allow-Origin': u'*',
                                                'Access-Control-Allow-Methods': u'GET, POST, POTATO'},
                                            content_type=u'application/json'),
            })

    def test_on_json(self):
        """This tests the on_json decorator which is used for websocket end-points and so has a slightly different
        structure from that of the other decorators."""
        m = mock.MagicMock(name="webapi")
        (f, UUT, calls) = self.initialise_webapi_with_method_using_decorator(m, on_json('/'), is_socket=True)

        socket_uuid = "05f1c8da-dc36-11e7-af05-7fe527dcf7ab"
        with mock.patch("uuid.uuid4", return_value=socket_uuid):
            m.side_effect = lambda ws,msg : self.assertIn(socket_uuid, UUT.socks)
            ws = mock.MagicMock(name="ws")
            ws.receive.side_effect = [ json.dumps({ "foo" : "bar", "baz" : [ "boop", ] }), Exception ]

            f(ws)

            self.assertListEqual(ws.receive.mock_calls, [ mock.call(), mock.call() ])

            m.assert_called_once_with(ws, { "foo" : "bar", "baz" : [ "boop", ] })

    def test_on_json_with_on_websocket_connect(self):
        """This tests the on_json decorator which is used for websocket end-points and so has a slightly different
        structure from that of the other decorators, it checks the behaviour when an alternative on_websocket_connect
        method is specified in the class."""
        m = mock.MagicMock(name="webapi")
        on_websocket_connect = mock.MagicMock(name="on_websocket_connect")
        (f, UUT, calls) = self.initialise_webapi_with_method_using_decorator(m, on_json('/'), is_socket=True, on_websocket_connect=on_websocket_connect)

        on_websocket_connect.assert_called_once_with(UUT, mock.ANY)
        self.assertEqual(f, on_websocket_connect.return_value)
        f = on_websocket_connect.call_args[0][1]

        socket_uuid = "05f1c8da-dc36-11e7-af05-7fe527dcf7ab"
        with mock.patch("uuid.uuid4", return_value=socket_uuid):
            ws = mock.MagicMock(name="ws")

            f(ws, json.dumps({ "foo" : "bar", "baz" : [ "boop", ] }))

            m.assert_called_once_with(ws, { "foo" : "bar", "baz" : [ "boop", ] })

    def test_on_json_with_grain_event_wrapper(self):
        """This tests the on_json decorator which is used for websocket end-points and so has a slightly different
        structure from that of the other decorators."""
        m = mock.MagicMock(name="webapi", __name__="webapi")
        (f, UUT, calls) = self.initialise_webapi_with_method_using_decorator(grain_event_wrapper(m), on_json('/'), is_socket=True)

        socket_uuid = "05f1c8da-dc36-11e7-af05-7fe527dcf7ab"
        with mock.patch("uuid.uuid4", return_value=socket_uuid):
            m.side_effect = lambda ws,msg : msg
            ws = mock.MagicMock(name="ws")
            ws.receive.side_effect = [ json.dumps({ "grain" : { "event_payload" : { "data" : [ {"post" : { "foo" : "bar", "baz" : [ "boop", ] } } ] } } }), Exception ]

            f(ws)

            self.assertListEqual(ws.receive.mock_calls, [ mock.call(), mock.call() ])

            m.assert_called_once_with(ws, { "foo" : "bar", "baz" : [ "boop", ] })
            print ws.receive.send.mock_calls
