from __future__ import unicode_literals

import logging
import sys
from collections import OrderedDict
from contextlib import closing
from datetime import datetime
from hashlib import md5

import re
import requests
import xmltodict
import os.path
from requests_toolbelt.multipart.encoder import MultipartEncoderMonitor

from .PartFile import PartFile, total_len
from .utils.SeekableHTTPFile import SeekableHTTPFile

CHOMIKBOX_VERSION = '2.0.8.2'

# TODO: speed limits for downloader and uploader

if sys.version_info >= (3, 0):
    # noinspection PyUnresolvedReferences
    ustr = str

    def str_casefold(s):
        return s.casefold()

    def dict_iteritems(d):
        return d.items()
else:
    # noinspection PyUnresolvedReferences
    ustr = unicode

    def str_casefold(s):
        return s.lower()

    def dict_iteritems(d):
        # noinspection PyCompatibility
        return d.iteritems()


class SendActionFailedException(Exception):
    def __init__(self, action, error=None):
        self.action, self.error = action, error
        Exception.__init__(self, '{}: {}'.format(action, error))


class NotLoggedInException(Exception):
    pass


class UnsupportedOperation(Exception):
    pass


class UploadException(Exception):
    pass


class WTFException(Exception):
    pass


class ChomikSOAP(object):
    @staticmethod
    def pack(name, dict_data, *args, **kwargs):
        if '@xmlns' not in dict_data:
            dict_data['@xmlns'] = 'http://chomikuj.pl/'
        data = {
            's:Envelope': {'s:Body': {name: dict_data}, '@s:encodingStyle': 'http://schemas.xmlsoap.org/soap/encoding/',
                           '@xmlns:s': 'http://schemas.xmlsoap.org/soap/envelope/'}}
        return xmltodict.unparse(data, *args, **kwargs)

    @staticmethod
    def unpack(xml_data, *args, **kwargs):
        data = xmltodict.parse(xml_data, *args, **kwargs)
        return data['s:Envelope']['s:Body']


class ChomikFile(object):
    def __init__(self, chomik, name, file_id, parent_folder, url=None):
        assert isinstance(chomik, Chomik)
        assert isinstance(name, ustr)
        assert isinstance(parent_folder, ChomikFolder)
        assert isinstance(url, ustr) or url is None

        self.chomik, self.name, self.file_id = chomik, name, int(file_id)
        self.parent_folder, self.url = parent_folder, url

    def __repr__(self):
        return '<ChomikBox.ChomikFile: "{p}"{i}({c})>'.format(p=self.path, i=' ' if self.downloadable else '-not downloadable- ', c=self.chomik.name)

    def open(self):
        if self.downloadable:
            return SeekableHTTPFile(self.url, self.name, self.chomik.sess)

    @property
    def downloadable(self):
        return self.url is not None

    @property
    def path(self):
        return self.parent_folder.path + self.name

    def rename(self, name, description):
        return self.chomik.rename_file(name, description, self)

    def move(self, toFolder):
        return self.chomik.move_file(self, toFolder)

    def remove(self):
        return self.chomik.remove_file(self)

    def download(self, file_like, progress_callback=None):
        return ChomikDownloader(self.chomik, self, file_like, progress_callback)


