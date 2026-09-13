import argparse
import os
import shlex
import socket
import socketserver
import traceback

from .jpx_merge import jpx_merge


class RequestParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


_request_parser = RequestParser(add_help=False)
_request_parser.add_argument('-i', nargs='+', required=True)
_request_parser.add_argument('-o', required=True)
_request_parser.add_argument('-links', action='store_true')


def parse_request(request):
    request_text = os.fsdecode(request)
    if any(character in request_text for character in "'\"\\"):
        request_args = shlex.split(request_text)
    else:
        request_args = request_text.split()
    args = _request_parser.parse_args(request_args)

    names = (os.fsencode(name) for name in args.i if name)
    names_in = [name for name in b','.join(names).split(b',') if name]
    return names_in, os.fsencode(args.o), args.links


class ThreadedUnixStreamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        request = self.rfile.read()
        if not request:
            return
        try:
            names_in, jpx_out, links = parse_request(request)
            jpx_merge(names_in, jpx_out, links)
        except Exception as error:
            traceback.print_exc()
            message = str(error).replace('\n', ' ')
            self.wfile.write(('ERROR: {0}: {1}\n'.format(
                type(error).__name__, message)).encode())
        else:
            self.wfile.write(b'OK\n')


class ThreadedUnixStreamServer(socketserver.ThreadingMixIn,
                               socketserver.UnixStreamServer):
    request_queue_size = socket.SOMAXCONN


def jpx_merge_daemon(address):
    if os.path.exists(address):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(address)
        except ConnectionRefusedError:
            os.unlink(address)
        else:
            raise RuntimeError('merge daemon is already running: ' + address)
        finally:
            probe.close()

    server = ThreadedUnixStreamServer(address, ThreadedUnixStreamHandler)
    try:
        os.chmod(address, 0o666)
        server.serve_forever()
    finally:
        try:
            os.unlink(address)
        except FileNotFoundError:
            pass
        finally:
            server.server_close()
