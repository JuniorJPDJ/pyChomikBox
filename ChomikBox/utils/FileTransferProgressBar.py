import time
import sys


def sizeof_fmt(num, unit='B'):
    # source: http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    for uprexif in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "{:3.2f} {}{}".format(num, uprexif, unit)
        num /= 1024.0
    return "{:3.2f} Yi{}".format(num, unit)


output = sys.stderr
progress_format = '{n} [{b}] {p:3.1f}% ({d}/{a}) {s}'


class FileTransferProgressBar(object):
    # inspired by clint.textui.progress.Bar
    def __init__(self, filesize, name='', width=32, empty_char=' ', filled_char='#', hide=None, speed_update=0.2,
                 bar_update=0.05, progress_format=progress_format):
        self.name, self.filesize, self.width, self.ec, self.fc = name, filesize, width, empty_char, filled_char
        self.speed_update, self.bar_update, self.progress_format = speed_update, bar_update, progress_format
        if hide is None:
            try:
                self.hide = not output.isatty()
            except AttributeError:
                self.hide = True
        else:
            self.hide = hide
        self.last_progress = 0
        self.last_time = time.time()
        self.last_speed_update = self.last_time
        self.start_time = self.last_time
        self.last_speed_progress = 0
        self.last_speed = 0
        self.max_bar_size = 0

    def show(self, progress):
        if time.time() - self.last_time > self.bar_update:
            self.last_time = time.time()
            self.last_progress = progress
            if self.last_time - self.last_speed_update > self.speed_update:
                self.last_speed = (self.last_speed_progress - progress) / float(self.last_speed_update - self.last_time)
                self.last_speed_update = self.last_time
                self.last_speed_progress = progress
            status = self.width * progress // self.filesize
            percent = float(progress * 100) / self.filesize
            bar = self.progress_format.format(n=self.name, b=self.fc * status + self.ec * (self.width - status),
                                              p=percent, d=sizeof_fmt(progress), a=sizeof_fmt(self.filesize),
                                              s=sizeof_fmt(self.last_speed) + '/s')
            max_bar = self.max_bar_size
            self.max_bar_size = max(len(bar), self.max_bar_size)
            bar = bar + (' ' * (max_bar - len(bar))) + '\r'  # workaround for ghosts
            output.write(bar)
            output.flush()

    def done(self):
        speed = self.filesize / float(time.time() - self.start_time)
        bar = self.progress_format.format(n=self.name, b=self.fc * self.width, p=100, d=sizeof_fmt(self.filesize),
                                          a=sizeof_fmt(self.filesize), s=sizeof_fmt(speed) + '/s')
        max_bar = self.max_bar_size
        self.max_bar_size = max(len(bar), self.max_bar_size)
        bar = bar + (' ' * (max_bar - len(bar))) + '\r'
        output.write(bar)
        output.write('\n')
        output.flush()
