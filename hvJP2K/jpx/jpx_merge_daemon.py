
import re
import os
import SocketServer

from jpx_merge import jpx_merge

#import time

class ThreadedUnixStreamHandler(SocketServer.StreamRequestHandler):
    def handle(self):
        #start = time.clock()

        jp2s_in = self.rfile.readline().strip()
        jpx_out = self.rfile.readline().strip()
        links = self.rfile.readline().strip()
        links = True if links else False

        jpx_merge(filter(None, re.split(',', jp2s_in)), jpx_out, links)
        #print(time.clock() - start)

class ThreadedUnixStreamServer(SocketServer.ThreadingMixIn,
                               SocketServer.UnixStreamServer):
    pass

def jpx_merge_daemon(address):
    if os.path.exists(address):
        os.unlink(address)
    # Create the server
    server = ThreadedUnixStreamServer(address, ThreadedUnixStreamHandler)
    # The socket needs to be writeable
    os.chmod(address, 0666)
    # Loop forever servicing requests
    #server.daemon_threads = True
    server.serve_forever()
