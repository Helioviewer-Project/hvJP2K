
import os
import sys

if sys.hexversion >= 0x03000000:
    import socketserver
else:
    import SocketServer as socketserver

from .jpx_merge import jpx_merge

#import time

class ThreadedUnixStreamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        #start = time.clock()

        jp2s_in = self.rfile.readline().decode('utf-8').strip()
        jpx_out = self.rfile.readline().decode('utf-8').strip()
        links = self.rfile.readline().strip()
        links = True if links else False

        names_in = [name for name in jp2s_in.split(',') if name]
        jpx_merge(names_in, jpx_out, links)

        #print(time.clock() - start)

class ThreadedUnixStreamServer(socketserver.ThreadingMixIn,
                               socketserver.UnixStreamServer):
    pass

def jpx_merge_daemon(address):
    if os.path.exists(address):
        os.unlink(address)
    # Create the server
    server = ThreadedUnixStreamServer(address, ThreadedUnixStreamHandler)
    # The socket needs to be writeable
    os.chmod(address, 0o666)
    # Loop forever servicing requests
    #server.daemon_threads = True
    server.serve_forever()