class ChomikFolder(object):
    def __init__(self, chomik, name, folder_id, parent_folder, hidden, adult, gallery_view):
        assert isinstance(chomik, Chomik)
        assert isinstance(name, ustr)
        assert isinstance(parent_folder, ChomikFolder) or parent_folder is None
        assert isinstance(hidden, bool)
        assert isinstance(adult, bool)
        assert isinstance(gallery_view, bool)

        self.chomik, self.folder_id, self.name = chomik, int(folder_id), name
        self.parent_folder, self.hidden, self.adult, self.gallery_view = parent_folder, hidden, adult, gallery_view

    @classmethod
    def cache(cls, chomik, name, folder_id, parent_folder, hidden, adult, gallery_view):
        assert isinstance(chomik, Chomik)
        folder_id = int(folder_id)
        if folder_id in chomik._folder_cache:
            assert isinstance(name, ustr)
            assert isinstance(parent_folder, ChomikFolder)
            assert isinstance(hidden, bool)
            assert isinstance(adult, bool)
            assert isinstance(gallery_view, bool)
            fol = chomik._folder_cache[folder_id]
            fol.name, fol.parent_folder, fol.hidden, fol.adult, fol.gallery_view = name, parent_folder, hidden, adult, gallery_view
        else:
            fol = cls(chomik, name, folder_id, parent_folder, hidden, adult, gallery_view)
            chomik._folder_cache[folder_id] = fol
        return fol

    def __repr__(self):
        return '<ChomikBox.ChomikFolder: "{p}" ({c})>'.format(p=self.path, c=self.chomik.name)

    def __iter__(self):
        return iter(self.list())

    def files_list(self, only_downloadable=False):
        return self.chomik.files_list(only_downloadable, self)

    def folders_list(self):
        return self.chomik.folders_list(self)

    def list(self, only_downloadable=False):
        return self.folders_list() + self.files_list(only_downloadable)

    def get_folder(self, name, case_sensitive=True):
        assert isinstance(name, ustr)
        if case_sensitive:
            for f in self.folders_list():
                if f.name == name:
                    return f
        else:
            name = str_casefold(name)
            for f in self.folders_list():
                if str_casefold(f.name) == name:
                    return f

    def get_file(self, name, case_sensitive=True):
        assert isinstance(name, ustr)
        if case_sensitive:
            for f in self.files_list():
                if f.name == name:
                    return f
        else:
            name = str_casefold(name)
            for f in self.files_list():
                if str_casefold(f.name) == name:
                    return f

    def get(self, name, case_sensitive=True):
        assert isinstance(name, ustr)
        found = self.get_folder(name, case_sensitive)
        if found is None:
            found = self.get_file(name, case_sensitive)
        return found

    @property
    def path(self):
        return self.parent_folder.path + self.name + '/'

    def new_folder(self, name):
        return self.chomik.new_folder(name, self)

    def rename(self, name):
        self.chomik.rename_folder(name, self)

    def move(self, to):
        self.chomik.move_folder(self, to)

    def remove(self, force=False):
        self.chomik.remove_folder(self, force)

    def set_hidden(self, hidden):
        return self.chomik.set_folder_hidden(self, hidden)

    def set_adult(self, adult):
        return self.chomik.set_folder_adult(self, adult)

    def set_gallery_view(self, gallery_view):
        return self.chomik.set_folder_gallery_view(self, gallery_view)

    def upload_file(self, file_like_obj, name=None, progress_callback=None):
        return self.chomik.upload_file(file_like_obj, name, progress_callback, self)


