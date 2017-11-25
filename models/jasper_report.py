# -*- encoding: utf-8 -*-

import odoo
import tempfile
import logging
import os, stat
from odoo import release, tools, models, api, SUPERUSER_ID
from . JasperReports.BrowseDataGenerator import CsvBrowseDataGenerator
from . JasperReports.RecordDataGenerator import CsvRecordDataGenerator
from . JasperReports.JasperReport import JasperReport
from suds.client import Client
from odoo import models

tools.config['jasperport'] = tools.config.get('jasperport', 8090)
tools.config['jasperpid'] = tools.config.get('jasperpid', 'odoo-jasper.pid')
tools.config['jasperunlink'] = tools.config.get('jasperunlink', True)

_logger = logging.getLogger(__name__)

class Report(models.AbstractModel):
    
    _name = 'report.report_jasper.abstract'
    
    def execute(self, docids, data):
        """
        If self.context contains "return_pages = True" it will return
        the number of pages of the generated report.
        """

        # * Get report path *
        # Not only do we search the report by name but also ensure that
        # 'report_rml' field has the '.jrxml' postfix. This is needed because
        # adding reports using the <report/> tag, doesn't remove the old
        # report record if the id already existed (ie. we're trying to
        # override the 'purchase.order' report in a new module).
        # As the previous record is not removed, we end up with two records
        # named 'purchase.order' so we need to destinguish
        # between the two by searching '.jrxml' in report_rml.
        report_model = self.env['ir.actions.report']
        model_class = self.env[self.env.context.get('active_model')]
        records = model_class.browse(docids)
        report_data = report_model.browse(self.env.context.get('report_id', False))
        self.outputFormat = report_data.jasper_output
        self.reportPath = report_data.report_rml
        self.reportPath = os.path.join(self.addonsPath(), self.reportPath)
        if not os.path.lexists(self.reportPath):
            self.reportPath = self.addonsPath(path=report_data.report_rml)

        # Get report information from the jrxml file
        _logger.info("Requested report: '%s'" % self.reportPath)
        report = JasperReport(self.reportPath)
        self.report = report
        self.rec_ids = docids

        # Create temporary input (XML) and output (PDF) files
        fd, dataFile = tempfile.mkstemp()
        if os.name != 'nt':
            os.chmod(fd, 0o777)
        os.close(fd)
        fd, outputFile = tempfile.mkstemp()
        if os.name != 'nt':
            os.chmod(fd, 0o777)
        os.close(fd)
        self.temporaryFiles = []
        self.temporaryFiles.append(dataFile)
        self.temporaryFiles.append(outputFile)
        _logger.info("Temporary data file: '%s'" % dataFile)

        import time
        start = time.time()

        # If the language used is xpath create the xmlFile in dataFile.
        if report.language() == 'xpath':
            if data.get('data_source', 'model') == 'records':
                generator = CsvRecordDataGenerator(report, records)
            else:
                generator = CsvBrowseDataGenerator(report, 
                                                   self.env.context.get('active_model'),
                                                   self.env, self._cr,
                                                   self.env.user.id, docids,
                                                   self.env.context)
            generator.generate(dataFile)
            self.temporaryFiles += generator.temporaryFiles

        subreportDataFiles = []
        for subreportInfo in report.subreports():
            subreport = subreportInfo['report']
            if subreport.language() == 'xpath':
                message = 'Creating CSV '
                if subreportInfo['pathPrefix']:
                    message += 'with prefix %s ' % subreportInfo['pathPrefix']
                else:
                    message += 'without prefix '
                message += 'for file %s' % subreportInfo['filename']
                _logger.info("%s" % message)

                fd, subreportDataFile = tempfile.mkstemp()
                os.close(fd)
                subreportDataFiles.append({
                    'parameter': subreportInfo['parameter'],
                    'dataFile': subreportDataFile,
                    'jrxmlFile': subreportInfo['filename'],
                })
                self.temporaryFiles.append(subreportDataFile)

                if subreport.isHeader():
                    generator = CsvBrowseDataGenerator(subreport,
                                                       'res.users',
                                                       self.env, self._cr,
                                                       self.env.user.id, [self.env.user.id],
                                                       self.env.context)
                elif data.get('data_source', 'model') == 'records':
                    generator = CsvRecordDataGenerator(subreport,
                                                       records)
                else:
                    generator = CsvBrowseDataGenerator(subreport, 
                                                       self.env.context.get('active_model'),
                                                       self.env, self._cr,
                                                       self.env.user.id, docids,
                                                       self.env.context)
                generator.generate(subreportDataFile)

        # Call the external java application that will generate the
        # PDF file in outputFile
        pages = self.executeReport(dataFile, outputFile, subreportDataFiles)
        elapsed = (time.time() - start) / 60
        _logger.info("ELAPSED: %f" % elapsed)

        # Read data from the generated file and return it
        f = open(outputFile, 'rb')
        try:
            data = f.read()
        finally:
            f.close()

        # Remove all temporary files created during the report
        if tools.config['jasperunlink']:
            for file in self.temporaryFiles:
                try:
                    os.unlink(file)
                except os.error:
                    _logger.warning("Could not remove file '%s'." % file)
        self.temporaryFiles = []

        if self.env.context.get('return_pages'):
            return (data, self.outputFormat, pages)
        else:
            return (data, self.outputFormat)

    def path(self):
        return os.path.abspath(os.path.dirname(__file__))

    def addonsPath(self, path=False):
        if path:
            report_module = path.split(os.path.sep)[0]
            for addons_path in tools.config['addons_path'].split(','):
                if os.path.lexists(addons_path + os.path.sep + report_module):
                    return os.path.normpath(addons_path + os.path.sep + path)

        return os.path.dirname(self.path())

    def systemUserName(self):
        if os.name == 'nt':
            import win32api
            return win32api.GetUserName()
        else:
            import pwd
            return pwd.getpwuid(os.getuid())[0]

    def dsn(self):
        host = tools.config['db_host'] or 'localhost'
        port = tools.config['db_port'] or '5432'
        dbname = self._cr.dbname
        return 'jdbc:postgresql://%s:%s/%s' % (host, port, dbname)

    def userName(self):
        return tools.config['db_user'] or self.env['ir.config_parameter'].get_param('db_user') or self.systemUserName()

    def password(self):
        return tools.config['db_password'] or self.env['ir.config_parameter'].get_param('db_password') or ''

    def executeReport(self, dataFile, outputFile, subreportDataFiles):
        locale = self._context.get('lang', self.env.user.lang or 'en_US')
        url = self.env['ir.config_parameter'].get_param('odoo_jasper_server_url')
        server = Client(url)
        try:
            return server.service.executeReportAll(
                self.outputFormat,
                dataFile,
                self.dsn(),
                self.userName(),
                self.password(),
                subreportDataFiles,
                self.reportPath,
                outputFile, 
                self.report.standardDirectory(),
                locale,
                self.rec_ids,
                )
        except Exception as e:
            _logger.warning(str(e))
            return -1

# vim:noexpandtab:smartindent:tabstop=8:softtabstop=8:shiftwidth=8:
