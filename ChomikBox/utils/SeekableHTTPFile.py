from io import IOBase
import cgi

import requests


class SeekableHTTPFile(IOBase):
    # a bit based on https://github.com/valgur/pyhttpio
    def __init__(self, url, name=None, requests_session=None):
        IOBase.__init__(self)
        self.url = url
        self.sess = requests_session if requests_session is not None else requests.session()
        self._seekable = False
        f = self.sess.head(url, headers={'Range': 'bytes=0-'})
        if f.status_code == 206 and 'Content-Range' in f.headers:
            self._seekable = True
        self.len = int(f.headers["Content-Length"])
        if name is None:
            if "Content-Disposition" in f.headers:
                value, params = cgi.parse_header(f.headers["Content-Disposition"])
                self.name = params["filename"]
        else:
            self.name = name
        f.close()
        self._pos = 0
        self._r = None

    def seekable(self):
        return self._seekable

    def __len__(self):
        return self.len

    def tell(self):
        return self._pos

    def readable(self):
        return not self.closed

    def writable(self):
        return False

    def _reopen_stream(self):
        if self._r is not None:
            self._r.close()
        if self._seekable:
            self._r = self.sess.get(self.url, headers={'Range': 'bytes={}-'.format(self._pos)}, stream=True)
        else:
            self._pos = 0
            self._r = self.sess.get(self.url, stream=True)

    def seek(self, offset, whence=0):
        if not self.seekable():
            raise OSError
        if whence == 0:
            self._pos = 0
        elif whence == 1:
            pass
        elif whence == 2:
            self._pos = self.len
        self._pos += offset
        if self._r is not None:
            self._r.close()
        elif hasattr(self._r, 'raw'):
            if hasattr(self._r.raw, 'closed'):
                self._r.close()
        return self._pos

    def read(self, amount=-1):
        if self._r is None or self._r.raw.closed:
            self._reopen_stream()
        if amount < 0:
            content = self._r.raw.read()
        else:
            content = self._r.raw.read(amount)
        self._pos += len(content)
        return content
