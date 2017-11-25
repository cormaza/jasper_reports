# -*- encoding: utf-8 -*-

import os
import glob
import time
import socket
import subprocess
from xmlrpc import client
import logging
from odoo.exceptions import except_orm
from odoo.tools.translate import _
from odoo import models, fields, _

class JasperServer:
    def __init__(self, port=8090):
        self.port = port
        self.pidfile = None
        self.javapath = None
        url = 'http://localhost:%d' % port
        self.proxy = client.ServerProxy(url, allow_none=True)
        self.logger = logging.getLogger(__name__)

    def error(self, message):
        if self.logger:
            self.logger.error("%s" % message)

    def path(self):
        return os.path.abspath(os.path.dirname(__file__))

    def setPidFile(self, pidfile):
        self.pidfile = pidfile

    def set_java_path(self, javapath):
        self.javapath = javapath

    def start(self):
        java_path = os.path.abspath(os.path.join(os.path.dirname(__file__) ,   '../java'))
        if java_path == False:
            raise except_orm(_('Java Path Not Found !'),_('Please add java path into the jasper configuration page under the company form view'))
        else :
            libraries = str(java_path) + '/lib'
            if os.path.exists(str(libraries)):
                java_path = java_path
            else:
                raise except_orm(_('libraries Not Found !'),_('There is No libraries found in Java'))
        env = {}
        env.update(os.environ)
        if os.name == 'nt':
            a = ';'
        else:
            a = ':'
        libs = os.path.join(java_path, 'lib', '*.jar')
        env['CLASSPATH'] = os.path.join(java_path + a) + a.join(glob.glob(libs)) + a + os.path.join(self.path(),'..','custom_reports')

        cwd = os.path.join(java_path)
        # Set headless = True because otherwise, java may use
        # existing X session and if session is closed JasperServer
        # would start throwing exceptions. So we better avoid
        # using the session at all.
        command = ['java', 
                   '-Djava.awt.headless=true', 
                   '-XX:MaxHeapSize=512m', 
                   '-XX:InitialHeapSize=512m', 
                   '-XX:CompressedClassSpaceSize=64m', 
                   '-XX:MaxMetaspaceSize=128m', 
                   '-XX:+UseConcMarkSweepGC',
                   'com.nantic.jasperreports.JasperServer', str(self.port)]
        process = subprocess.Popen(command, env=env, cwd=cwd)
        if self.pidfile:
            f = open(self.pidfile, 'w')
            try:
                f.write(str(process.pid))
            finally:
                f.close()

    def execute(self, *args):
        """
        Render report and return the number of pages generated.
        """
        try:
            return self.proxy.Report.execute(*args)
        except (client.ProtocolError, socket.error) as e:
            self.start()
            for x in range(40):
                time.sleep(1)
                try:
                    return self.proxy.Report.execute(*args)
                except (client.ProtocolError, socket.error) as e:
                    self.error("EXCEPTION: %s %s" % (str(e), str(e.args)))
                    pass
                except client.Fault as e:
                    raise except_orm(_('Report Error'), e.faultString)
        except client.Fault as e:
            raise except_orm(_('Report Error'), e.faultString)

# vim:noexpandtab:smartindent:tabstop=8:softtabstop=8:shiftwidth=8:
