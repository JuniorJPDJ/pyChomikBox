import io
import os


def total_len(o):
    # Stolen from requests_toolbelt and modified
    if hasattr(o, '__len__'):
        return len(o)

    if hasattr(o, 'len'):
        return o.len

    if hasattr(o, 'fileno'):
        try:
            fileno = o.fileno()
        except io.UnsupportedOperation:
            pass
        else:
            return os.fstat(fileno).st_size

    if hasattr(o, 'getvalue'):
        # e.g. BytesIO, cStringIO.StringIO
        return len(o.getvalue())

    if o.seekable():
        current_pos = o.tell()
        length = o.seek(0, 2)
        o.seek(current_pos, 0)
        return length


class PartFile(io.IOBase):
    def __init__(self, file, start):
        assert hasattr(file, 'read') and hasattr(file, 'tell') and hasattr(file, 'seek')
        assert isinstance(start, int)

        self.file, self.start = file, start
        self.total_len = total_len(file)
        self.len = self.total_len - start

        io.IOBase.__init__(self)

        if self.seekable():
            self.seek(0)

    def seek(self, offset, whence=0):
        if whence == 0:
            tell = self.file.seek(offset + self.start, 0)
        else:
            tell = self.file.seek(offset, whence)
        return tell - self.start

    def tell(self):
        return self.file.tell() - self.start

    def __getattr__(self, item):
        return getattr(self.file, item)
