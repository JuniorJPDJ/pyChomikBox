import argparse
import hashlib
import concurrent.futures
import logging
from collections import defaultdict

from ChomikBox.ChomikBox import Chomik, ChomikFolder, ChomikFile

# This code is counting sha1 hashes of every free downloadable file at Chomik without saving it to disk

# TODO: investigate misterious redirections at some files..

workers = 20
chunk_size = 2 ** 12  # 4KiB
max_errors_per_file = 5
skip_hashed = True
out_f = r'C:\Users\Junior\Nextcloud\dev\msdn\chomik.sha1'
#paths = ['/prywatne/MSDN', '/prywatne/MSDN SVF']
paths = ['/']


logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s][%(levelname)s]: %(name)s | %(message)s', datefmt='%H:%M:%S')

p = argparse.ArgumentParser()
p.add_argument('login', help="Chomikuj login/email")
p.add_argument('password', help="Chomikuj password")
args = p.parse_args()


# used for sniffing requests with burp suite
# import requests
# s = requests.session()
# s.proxies = {'http': '127.0.0.1:8080', 'https': '127.0.0.1:8080'}
# s.verify = False
# from requests.packages.urllib3.exceptions import InsecureRequestWarning
# requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
# c = Chomik(args.login, args.password, s)

c = Chomik(args.login, args.password)
c.login()
folders = [c.get_path(path) for path in paths]
files = []

while folders:
    for f in folders:
        if isinstance(f, ChomikFile):
            files.append(f)
        elif isinstance(f, ChomikFolder):
            folders.extend(f.folders_list())
            files.extend(f.files_list(only_downloadable=True))
        folders.remove(f)

if skip_hashed:
    with open(out_f, 'r') as f:
        hashed_fnames = [fname.split(' ', maxsplit=1)[1].rstrip() for fname in f if fname]
        files = [file for file in files if file.path not in hashed_fnames]
        del hashed_fnames


def gen_sha1(file):
    f = file.open()
    sha = hashlib.sha1()
    while True:
        block = f.read(chunk_size)
        if not block:
            break
        sha.update(block)
    return sha.hexdigest()


errors = defaultdict(lambda: 0)

with open(out_f, 'a', 1) as out_f:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(gen_sha1, file): file for file in files}
        for future in concurrent.futures.as_completed(future_to_file):
            file = future_to_file[future]
            try:
                sha = future.result()
            except Exception as exc:
                errors[file] += 1
                print('[EXCEPTION #{n}] {f}: {e}'.format(f=file.path, e=str(exc), n=errors[file]))
                if errors[file] < max_errors_per_file:
                    print('Adding to the end of queue')
                    future_to_file[executor.submit(gen_sha1, file)] = file
            else:
                print(sha, file.path, file=out_f)
                print(sha, file.path)
