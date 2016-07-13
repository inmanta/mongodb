"""
    Copyright 2016 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: code@inmanta.com
"""

import subprocess
import tempfile
import shutil
import os

from inmanta.resources import Resource, resource, ResourceNotFoundExcpetion
from inmanta.agent.handler import provider, ResourceHandler, HandlerNotAvailableException
import base64


@resource("mongodb::Database", agent="server.host.name", id_attribute="name")
class Database(Resource):
    """
        A mongodb database
    """
    fields = ("name", "purged", "allow_snapshot", "allow_restore", "state_id")


@provider("mongodb::Database", name = "mongodb")
class DatabaseHandler(ResourceHandler):
    """
        A handler to manage database on a mongodb server and snapshot/restore

        (this handler currently does nothing because mongo creates its database lazily)
    """
    def check_resource(self, resource : Database):
        current = resource.clone()
        return current

    def list_changes(self, resource : Database):
        current = self.check_resource(resource)
        return self._diff(current, resource)

    def do_changes(self, resource : Database) -> bool:
        changed = False
        changes = self.list_changes(resource)
        return changed

    def snapshot(self, resource):
        if not os.path.exists("/usr/bin/mongodump"):
            raise Exception("/usr/bin/mongodump does not exist.")

        outdir = tempfile.mkdtemp()
        try:
            dumpdir = os.path.join(outdir, "dump")
            proc = subprocess.Popen(["/usr/bin/mongodump", "-d", resource.name, "-o", dumpdir],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()

            if proc.returncode > 0:
                raise Exception("Failed to dump database: out: %s, err: %s" % (stdout, stderr))

            proc = subprocess.Popen(["/usr/bin/tar", "-czf", "-", resource.name], cwd=dumpdir,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stdout, stderr = proc.communicate()

            if proc.returncode > 0:
                raise Exception("Failed to dump database: out: %s, err: %s" % (stderr))

            return stdout
        finally:
            shutil.rmtree(outdir)

        return None

    def restore(self, resource, content_hash):
        if not os.path.exists("/usr/bin/mongodump"):
            raise Exception("/usr/bin/mongodump does not exist.")

        outdir = tempfile.mkdtemp()
        try:
            dumpdir = os.path.join(outdir, "dump")
            os.mkdir(dumpdir)

            # download snapshot
            result = self.get_file(content_hash)
            if result is None:
                raise Exception("Unable to download snapshot content.")

            data_file = os.path.join(outdir, "data.tar.gz")
            with open(data_file, "wb+") as fd:
                fd.write(result)

            proc = subprocess.Popen(["tar", "xvzf", data_file], cwd=dumpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            if proc.returncode > 0:
                raise Exception("Failed to unzip database snapshot: out: %s, err: %s" % (stdout, stderr))

            os.remove(data_file)

            proc = subprocess.Popen(["/usr/bin/mongorestore", "--drop", dumpdir],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()

            if proc.returncode > 0:
                raise Exception("Failed to restore database: out: %s, err: %s" % (stdout, stderr))
        finally:
            shutil.rmtree(outdir)