class Chomik(ChomikFolder):
    def __init__(self, name, password, requests_session=None):
        assert isinstance(name, ustr)
        assert isinstance(password, ustr)
        assert isinstance(requests_session, requests.Session) or requests_session is None

        self.__password = password
        self.sess = requests.session() if requests_session is None else requests_session
        self.__token, self.chomik_id, self.chomik_id2 = '', 0, 0
        self._last_action = datetime.now()
        self._folder_cache = {}
        self.logger = logging.getLogger('ChomikBox.Chomik.{}'.format(name))
        # TODO: init adult & gallery_view properly
        ChomikFolder.__init__(self, self, name, 0, None, False, False, False)

    def __repr__(self):
        return '<ChomikBox.Chomik: {n}>'.format(n=self.name)

    def _send_action(self, action, data):
        self.logger.debug('Sending action: "{}"'.format(action))
        if action != 'Auth':
            if not self.__token:
                raise NotLoggedInException
            if (datetime.now() - self._last_action).total_seconds() > 300 and action != 'Logout':
                self.login()

        headers = {'SOAPAction': 'http://chomikuj.pl/IChomikBoxService/{}'.format(action), 'User-Agent': 'Mozilla/5.0',
                   'Content-Type': 'text/xml;charset=utf-8', 'Accept-Language': 'en-US,*'}
        data = ChomikSOAP.pack(action, data)
        resp = self.sess.post('http://box.chomikuj.pl/services/ChomikBoxService.svc', data, headers=headers)
        resp = ChomikSOAP.unpack(resp.text)['{}Response'.format(action)]['{}Result'.format(action)]
        if 'a:hamsterName' in resp and isinstance(resp['a:hamsterName'], ustr):
            self.name = resp['a:hamsterName']
        if 'a:status' in resp and resp['a:status'] != 'Ok':
            if isinstance(resp['a:errorMessage'], ustr):
                raise SendActionFailedException(action, resp['a:errorMessage'])
            else:
                raise SendActionFailedException(action)
        elif 'status' in resp and resp['status']['#text'] != 'Ok':
            if '#text' in resp['errorMessage']:
                raise SendActionFailedException(action, resp['errorMessage']['#text'])
            else:
                raise SendActionFailedException(action)
        self._last_action = datetime.now()
        self.logger.debug('Action sent: "{}"'.format(action))
        return resp

    def _send_web_action(self, action, data):
        self.logger.debug('Sending web action: "{}"'.format(action))
        headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded', 'Accept-Language': 'en-US,*'}
        resp = self.sess_web.post('http://chomikuj.pl/action/{}'.format(action), data=data, headers=headers)
        try:
            return resp.json()
        except ValueError:
            return False

    def login(self):
        data = OrderedDict([['name', self.name], ['passHash', md5(self.__password.encode('utf-8')).hexdigest()],
                            ['client', {'name': 'chomikbox', 'version': CHOMIKBOX_VERSION}], ['ver', '4']])
        resp = self._send_action('Auth', data)
        self.chomik_id = int(resp['a:hamsterId'])
        self.__token = resp['a:token']
        self.logger.debug('Logged in with token {}'.format(self.__token))

        # Web login
        self.sess_web = requests.session()
        self.sess_web.get('http://box.chomikuj.pl/chomik/chomikbox/LoginFromBox', params={'t':self.__token, 'returnUrl':self.name})

    def logout(self):
        self._send_action('Logout', {'token': self.__token})
        self.__token = ''
        self.logger.debug('Logged out')

    @property
    def path(self):
        return '/'

    def files_list(self, only_downloadable=False, folder=None):
        if folder is None:
            folder = self
        assert isinstance(folder, ChomikFolder)

        free_files = {}

        def file(data):
            url = data['url'] if isinstance(data['url'], ustr) else None
            f = ChomikFile(self, data['name'], data['id'], folder, url)
            if url is None:
                for a in data['agreementInfo']['AgreementInfo']:
                    if 'name' in a and 'cost' in a and a['cost'] == '0':
                        if a['name'] not in free_files:
                            free_files[a['name']] = []
                        free_files[a['name']].append(f)
                        break
            return f

        def files_gen(data):
            data = data['a:list']['DownloadFolder']['files']
            if data is not None:
                data = data['FileEntry']
                if isinstance(data, list):
                    for f in data:
                        yield file(f)
                else:
                    yield file(data)

        def dwn_req_data(data):
            return OrderedDict([['token', self.__token], ['sequence', {'stamp': 0, 'part': 0, 'count': 1}], ['disposition', 'download'], ['list', {'DownloadReqEntry': data}]])

        a_data = dwn_req_data(OrderedDict([['id', '/'+self.name+folder.path], ['agreementInfo', {'AgreementInfo': {'name': 'own'}}]]))
        self.logger.debug('Loading files from folder {id}'.format(id=folder.folder_id))
        resp = self._send_action('Download', a_data)

        files = list(files_gen(resp))

        if free_files:
            a_data = []
            for name, fs in dict_iteritems(free_files):
                for ff in fs:
                    a_data.append(OrderedDict([['id', ff.file_id], ['agreementInfo', {'AgreementInfo': {'name': name}}]]))
                    files.remove(ff)
            self.logger.debug('Asking server for additional free files from folder {id}'.format(id=folder.folder_id))
            files.extend(files_gen(self._send_action('Download', dwn_req_data(a_data))))

        if only_downloadable:
            files = list(filter(lambda x: not x.downloadable, files))

        return files

    def folders_list(self, folder=None):
        if folder is None:
            folder = self
        assert isinstance(folder, ChomikFolder)

        def folder_(data):
            hidden = True if data['hidden'] == 'true' else False
            adult = True if data['adult'] == 'true' else False
            gallery_view = True if data['view']['gallery'] == 'true' else False
            return ChomikFolder.cache(self, data['name'], data['id'], folder, hidden, adult, gallery_view)

        def folders_gen(data):
            if 'FolderInfo' in data:
                data = data['FolderInfo']
                if isinstance(data, list):
                    for f in data:
                        yield folder_(f)
                else:
                    yield folder_(data)

        a_data = OrderedDict([['token', self.__token], ['hamsterId', self.chomik_id], ['folderId', folder.folder_id], ['depth', 2]])
        self.logger.debug('Loading folders from folder {id}'.format(id=folder.folder_id))
        resp = self._send_action('Folders', a_data)
        resp = resp['a:folder']['folders']

        return list(folders_gen(resp))

    def get_path(self, path, case_sensitive=True):
        assert isinstance(path, ustr)
        path = list(filter(None, path.split('/')))
        file = self
        for name in path:
            if name == '..':
                file = file.parent_folder
            elif name == '.':
                pass
            else:
                file = file.get(name, case_sensitive)
            if file is None:
                return
        return file

    def new_folder(self, name, parent_folder=None):
        assert isinstance(name, ustr)
        if parent_folder is None:
            parent_folder = self
        assert isinstance(parent_folder, ChomikFolder)

        self.logger.debug('Creating new folder "{n}" in {f}'.format(n=name, f=parent_folder.folder_id))
        data = OrderedDict([['token', self.__token], ['newFolderId', parent_folder.folder_id], ['name', name]])
        data = self._send_action('AddFolder', data)

        return ChomikFolder(self, name, data['a:folderId'], parent_folder, False, False, False)

    def rename_folder(self, name, folder):
        assert isinstance(name, ustr)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Renaming folder {f} to {n}'.format(f=folder.folder_id, n=name))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['name', name]])
        self._send_action('RenameFolder', data)
        folder.name = name

    def move_folder(self, folder, to):
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(to, ChomikFolder)
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Moving folder {f} to {tf}'.format(f=folder.folder_id, tf=to.folder_id))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['newFolderId', to.folder_id]])
        self._send_action('MoveFolder', data)
        folder.parent_folder = to

    def remove_folder(self, folder, force=False):
        assert isinstance(force, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Removing folder {f}'.format(f=folder.folder_id))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['force', int(force)]])
        self._send_action('RemoveFolder', data)
        folder.parent_folder = None
        del(self._folder_cache[folder.folder_id])

    def set_folder_hidden(self, folder, hidden):
        assert isinstance(hidden, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Setting folder {f} hidden status to {h}'.format(f=folder.folder_id, h=hidden))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['hidden', int(hidden)]])
        data = self._send_action('ModifyFolder', data)
        data = data['a:folderDetails']['hidden']
        data = True if data == 'true' else False

        folder.hidden = data
        if hidden == data:
            folder.hidden = hidden
            return True
        else:
            return False

    def set_folder_gallery_view(self, folder, gallery_view):
        assert isinstance(gallery_view, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Setting folder {f} gallery_view status to {h}'.format(f=folder.folder_id, h=gallery_view))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['view', OrderedDict([('gallery', int(gallery_view))])]])
        data = self._send_action('ModifyFolder', data)
        data = data['a:folderDetails']['view']['gallery']
        data = True if data == 'true' else False

        folder.gallery_view = data
        if gallery_view == data:
            folder.gallery_view = gallery_view
            return True
        else:
            return False

    # TODO: set (cached?) child folders adult param (chomikuj do this)
    def set_folder_adult(self, folder, adult):
        assert isinstance(adult, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Setting folder {f} adult status to {h}'.format(f=folder.folder_id, h=adult))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['adult', int(adult)]])
        data = self._send_action('ModifyFolder', data)
        data = data['a:folderDetails']['adult']
        data = True if data == 'true' else False

        folder.adult = data
        if adult == data:
            folder.adult = adult
            return True
        else:
            return False

    def rename_file(self, name, description, file):
        assert isinstance(name, ustr)
        assert isinstance(description, ustr)
        assert isinstance(file, ChomikFile)

        if name == '':
            return False

        # Cut extension
        name = os.path.splitext(name)[0]

        self.logger.debug('Renaming file {f} to {n}'.format(f=file.file_id, n=name))
        data = {
            'FileId':      file.file_id,
            'Name':        name,
            'Description': description
        }
        resp = self._send_web_action('FileDetails/EditNameAndDescAction', data)
        if resp and resp['IsSuccess']:
            file.name = name + os.path.splitext(file.name)[1]
            return True
        return False

    def move_file(self, file, toFolder):
        assert isinstance(file, ChomikFile)
        assert isinstance(toFolder, ChomikFolder)

        self.logger.debug('Moving file {f} to {tf}'.format(f=file.file_id, tf=toFolder.folder_id))
        data = {
            'ChomikName': self.name,
            'FolderId': file.parent_folder.folder_id,
            'FileId':   file.file_id,
            'FolderTo': toFolder.folder_id
        }
        resp = self._send_web_action('FileDetails/MoveFileAction', data)
        if resp and resp['IsSuccess']:
            file.parent_folder = toFolder
            return True
        return False

    def remove_file(self, file):
        assert isinstance(file, ChomikFile)

        self.logger.debug('Removing file {f}'.format(f=file.file_id))
        data = {
            'ChomikName': self.name,
            'FolderId': file.parent_folder.folder_id,
            'FileId':   file.file_id,
            'FolderTo': 0
        }
        resp = self._send_web_action('FileDetails/DeleteFileAction', data)
        if resp and resp['IsSuccess']:
            del(file)
            return True
        return False


    def upload_file(self, file_like_obj, name=None, progress_callback=None, folder=None):
        if name is None:
            name = file_like_obj.name
        if folder is None:
            folder = self
        if progress_callback is None:
            progress_callback = lambda monitor: None
        assert isinstance(name, ustr)
        assert isinstance(folder, ChomikFolder)

        self.logger.debug('Getting file upload data for file "{n}" in folder {f}'.format(n=name, f=folder.folder_id))
        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['fileName', name]])
        data = self._send_action('UploadToken', data)

        key, stamp, server = data['a:key'], data['a:stamp'], data['a:server']

        return ChomikUploader(self, folder, file_like_obj, name, server, key, stamp, progress_callback)


class ChomikUploader(object):
    class UploadPaused(Exception):
        pass

    def __init__(self, chomik, folder, file, name, server, key, stamp, progress_callback=None):
        assert hasattr(file, 'read') and hasattr(file, 'tell') and hasattr(file, 'seek')
        assert isinstance(folder, ChomikFolder)
        assert callable(progress_callback)
        assert isinstance(chomik, Chomik)
        assert isinstance(name, ustr)
        assert isinstance(server, ustr)
        assert isinstance(key, ustr)
        assert isinstance(stamp, ustr)

        self.chomik, self.folder, self.file, self.name = chomik, folder, file, name
        self.server, self.key, self.stamp = server, key, stamp
        self.paused, self.finished, self.started = False, False, False
        self.upload_size, self.bytes_uploaded = total_len(file), 0
        self.__start_pos, self.__part_size = 0, self.upload_size
        self.progress_callback = progress_callback

    def __callback(self, monitor):
        self.bytes_uploaded = self.__start_pos + (monitor.bytes_read - (monitor.len - self.__part_size))
        if self.progress_callback is not None:
            self.progress_callback(self)
        if self.paused:
            raise self.UploadPaused

    def pause(self):
        self.paused = True

    def start(self, attempts=0):
        # attempts = -1 for infinite
        assert isinstance(attempts, int)

        if self.finished:
            raise UploadException('Tried to start finished upload')
        if self.started:
            raise UploadException('Tried to start already started upload')
        self.started = True

        data = OrderedDict([['chomik_id', ustr(self.chomik.chomik_id)], ['folder_id', ustr(self.folder.folder_id)],
                            ['key', self.key], ['time', self.stamp], ['client', 'ChomikBox-'+CHOMIKBOX_VERSION], ['locale', 'PL'],
                            ['file', (self.name, self.file)]])
        monitor = MultipartEncoderMonitor.from_fields(fields=data, callback=self.__callback)
        headers = {'Content-Type': monitor.content_type, 'User-Agent': 'Mozilla/5.0'}

        try:
            self.chomik.logger.debug('Started uploading file "{n}" to folder {f}'.format(n=self.name, f=self.folder.folder_id))
            resp = self.chomik.sess.post('http://{server}/file/'.format(server=self.server), data=monitor, headers=headers)
        except Exception as e:
            if isinstance(e, self.UploadPaused):
                self.chomik.logger.debug('Upload of file "{n}" paused'.format(n=self.name))
                return 'paused'
            else:
                self.chomik.logger.debug('Error {e} occurred during upload of file "{n}"'.format(e=e, n=self.name))
                attempt = 1
                while attempts >= attempt or attempts == -1:
                    try:
                        self.chomik.logger.debug('Resuming failed upload of file "{n}"'.format(n=self.name))
                        return self.resume()
                    except Exception as ex:
                        e = ex
                        self.chomik.logger.debug('Error {e} occurred during upload of file "{n}"'.format(e=ex, n=self.name))
                        attempt += 1
                else:
                    raise e
        else:
            self.chomik.logger.debug('Upload of file "{n}" finished'.format(n=self.name))
            resp = xmltodict.parse(resp.content)['resp']
            if resp['@res'] != '1':
                if '@errorMessage' in resp:
                    raise UploadException(resp['@res'], resp['@errorMessage'])
                else:
                    raise UploadException(resp['@res'])
            if '@fileid' not in resp:
                raise UploadException

            self.finished = True
            return resp['@fileid']

    def resume(self):
        if self.finished:
            raise UploadException('Tried to resume finished upload')
        self.paused = False

        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = self.chomik.sess.get('http://{server}/resume/check/?key={key}'.format(server=self.server, key=self.key), headers=headers)
        resp = xmltodict.parse(resp.content)['resp']

        resume_from = int(resp['@file_size'])
        part = PartFile(self.file, resume_from)
        self.__start_pos = resume_from
        self.__part_size = part.len

        data = OrderedDict([['chomik_id', ustr(self.chomik.chomik_id)], ['folder_id', ustr(self.folder.folder_id)],
                            ['key', self.key], ['time', self.stamp], ['resume_from', ustr(resume_from)],
                            ['client', 'ChomikBox-'+CHOMIKBOX_VERSION], ['locale', 'PL'], ['file', (self.name, part)]])
        monitor = MultipartEncoderMonitor.from_fields(fields=data, callback=self.__callback)
        headers = {'Content-Type': monitor.content_type, 'User-Agent': 'Mozilla/5.0'}

        self.chomik.logger.debug('Resumed uploading file "{n}" to folder {f} from {b} bytes'.format(n=self.name, f=self.folder.folder_id, b=resume_from))
        try:
            resp = self.chomik.sess.post('http://{server}/file/'.format(server=self.server), data=monitor, headers=headers)
        except self.UploadPaused:
            self.chomik.logger.debug('Upload of file "{n}" paused'.format(n=self.name))
            return 'paused'
        else:
            self.chomik.logger.debug('Upload of file "{n}" finished'.format(n=self.name))

            resp = xmltodict.parse(resp.content)['resp']
            if resp['@res'] != '1':
                if '@errorMessage' in resp:
                    raise UploadException(resp['@res'], resp['@errorMessage'])
                else:
                    raise UploadException(resp['@res'])
            if '@fileid' not in resp:
                raise UploadException

            self.finished = True
            return resp['@fileid']


class ChomikDownloader(object):
    def __init__(self, chomik, chomik_file, save_file, progress_callback=None, chunk_size=8192):
        assert isinstance(chomik, Chomik)
        assert isinstance(chomik_file, ChomikFile)
        assert hasattr(save_file, 'write')
        assert isinstance(chunk_size, int)
        assert chomik_file.downloadable

        self.chomik, self.chomik_file, self.save_file, self.chunk_size = chomik, chomik_file, save_file, chunk_size
        self.paused, self.finished, self.started, self.bytes_downloaded = False, False, False, 0
        self.download_size = int(self.chomik.sess.head(chomik_file.url).headers["Content-Length"])
        self.progress_callback = progress_callback

    @property
    def name(self):
        return self.chomik_file.name

    def pause(self):
        self.paused = True

    def __dwn(self, headers):
        with closing(self.chomik.sess.get(self.chomik_file.url, stream=True, headers=headers)) as resp:
            if resp.status_code in (200, 206):
                for data in resp.iter_content(self.chunk_size):
                    self.save_file.write(data)
                    self.bytes_downloaded += len(data)
                    if self.progress_callback is not None:
                        self.progress_callback(self)
                    if self.paused:
                        return 'paused'
                self.finished = True
                return True
            else:
                return False

    def start(self):
        if self.finished:
            raise UploadException('Tried to start finished download')
        if self.started:
            raise UploadException('Tried to start already started download')
        self.started = True

        headers = {'User-Agent': 'Mozilla/5.0'}
        return self.__dwn(headers)

    def resume(self):
        if self.finished:
            raise UploadException('Tried to resume finished download')
        self.paused = False

        headers = {'User-Agent': 'Mozilla/5.0', 'Range': 'bytes={}-'.format(self.bytes_downloaded)}
        return self.__dwn(headers)
