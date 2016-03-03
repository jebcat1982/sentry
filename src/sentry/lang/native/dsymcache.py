import os
import time
import errno
import shutil

from django.conf import settings
from sentry.models import find_dsym_file


ONE_DAY = 60 * 60 * 24
ONE_DAY_AND_A_HALF = int(ONE_DAY * 1.5)


class DSymCache(object):

    def __init__(self):
        pass

    def get_project_path(self, project):
        return os.path.join(settings.DSYM_CACHE_PATH, str(project.id))

    def get_global_path(self):
        return os.path.join(settings.DSYM_CACHE_PATH, 'global')

    def fetch_dsyms(self, project, uuids):
        base = self.get_project_path(project)
        loaded = []
        for image_uuid in uuids:
            dsym = self.fetch_dsym(project, image_uuid)
            if dsym is not None:
                loaded.append(dsym)
        return base, loaded

    def try_bump_timestamp(self, path, old_stat):
        now = int(time.time())
        if old_stat.st_ctime < now - ONE_DAY:
            os.utime(path, (now, now))
        return path

    def fetch_dsym(self, project, image_uuid):
        image_uuid = image_uuid.lower()
        for path in self.get_project_path(project), self.get_global_path():
            base = self.get_project_path(project)
            dsym = os.path.join(base, image_uuid)
            try:
                stat = os.stat(dsym)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
            else:
                return self.try_bump_timestamp(dsym, stat)

        dsf = find_dsym_file(project, image_uuid)
        if dsf is None:
            return None

        if dsf.is_global:
            base = self.get_global_path()
        else:
            base = self.get_project_path(project)
        dsym = os.path.join(base, image_uuid)

        try:
            os.makedirs(base)
        except OSError:
            pass

        with dsf.file.getfile() as sf:
            with open(dsym + '_tmp', 'w') as df:
                shutil.copyfileobj(sf, df)
            os.rename(dsym + '_tmp', dsym)

        return dsym

    def clear_old_entries(self):
        try:
            cache_folders = os.listdir(settings.DSYM_CACHE_PATH)
        except OSError:
            pass

        cutoff = int(time.time()) - ONE_DAY_AND_A_HALF

        for cache_folder in cache_folders:
            cache_folder = os.path.join(settings.DSYM_CACHE_PATH, cache_folder)
            try:
                items = os.listdir(cache_folder)
            except OSError:
                continue
            for cached_file in items:
                cached_file = os.path.join(cache_folder, cached_file)
                try:
                    mtime = os.path.getmtime(cached_file)
                except OSError:
                    continue
                if mtime < cutoff:
                    try:
                        os.remove(cached_file)
                    except OSError:
                        pass


dsymcache = DSymCache()
