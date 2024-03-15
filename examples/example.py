#!/usr/bin/env python
from __future__ import unicode_literals

import logging
import os.path
import time
import argparse

import requests

from ChomikBox.ChomikBox import Chomik, ChomikUploader, ChomikDownloader
from ChomikBox.utils.FileTransferProgressBar import FileTransferProgressBar

# This program uploads file, then downloads it in another path
# Both are done with beautiful progressbars and pauses at middle
# It was used to test if pyChomikBox works and if files are the same and not corrupt
# It can be used as code example, feel free to copy ;)

p = argparse.ArgumentParser()
p.add_argument('login', help="Chomikuj login/email")
p.add_argument('password', help="Chomikuj password")
p.add_argument('upload_file', help="Path to file to upload")
#p.add_argument('dwn_file', help="Path to file where to download")
args = p.parse_args()

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s][%(levelname)s]: %(name)s | %(message)s', datefmt='%H:%M:%S')
s = requests.session()
# s.proxies = {'http': '127.0.0.1:8080'} # used for sniffing requests with burp suite
c = Chomik(args.login, args.password, requests_session=s)
c.login()

upload_folder = c.get('test')

class ProgressCallback(object):
    def __init__(self):
        self.bar = None
        self.stop = True

    def progress_callback(self, par):
        if isinstance(par, ChomikUploader):
            size = par.upload_size
            done = par.bytes_uploaded
        elif isinstance(par, ChomikDownloader):
            size = par.download_size
            done = par.bytes_downloaded

        if self.bar is None:
            self.bar = FileTransferProgressBar(size, par.name)
        self.bar.show(done)

        if done > size / 2 and self.stop:
            print(done)
            self.stop = False
            par.pause()

    def finish_callback(self, par):
        if isinstance(par, ChomikUploader):
            print(par.bytes_uploaded)
        elif isinstance(par, ChomikDownloader):
            print(par.bytes_downloaded)
        self.bar.done()

name = os.path.basename(args.upload_file)
callback = ProgressCallback()
uploader = upload_folder.upload_file(open(args.upload_file, 'rb'), name, callback.progress_callback)
uploader.start()
time.sleep(1)
if uploader.paused:
    time.sleep(1)
    uploader.resume()
callback.finish_callback(uploader)

#with open(args.dwn_file + '.dwn', 'wb') as f:
#    file = upload_folder.get_file(name)
#    callback = ProgressCallback()
#    downloader = file.download(f, callback.progress_callback)
#    downloader.start()
#    if downloader.paused:
#        downloader.resume()
#    callback.finish_callback(downloader)

c.logout()
