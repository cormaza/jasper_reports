# -*- encoding: utf-8 -*-

import os
import base64
from . import jasper_report
from odoo.exceptions import except_orm, UserError
from odoo import models, fields, api, _
import unicodedata
from xml.dom.minidom import getDOMImplementation

src_chars = """ '"()/*-+?¿!&$[]{}@#`'^:;<>=~%,\\"""
dst_chars = """________________________________"""


class report_xml_file(models.Model):
    _name = 'ir.actions.report.file'

    file = fields.Binary('File', required=True, filters="*.jrxml,*.properties,*.ttf",)
    filename = fields.Char('File Name')
    report_id = fields.Many2one('ir.actions.report', 'Report', ondelete='cascade')
    default = fields.Boolean('Default')

    @api.model
    def create(self, vals):
        record = super(report_xml_file, self).create(vals)
        record.report_id.update_report_data()
        return record

    @api.multi
    def write(self, vals):
        result = super(report_xml_file, self).write(vals)
        for attachment in self:
            attachment.report_id.update_report_data()
        return result


# Inherit ir.actions.report and add an action to be able to store
# .jrxml and .properties files attached to the report so they can be
# used as reports in the application.
class ReportXmlAction(models.Model):
    _inherit = 'ir.actions.report'

    report_type = fields.Selection(selection_add=[("jasper", "Jasper")])
    jasper_output = fields.Selection([
        ('csv', 'CSV'),
        ('xls', 'XLS'), 
        ('doc', 'DOC'),
        ('rtf', 'RTF'),
        ('odt', 'ODT'),
        ('ods', 'ODS'),
        ('pdf', 'PDF'),
        ], 'Jasper Output', default='pdf')
    jasper_file_ids = fields.One2many('ir.actions.report.file',
                                      'report_id', 'Files', help='')
    jasper_model_id = fields.Many2one('ir.model', 'Model', help='')
    report_rml = fields.Char(string=u'Jasper File Path', index=True, 
                             required=False, readonly=False, states={}, help=u"") 

    @api.model
    def create(self, vals):
        if 'jasper_model_id' in vals:
            vals['model'] = self.env['ir.model'].browse(vals['jasper_model_id']).model
        return super(ReportXmlAction, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'jasper_model_id' in vals and vals.get('jasper_model_id', False):
            vals['model'] = self.env['ir.model'].browse(vals['jasper_model_id']).model
        return super(ReportXmlAction, self).write(vals)

    @api.multi
    def update_report_data(self):
        if self._context is None:
            self._context = {}
        pool_values = self.env['ir.values']
        for report in self:
            has_default = False
            # Browse attachments and store .jrxml and .properties
            # into jasper_reports/custom_reportsdirectory. Also add
            # or update ir.values data so they're shown on model views.for
            # attachment in self.env['ir.attachment'].browse(attachmentIds)
            for attachment in report.jasper_file_ids:
                content = attachment.file
                fileName = attachment.filename
                if not fileName or not content:
                    continue
                path = self.save_file(fileName, content)
                if '.jrxml' in fileName:
                    if attachment.default:
                        if has_default:
                            raise except_orm(_('Error'),
                                             _('There is more than one \
                                             report marked as default'))
                        has_default = True
                        # Update path into report_rml field.
                        my_obj = self.browse([report.id])
                        my_obj.write({'report_rml': path})
                        ser_arg = [('value', '=',
                                    'ir.actions.report,%s' % report.id)]
                        valuesId = pool_values.search(ser_arg)
                        data = {
                            'name': report.name,
                            'model': report.model,
                            'key': 'action',
                            'object': True,
                            'key2': 'client_print_multi',
                            'value': 'ir.actions.report,%s' % report.id
                        }
                        if not valuesId.ids:
                            valuesId = pool_values.create(data)
                        else:
                            for pool_obj in pool_values.browse(valuesId.ids):
                                pool_obj.write(data)
                                valuesId = valuesId[0]

            if not has_default:
                raise except_orm(_('Error'),
                                 _('No report has been marked as default! \
                                 You need atleast one jrxml report!'))

        return True

    def save_file(self, name, value):
        path = os.path.abspath(os.path.dirname(__file__))
        path += '/custom_reports/%s' % name
        f = open(path, 'wb+')
        try:
            f.write(base64.decodestring(value))
        finally:
            f.close()
        path = 'jasper_reports/models/custom_reports/%s' % name
        return path

    def unaccent(self, text):
        if isinstance(text, str):
            text = text.encode('utf-8')
        output = text
        for c in range(len(src_chars)):
            if c >= len(dst_chars):
                break
            output = output.replace(src_chars[c], dst_chars[c])
        output = unicodedata.normalize('NFKD', output).encode('ASCII', 'ignore')
        return output.strip('_').encode('utf-8')

    @api.model
    def generate_xml(self, pool, modelName, parentNode, document, depth,
                     first_call):
        if self._context is None:
            self._context = {}
        # First of all add "id" field
        fieldNode = document.createElement('id')
        parentNode.appendChild(fieldNode)
        valueNode = document.createTextNode('1')
        fieldNode.appendChild(valueNode)
        language = self._context.get('lang', self.env.user.lang or 'en_US')
        if language == 'en_US':
            language = False

        # Then add all fields in alphabetical order
        model = pool.get(modelName)
        fields = model._fields.keys()
#        for magic_field in models.MAGIC_COLUMNS + [model.CONCURRENCY_CHECK_FIELD]:
        for magic_field in [model.CONCURRENCY_CHECK_FIELD]:
            if magic_field in fields: 
                fields.pop(fields.index(magic_field))
        # Remove duplicates because model may have fields with the
        # same name as it's parent
        fields = sorted(list(set(fields)))
        for field in fields:
            name = False
            if language:
                # Obtain field string for user's language.
                name = self.env['ir.translation']._get_source(
                    '{model},{field}'.format(model=modelName, field=field),
                    'field', language)
            if not name:
                # If there's not description in user's language,
                # use default (english) one.
                if field in model._fields.keys():
                    name = model._fields[field].string

            if name:
                name = self.unaccent(name)
            # After unaccent the name might result in an empty string
            if name:
                name = '%s-%s' % (self.unaccent(name), field)
            else:
                name = field
            fieldNode = document.createElement(name)

            parentNode.appendChild(fieldNode)
            if field in pool.get(modelName)._fields:
                fieldType = model._fields[field].type
            if fieldType in ('many2one', 'one2many', 'many2many'):
                if depth <= 1:
                    continue
                if field in model._fields:
                    newName = model._fields[field].comodel_name
                self.generate_xml(pool, newName, fieldNode, document,
                                  depth - 1, False)
                continue

            value = field
            if fieldType == 'float':
                value = '12345.67'
            elif fieldType == 'integer':
                value = '12345'
            elif fieldType == 'date':
                value = '2009-12-31 00:00:00'
            elif fieldType == 'time':
                value = '12:34:56'
            elif fieldType == 'datetime':
                value = '2009-12-31 12:34:56'

            valueNode = document.createTextNode(value)
            fieldNode.appendChild(valueNode)

        if depth > 1 and modelName != 'Attachments':
            # Create relation with attachments
            fieldNode = document.createElement('%s-Attachments' % self.
                                               unaccent(_('Attachments')))
            parentNode.appendChild(fieldNode)
            self.generate_xml(pool, 'ir.attachment', fieldNode, document,
                              depth - 1, False)

        if first_call:
            # Create relation with user
            fieldNode = document.createElement('%s-User' % self.unaccent
                                               (_('User')))
            parentNode.appendChild(fieldNode)
            self.generate_xml(pool, 'res.users', fieldNode, document,
                              depth - 1, False)

            # Create special entries
            fieldNode = document.createElement('%s-Special' % self.unaccent
                                               (_('Special')))
            parentNode.appendChild(fieldNode)

            newNode = document.createElement('copy')
            fieldNode.appendChild(newNode)
            valueNode = document.createTextNode('1')
            newNode.appendChild(valueNode)

            newNode = document.createElement('sequence')
            fieldNode.appendChild(newNode)
            valueNode = document.createTextNode('1')
            newNode.appendChild(valueNode)

            newNode = document.createElement('subsequence')
            fieldNode.appendChild(newNode)
            valueNode = document.createTextNode('1')
            newNode.appendChild(valueNode)

    @api.model
    def create_xml(self, model, depth):
        if self._context is None:
            self._context = {}
        document = getDOMImplementation().createDocument(None, 'data', None)
        topNode = document.documentElement
        recordNode = document.createElement('record')
        topNode.appendChild(recordNode)
        self.generate_xml(self.pool, model, recordNode, document, depth, True)
        topNode.toxml()
        return topNode.toxml()

    @api.model
    def _get_report_from_name(self, report_name):
        res = super(ReportXmlAction, self)._get_report_from_name(report_name)
        if res:
            return res
        report_model = self.env['ir.actions.report']
        qwebtypes = ['jasper']
        conditions = [('report_type', 'in', qwebtypes),
                      ('report_name', '=', report_name)]
        context = self.env['res.users'].context_get()
        return report_model.with_context(context).search(conditions, limit=1)

    @api.model
    def render_jasper(self, docids, data):
        abstrac_model = self.env['report.report_jasper.abstract']
        report = self.env['ir.actions.report']._get_report_from_name(self.report_name)
        if report is None:
            raise UserError(_('%s model was not found' % self.report_name))
        return abstrac_model.with_context({
            'report_id': report.id,
            'active_model': self.model,
        }).execute(docids, data)

ReportXmlAction()