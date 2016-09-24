from __future__ import unicode_literals

from .httpio_requests import SeekableHTTPFile
from collections import OrderedDict
from datetime import datetime
from hashlib import md5
import xmltodict
import requests
import logging
import sys

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
        return d.iteritems()


class SendActionFailedException(Exception):
    def __init__(self, action, error=None):
        self.action, self.error = action, error
        Exception.__init__(self, '{}: {}'.format(action, error))


class NotLoggedInException(Exception):
    pass


class UnsupportedOperation(Exception):
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
        return '<ChomikBox.ChomikFile: "{p}" {i}({c})>'.format(p=self.path, i='-not downloadable- ' if self.downloadable else ' ', c=self.chomik.name)

    def open(self):
        if self.url is None:
            return
        return SeekableHTTPFile(self.url, repeat_time=None, requests_session=self.chomik.sess)

    @property
    def downloadable(self):
        return self.url is None

    @property
    def path(self):
        return self.parent_folder.path + self.name


class ChomikFolder(object):
    def __init__(self, chomik, name, folder_id, parent_folder, hidden):
        assert isinstance(chomik, Chomik)
        assert isinstance(name, ustr)
        assert isinstance(parent_folder, ChomikFolder) or parent_folder is None
        assert isinstance(hidden, bool)

        self.chomik, self.folder_id, self.name = chomik, int(folder_id), name
        self.parent_folder, self.hidden = parent_folder, hidden

    @classmethod
    def cache(cls, chomik, name, folder_id, parent_folder, hidden):
        assert isinstance(chomik, Chomik)
        folder_id = int(folder_id)
        if folder_id in chomik._folder_cache:
            assert isinstance(name, ustr)
            assert isinstance(parent_folder, ChomikFolder)
            assert isinstance(hidden, bool)
            fol = chomik._folder_cache[folder_id]
            fol.name, fol.parent_folder, fol.hidden = name, parent_folder, hidden
        else:
            fol = cls(chomik, name, folder_id, parent_folder, hidden)
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


class Chomik(ChomikFolder):
    def __init__(self, name, password, requests_session=None):
        assert isinstance(name, ustr)
        assert isinstance(password, ustr)
        assert isinstance(requests_session, requests.Session) or requests_session is None

        self.__password = password
        self.sess = requests.session() if requests_session is None else requests_session
        self.__token, self.chomik_id = '', 0
        self._last_action = datetime.now()
        self._folder_cache = {}
        self.logger = logging.getLogger('ChomikBox.Chomik.{}'.format(name))
        ChomikFolder.__init__(self, self, name, 0, None, False)

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

    def login(self):
        # URL for easy web login:
        # 'http://box.chomikuj.pl/chomik/chomikbox/LoginFromBox?t={token}&returnUrl=/{name}'.format(self.__token, self.name)

        data = OrderedDict([['name', self.name], ['passHash', md5(self.__password.encode('utf-8')).hexdigest()],
                            ['client', {'name': 'chomikbox', 'version': '2.0.8.1'}], ['ver', '4']])
        resp = self._send_action('Auth', data)
        self.chomik_id = int(resp['a:hamsterId'])
        self.__token = resp['a:token']
        self.logger.debug('Logged in with token {}'.format(self.__token))

    def logout(self):
        self._send_action('Logout', {'token': self.__token})
        self.__token = ''

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

        id_ = '{}/{}'.format(self.chomik_id, folder.folder_id)
        a_data = dwn_req_data(OrderedDict([['id', id_], ['agreementInfo', {'AgreementInfo': {'name': 'own'}}]]))
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
            return ChomikFolder.cache(self, data['name'], data['id'], folder, hidden)

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

        data = OrderedDict([['token', self.__token], ['newFolderId', parent_folder.folder_id], ['name', name]])
        data = self._send_action('AddFolder', data)

        return ChomikFolder(self, name, data['a:folderId'], parent_folder, False)

    def rename_folder(self, name, folder):
        assert isinstance(name, ustr)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['name', name]])
        self._send_action('RenameFolder', data)
        folder.name = name

    def move_folder(self, folder, to):
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(to, ChomikFolder)
        assert isinstance(folder, ChomikFolder)

        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['newFolderId', to.folder_id]])
        self._send_action('MoveFolder', data)
        folder.parent_folder = to

    def remove_folder(self, folder, force=False):
        assert isinstance(force, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['force', int(force)]])
        self._send_action('RemoveFolder', data)
        folder.parent_folder = None

    def set_folder_hidden(self, folder, hidden):
        assert isinstance(hidden, bool)
        if isinstance(folder, Chomik):
            raise UnsupportedOperation
        assert isinstance(folder, ChomikFolder)

        data = OrderedDict([['token', self.__token], ['folderId', folder.folder_id], ['hidden', int(hidden)]])
        data = self._send_action('ModifyFolder', data)
        data = data['a:folderDetails']['hidden']
        data = True if data == 'true' else False

        folder.hidden = data
        return hidden == data
