import cgi
import time
import requests
from io import IOBase

# Original version: https://github.com/valgur/pyhttpio
# Modified to use requests by JuniorJPDJ


class SeekableHTTPFile(IOBase):
    def __init__(self, url, name=None, repeat_time=15, debug=False, requests_session=None):
        """Allow a file accessible via HTTP to be used like a local file by utilities
         that use `seek()` to read arbitrary parts of the file, such as `ZipFile`.
        Seeking is done via the 'range: bytes=xx-yy' HTTP header.

        Parameters
        ----------
        url : str
            A HTTP or HTTPS URL
        name : str, optional
            The filename of the file.
            Will be filled from the Content-Disposition header if not provided.
        repeat_time : int, optional
            In case of HTTP errors wait `repeat_time` seconds before trying again.
            15 seconds by default.
            Negative value or `None` disables retrying and simply passes on the exception.
        """
        IOBase.__init__(self)
        self.url = url
        self.name = name
        self.repeat_time = repeat_time
        self.debug = debug
        self._pos = 0
        self._seekable = True
        self.sess = requests_session if requests_session is not None else requests.session()
        f = self._urlopen(method='HEAD')
        if self.debug:
            print(f.headers)
        self.content_length = int(f.headers["Content-Length"]) if "Content-Length" in f.headers else -1
        if self.content_length < 0:
            self._seekable = False
        if "Accept-Ranges" not in f.headers or f.headers["Accept-Ranges"] != "bytes":
            ff = self._urlopen((0, 1), method='HEAD')
            if ff.status_code != 206:
                self._seekable = False
            ff.close()
        if name is None:
            if "Content-Disposition" in f.headers:
                value, params = cgi.parse_header(f.headers["Content-Disposition"])
                self.name = params["filename"]
        f.close()

    def seek(self, offset, whence=0):
        if not self.seekable():
            raise OSError
        if whence == 0:
            self._pos = 0
        elif whence == 1:
            pass
        elif whence == 2:
            self._pos = self.content_length
        self._pos += offset
        return self._pos

    def seekable(self, *args, **kwargs):
        return self._seekable

    def readable(self, *args, **kwargs):
        return not self.closed

    def writable(self, *args, **kwargs):
        return False

    def read(self, amt=-1):
        if self._pos >= self.content_length:
            return b""
        if amt < 0:
            end = self.content_length - 1
        else:
            end = min(self._pos + amt - 1, self.content_length - 1)
        byte_range = (self._pos, end)
        self._pos = end + 1
        f = self._urlopen(byte_range)
        content = f.content
        f.close()
        return content

    def readall(self):
        return self.read(-1)

    def tell(self):
        return self._pos

    def __getattribute__(self, item):
        attr = object.__getattribute__(self, item)
        if not object.__getattribute__(self, "debug"):
            return attr

        if hasattr(attr, '__call__'):
            def trace(*args, **kwargs):
                a = ", ".join(map(str, args))
                if kwargs:
                    a += ", ".join(["{}={}".format(k, v) for k, v in kwargs.items()])
                print("Calling: {}({})".format(item, a))
                return attr(*args, **kwargs)

            return trace
        else:
            return attr

    def _urlopen(self, byte_range=None, method='GET'):
        header = {}
        if byte_range:
            header = {"range": "bytes={}-{}".format(*byte_range)}
        while True:
            r = self.sess.request(method, self.url, headers=header, stream=True)
            if r.status_code in (200, 206):
                return r
            else:
                if self.repeat_time is None or self.repeat_time < 0:
                    raise Exception(r.status_code)
                time.sleep(self.repeat_time)
