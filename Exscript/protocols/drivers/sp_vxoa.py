#
# Copyright (C) 2010-2017 Samuel Abels
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
A driver for devices running VXOA (by Silver Peak).
"""
import re
from Exscript.protocols.drivers.driver import Driver

_user_re = [re.compile(r'[\r\n]login ?:as :')]
_password_re = [re.compile(r'[\r\n][Pp]assword: ?$')]
_prompt_re = [re.compile(r'[\r\n].*?[>#] ?$')]
_error_re = [re.compile(r'^(unknown|invalid|error|syntax error)', re.I)]
_banner_re = re.compile(r'Silver[\r\n\s]Peak[\r\n\s]Systems[\r\n\s]Inc\.')
_auth_banner_re = re.compile(r'Last login:\s')


class SilverPeakVXOADriver(Driver):

    def __init__(self):
        Driver.__init__(self, 'sp_vxoa')
        self.user_re = _user_re
        self.password_re = _password_re
        self.prompt_re = _prompt_re
        self.error_re = _error_re

    def check_head_for_os(self, string):
        if _banner_re.search(string):
            return 90
        return 0

    def check_response_for_os(self, string):
        if _auth_banner_re.search(string):
            return 20
        return 0

    def init_terminal(self, conn):
        conn.execute('terminal length 65536')

    def auto_authorize(self, conn, account, flush, bailout):
        conn.send('enable\r')
        conn.app_authorize(account, flush, bailout)
