import os
import shutil
import zipfile

from jinja2.sandbox import SandboxedEnvironment

from inkpy_jinja.backends.external_script import ExternalRenderer


settings = {}


class Error(Exception):
    pass


class FileDoesNotExist(Error):
    """File to file does not exist"""


class IdDoesNotExist(Error):
    """Document id does not exist"""


class Converter(object):
    """
    Fill special prepareted odt file with filled django style template
    tags and convert this file to pdf file.
    Conversion from odt to pdf file it's made with external command
    run in subprocess.call.

    :param source_file: The source odt file path.
    :param output_path: The destination pdf file path.
    :param data: The directory with data to fill template.
    :param lang_code: forces language during docs generation, if None then
        django's *settings.LANGUAGE_CODE* is used.
    """

    def __init__(
        self, source_file, output_path, data, backend=None, lang_code=None
    ):
        if not os.path.exists(source_file):
            raise FileDoesNotExist()
        self.source_file = source_file
        self.output_path = output_path
        output_path_without_ext = self.source_file[:-3]
        if not data.get('id'):
            raise IdDoesNotExist()
        self.data = data
        self.tmp_dir_master = settings.get('tmp_dir', '/tmp/INKPY')
        self.tmp_dir = "{}/{}".format(self.tmp_dir_master, self.data['id'])
        output_odt_path = "{}odt".format(output_path_without_ext)
        self.tmp_odt = '{}/{}'.format(
            self.tmp_dir_master, output_odt_path.split('/')[-1],
        )
        self.set_lang(lang_code)
        backend_args = {
            'output_path': output_path,
            'input_path': self.tmp_odt,
        }
        if not backend:
            self.backend = ExternalRenderer(**backend_args)
        else:
            self.backend = backend(**backend_args)

    def set_lang(self, lang_code):
        if not lang_code:
            lang_code = getattr(settings, 'LANGUAGE_CODE', 'pl').split('-')[0]
        self.lang_code = lang_code

    def convert(self):
        self._convert()

    def _convert(self):
        """
        Flow:
        unzip odt file -> render content.xml -> zip to odt file ->
        convert odt to pdf -> remove temporary data
        """

        self.unzip_odt()
        self.render()
        self.zip_odt()
        self.to_pdf()
        self.remove_tmp()

    def remove_tmp(self):
        """Remove temporary unpaced odt and translated odt file"""
        shutil.rmtree(self.tmp_dir)
        os.remove(self.tmp_odt)

    def unzip_odt(self):
        if not os.path.exists(self.tmp_dir):
            os.makedirs(self.tmp_dir)
        with zipfile.ZipFile(self.source_file) as zf:
            zf.extractall(self.tmp_dir)

    def zip_odt(self):
        self.zip_dir(self.tmp_dir, self.tmp_odt)

    def render(self):
        content_xml = "{}/content.xml".format(self.tmp_dir)
        styles_xml = "{}/styles.xml".format(self.tmp_dir)

        def _render(file_name):
            with open(file_name, 'rb') as reader:
                new_content = self._jinja_renderer(reader.read())
            with open(file_name, 'wb') as writer:
                writer.write(new_content.encode("UTF-8"))
        _render(content_xml)
        _render(styles_xml)

    def _jinja_renderer(self, file_content):
        jinja_env = SandboxedEnvironment()
        template = jinja_env.from_string(file_content.decode('utf-8'))
        rendered = template.render(**self.data)
        return rendered

    def zip_dir(self, dir_path=None, zip_file_path=None):
        """Create a zip archive from a directory.

        Note that this function is designed to put files in the zip archive
        with either no parent directory or just one parent directory, so it
        will trim any leading directories in the filesystem paths and not
        include them inside the zip archive paths. This is generally the case
        when you want to just take a directory and make it into a zip file that
        can be extracted in differentlocations.

        Keyword arguments:

        dir_path -- string path to the directory to archive. This is the only
        required argument. It can be absolute or relative, but only one or zero
        leading directories will be included in the zip archive.

        zip_file_path -- string path to the output zip file. This can be an
        absolute or relative path. If the zip file already exists, it will be
        updated. If not, it will be created. If you want to replace it from
        scratch, delete it prior to calling this function. (default is computed
        as dir_path + ".zip")

        include_dir_inZip -- boolean indicating whether the top level directory
        should be included in the archive or omitted. (default True)

        """

        if not zip_file_path:
            zip_file_path = dir_path + ".zip"
        if not os.path.isdir(dir_path):
            raise OSError(
                "dir_path argument must point to a directory. "
                "'%s' does not." % dir_path
            )
        parentDir, dirToZip = os.path.split(dir_path)

        def trim_path(path):
            # Little nested function to prepare the proper archive path
            archive_path = path.replace(parentDir, "", 1)
            if parentDir:
                archive_path = archive_path.replace(
                    dirToZip + os.path.sep, "", 1,
                )
            return os.path.normcase(archive_path)

        out_file = zipfile.ZipFile(
            zip_file_path, "w", compression=zipfile.ZIP_DEFLATED,
        )
        for (archiveDir_path, dirNames, fileNames) in os.walk(dir_path):
            for fileName in fileNames:
                file_path = os.path.join(archiveDir_path, fileName)
                out_file.write(file_path, trim_path(file_path))
            # Make sure we get empty directories as well
            if not fileNames and not dirNames:
                zip_info = zipfile.ZipInfo(trim_path(archiveDir_path) + "/")
                # Some web sites suggest doing zipInfo.external_attr = 16
                # or zipInfo.external_attr = 48. Here to allow for inserting
                # an empty directory. Still TBD/TODO.
                out_file.writestr(zip_info, "")
        out_file.close()

    def to_pdf(self):
        """ Run external python file to provide convert odt file to pdf"""
        self.backend.render()
