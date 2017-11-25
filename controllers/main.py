# -*- encoding: utf-8 -*-

from odoo.addons.web.controllers import main as report
from odoo.http import route, request

import json


_CONTENT_TYPE = {
        'csv': 'text/csv',
        'xls': 'application/vnd.ms-excel', 
        'doc': 'application/msword',
        'rtf': 'application/rtf',
        'odt': 'application/vnd.oasis.opendocument.text',
        'ods': 'application/vnd.oasis.opendocument.spreadsheet',
        'pdf': 'application/pdf',
    
    }

class ReportController(report.ReportController):
    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        if converter == 'jasper':
            report = request.env['ir.actions.report']._get_report_from_name(reportname)
            context = dict(request.env.context)
            if docids:
                docids = [int(i) for i in docids.split(',')]
            if data.get('options'):
                data.update(json.loads(data.pop('options')))
            if data.get('context'):
                # Ignore 'lang' here, because the context in data is the one
                # from the webclient *but* if the user explicitely wants to
                # change the lang, this mechanism overwrites it.
                data['context'] = json.loads(data['context'])
                if data['context'].get('lang'):
                    del data['context']['lang']
                context.update(data['context'])
            file_data = report.with_context(context).render_jasper(
                docids, data=data
            )[0]
            jasperhttpheaders = [
                ('Content-Type', _CONTENT_TYPE.get(report.jasper_output)),
                ('Content-Length', len(file_data)),
                (
                    'Content-Disposition',
                    'attachment; filename=%s%s' % ((report.report_file and report.report_file or 'Report') , '.' + report.jasper_output)
                )
            ]
            return request.make_response(file_data, headers=jasperhttpheaders)
        return super(ReportController, self).report_routes(
            reportname, docids, converter, **data
        )
