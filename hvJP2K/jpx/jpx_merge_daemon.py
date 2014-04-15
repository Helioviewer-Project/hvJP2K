
import re
import os
import threading
import SocketServer
from cStringIO import StringIO

from jpx_merge import jpx_merge


class ThreadedUnixStreamHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        #print(threading.currentThread().getName())

        msg = ''
        while True:
            data = self.request.recv(4096)
            if not data: break
            msg += data

        buf = StringIO(msg)
        jp2s_in = buf.readline().strip()
        jpx_out = buf.readline().strip()
        links = buf.readline().strip()
        links = True if links else False

        jpx_merge(filter(None, re.split(',', jp2s_in)), jpx_out, links)


class ThreadedUnixStreamServer(SocketServer.ThreadingMixIn, SocketServer.UnixStreamServer):
    pass

def jpx_merge_daemon(address):
    if os.path.exists(address):
        os.unlink(address)
    # Create the server
    server = ThreadedUnixStreamServer(address, ThreadedUnixStreamHandler)
    # The socket needs to be writeable
    os.chmod(address, 0666)
    # Loop forever servicing requests
    server.daemon_threads = True
    server.serve_forever()
