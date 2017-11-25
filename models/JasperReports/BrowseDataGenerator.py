# -*- encoding: utf-8 -*-

import os
import csv
import copy
import base64
from xml.dom.minidom import getDOMImplementation
from odoo import models
import tempfile
import codecs
import logging
from . AbstractDataGenerator import AbstractDataGenerator


class BrowseDataGenerator(AbstractDataGenerator):
    def __init__(self, report, model, env, cr, uid, ids, context):
        self.report = report
        self.model = model
        self.env = env
        self.cr = cr
        self.uid = uid
        self.ids = ids
        self.context = context
        self._context = context
        self._languages = []
        self.imageFiles = {}
        self.temporaryFiles = []
        self.logger = logging.getLogger(__name__)

    def warning(self, message):
        if self.logger:
            self.logger.warning("%s" % message)

    def languages(self):
        if self._languages:
            return self._languages
        ids = self.env['res.lang'
                       ].search(self.cr, self.uid,
                                [('translatable', '=', '1')])
        self._languages = self.env['res.lang'].read(self.cr, self.uid,
                                                    ids, ['code'])
        self._languages = [x['code'] for x in self._languages]
        return self._languages

    def valueInAllLanguages(self, model, id, field):
        context = copy.copy(self._context)
        model = self.env[model]
        values = {}
        for language in self.languages():
            if language == 'en_US':
                context['lang'] = False
            else:
                context['lang'] = language
            value = model.read(self.cr, self.uid, [id], [field],
                               context=context)
            values[language] = value[0][field] or ''

            if(model._fields[field].type == 'selection' and
               model._fields[field
                              ].selection):
                field_data = model.fields_get(self.cr, self.uid,
                                              allfields=[field],
                                              context=context)
                values[language
                       ] = dict(field_data[field]['selection'
                                                  ]).get(values[language
                                                                ],
                                                         values[language])

        result = []
        for key, value in values.iteritems():
            result.append('%s~%s' % (key, value))
        return '|'.join(result)

    def generateIds(self, record, relations, path, currentRecords):
        unrepeated = set([field.partition('/')[0] for field in relations])
        for relation in unrepeated:
            root = relation.partition('/')[0]
            if path:
                currentPath = '%s/%s' % (path, root)
            else:
                currentPath = root
            if root == 'Attachments':
                ids = self.env['ir.attachment'
                               ].search(self.cr,
                                        self.uid,
                                        [('res_model', '=', record._name),
                                         ('res_id', '=', record.id)])
                value = self.env['ir.attachment'
                                 ].browse(self.cr, self.uid, ids,
                                          self._context)
            elif root == 'User':
                value = self.env['res.users'
                                 ].browse(self.cr, self.uid,
                                          [self.uid], self._context)
            else:
                if root == 'id':
                    value = record.id
                elif hasattr(record, root):
                    value = getattr(record, root)
                else:
                    warng = "Field '%s' does not exist in model '%s'."
                    self.warning(warng % (root, record._name))
                    continue

                if isinstance(value, models.BaseModel):
                    relations2 = [f.partition('/')[2] for f in relations
                                  if f.partition('/')[0] == root and
                                  f.partition('/')[2]]
                    return self.generateIds(value, relations2, currentPath,
                                            currentRecords)

                if not isinstance(value, models.BaseModel):
                    wrng2 = "Field '%s' in model '%s' is not a relation."
                    self.warning(wrng2 % (root, self.model))
                    return currentRecords

            # Only join if there are any records because it's a LEFT JOIN
            # If we wanted an INNER JOIN we wouldn't check for "value" and
            # return an empty currentRecords
            if value:
                # Only
                newRecords = []
                for v in value:
                    currentNewRecords = []
                    for id in currentRecords:
                        new = id.copy()
                        new[currentPath] = v
                        currentNewRecords.append(new)
                    relations2 = [f.partition('/')[2] for f in relations
                                  if f.partition('/')[0] == root and
                                  f.partition('/')[2]]
                    newRecords += self.generateIds(v, relations2, currentPath,
                                                   currentNewRecords)

                currentRecords = newRecords
        return currentRecords


class XmlBrowseDataGenerator(BrowseDataGenerator):
    # XML file generation works as follows:
    # By default (if no OPENERP_RELATIONS property exists in the report)
    # a record will be created for each model id we've been asked to show.
    # If there are any elements in the OPENERP_RELATIONS list,
    # they will imply a LEFT JOIN like behaviour on the rows to be shown.
    def generate(self, fileName):
        self.allRecords = []
        relations = self.report.relations()
        # The following loop generates one entry to allRecords list
        # for each record that will be created. If there are any relations
        # it acts like a LEFT JOIN against the main model/table.
        for record in self.env[self.model].browse(self.cr, self.uid,
                                                  self.ids, self._context):
            newRecords = self.generateIds(record, relations, '',
                                          [{'root': record}])
            copies = 1
            if(self.report.copiesField() and record.__hasattr__
               (self.report.copiesField())):
                copies = int(record.__getattr__(self.report.copiesField()))
            for new in newRecords:
                for x in range(copies):
                    self.allRecords.append(new)

        # Once all records have been calculated, create the
        # XML structure itself
        self.document = getDOMImplementation().createDocument(None, 'data',
                                                              None)
        topNode = self.document.documentElement
        for records in self.allRecords:
            recordNode = self.document.createElement('record')
            topNode.appendChild(recordNode)
            self.generateXmlRecord(records['root'], records, recordNode, '',
                                   self.report.fields())

        # Once created, the only missing step is to store the XML into a file
        f = codecs.open(fileName, 'wb+', 'utf-8')
        try:
            topNode.writexml(f)
        finally:
            f.close()

    def generateXmlRecord(self, record, records, recordNode, path, fields):
        # One field (many2one, many2many or one2many) can appear several times.
        # Process each "root" field only once by using a set.
        unrepeated = set([field.partition('/')[0] for field in fields])
        for field in unrepeated:
            root = field.partition('/')[0]
            if path:
                currentPath = '%s/%s' % (path, root)
            else:
                currentPath = root
            fieldNode = self.document.createElement(root)
            recordNode.appendChild(fieldNode)
            if root == 'Attachments':
                ids = self.env['ir.attachment'
                               ].search(self.cr, self.uid,
                                        [('res_model', '=',
                                          record._name),
                                         ('res_id', '=', record.id)])
                value = self.env['ir.attachment'
                                 ].browse(self.cr, self.uid, ids)
            elif root == 'User':
                value = self.env['res.users'
                                 ].browse(self.cr, self.uid, self.uid,
                                          self._context)
            else:
                if root == 'id':
                    value = record.id
                elif hasattr(record, root):
                    value = getattr(record, root)
                else:
                    value = None
                    wrng4 = "Field '%s' does not exist in model '%s'."
                    self.warning(wrng4 % (root, record._name))

            # Check if it's a many2one
            if isinstance(value, models.BaseModel):
                fields2 = [f.partition('/')[2] for f in fields
                           if f.partition('/')[0] == root]
                self.generateXmlRecord(value, records, fieldNode, currentPath,
                                       fields2)
                continue

            # Check if it's a one2many or many2many
            if isinstance(value, models.BaseModel):
                if not value:
                    continue
                fields2 = [f.partition('/')[2] for f in fields
                           if f.partition('/')[0] == root]
                if currentPath in records:
                    self.generateXmlRecord(records[currentPath], records,
                                           fieldNode, currentPath, fields2)
                else:
                    # If the field is not marked to be iterated use
                    # the first record only
                    self.generateXmlRecord(value[0], records, fieldNode,
                                           currentPath, fields2)
                continue

            if field in record._fields:
                field_type = record._fields[field].type

            # The rest of field types must be converted into str
            if field == 'id':
                # Check for field 'id' because we can't find it's
                # type in _columns
                value = str(value)
            elif value is False:
                value = ''
            elif field_type == 'date':
                value = '%s 00:00:00' % str(value)
            elif field_type == 'binary':
                imageId = (record.id, field)
                if imageId in self.imageFiles:
                    fileName = self.imageFiles[imageId]
                else:
                    fd, fileName = tempfile.mkstemp()
                    try:
                        os.write(fd, base64.decodestring(value))
                    finally:
                        os.close(fd)
                    self.temporaryFiles.append(fileName)
                    self.imageFiles[imageId] = fileName
                value = fileName
            elif isinstance(value, str):
                value = str(value, 'utf-8')
            elif isinstance(value, float):
                value = '%.10f' % value
            elif not isinstance(value, str):
                value = str(value)

            valueNode = self.document.createTextNode(value)
            fieldNode.appendChild(valueNode)


class CsvBrowseDataGenerator(BrowseDataGenerator):
    # CSV file generation works as follows:
    # By default (if no OPENERP_RELATIONS property exists in the report)
    # a record will be created for each model id we've been asked to show.
    # If there are any elements in the OPENERP_RELATIONS list,
    # they will imply a LEFT JOIN like behaviour on the rows to be shown.
    def generate(self, fileName):
        self.allRecords = []
        relations = self.report.relations()
        # The following loop generates one entry to allRecords list
        # for each record that will be created. If there are any relations
        # it acts like a LEFT JOIN against the main model/table.
        reportCopies = self.report.copies() or 1
        sequence = 0
        copiesField = self.report.copiesField()
        for record in self.env[self.model].with_context(self._context).browse(self.ids):
            newRecords = self.generateIds(record, relations, '',
                                          [{'root': record}])
            copies = reportCopies
            if copiesField and record.__hasattr__(copiesField):
                copies = copies * int(record.__getattr__(copiesField))
            sequence += 1
            subsequence = 0
            for new in newRecords:
                new['sequence'] = sequence
                new['subsequence'] = subsequence
                subsequence += 1
                for x in range(copies):
                    new['copy'] = x
                    self.allRecords.append(new.copy())

        f = open(fileName, 'w+', newline='')
        try:
            csv.QUOTE_ALL = True
            # JasperReports CSV reader requires an extra colon at the
            # end of the line.
            writer = csv.DictWriter(f, self.report.fieldNames() + [''],
                                    delimiter=",", quotechar='"')
            writer.writeheader()
            # Once all records have been calculated,
            # create the CSV structure itself
            for records in self.allRecords:
                row = {}
                self.generateCsvRecord(records['root'], records, row, '',
                                       self.report.fields(),
                                       records['sequence'],
                                       records['subsequence'],
                                       records['copy'])
                if row:
                    writer.writerow(row)
        finally:
            f.close()

    def generateCsvRecord(self, record, records, row, path, fields, sequence,
                          subsequence, copy):
        # One field (many2one, many2many or one2many) can appear several times
        # Process each "root" field only once by using a set.
        unrepeated = set([field.partition('/')[0] for field in fields])
        for field in unrepeated:
            root = field.partition('/')[0]
            if path:
                currentPath = '%s/%s' % (path, root)
            else:
                currentPath = root
            if root == 'Attachments':
                ids = self.env['ir.attachment'
                               ].search(self.cr, self.uid,
                                        [('res_model', '=', record._name),
                                         ('res_id', '=', record.id)])
                value = self.env['ir.attachment'
                                 ].browse(self.cr, self.uid, ids)
            elif root == 'User':
                value = self.env.user
            elif root == 'Special':
                fields2 = [f.partition('/')[2] for f in fields
                           if f.partition('/')[0] == root]
                for f in fields2:
                    p = '%s/%s' % (currentPath, f)
                    if f == 'sequence':
                        row[self.report.fields()[p]['name']] = sequence
                    elif f == 'subsequence':
                        row[self.report.fields()[p]['name']] = subsequence
                    elif f == 'copy':
                        row[self.report.fields()[p]['name']] = copy
                continue
            else:
                if root == 'id':
                    value = record.id
                elif hasattr(record, root):
                    value = getattr(record, root)
                else:
                    value = None
                    wrng6 = "Field '%s' (path: %s) does not \
                    exist in model '%s'."
                    self.warning(wrng6 % (root, currentPath, record._name))

            # Check if it's a many2one
            if isinstance(value, models.BaseModel):
                fields2 = [f.partition('/')[2] for f in fields
                           if f.partition('/')[0] == root]
                self.generateCsvRecord(value, records, row, currentPath,
                                       fields2, sequence, subsequence, copy)
                continue

            # Check if it's a one2many or many2many
            if isinstance(value, models.BaseModel):
                if not value:
                    continue
                fields2 = [f.partition('/')[2] for f in fields
                           if f.partition('/')[0] == root]
                if currentPath in records:
                    self.generateCsvRecord(records[currentPath], records, row,
                                           currentPath, fields2, sequence,
                                           subsequence, copy)
                else:
                    # If the field is not marked to be iterated
                    # use the first record only
                    self.generateCsvRecord(value[0], records, row,
                                           currentPath, fields2, sequence,
                                           subsequence, copy)
                continue

            # The field might not appear in the self.report.fields()
            # only when the field is a many2one but in this case it's null.
            # This will make the path to look like: "journal_id",
            # when the field actually in the report is "journal_id/name",
            # for example.In order not to change the way we detect many2one
            # fields, we simply check that the field is in self.report.
            # fields() and that's it.
            if currentPath not in self.report.fields():
                continue

            # Show all translations for a field
            type = self.report.fields()[currentPath]['type']
            if type == 'java.lang.Object':
                value = self.valueInAllLanguages(record._name, record.id, root)

            if field in record._fields:
                field_type = record._fields[field].type

            # The rest of field types must be converted into str
            if field == 'id':
                # Check for field 'id' because we can't find it's
                # type in _columns
                value = str(value)
            elif value in (False, None):
                value = ''
            elif field_type == 'date':
                value = '%s 00:00:00' % str(value)
            elif field_type == 'binary':
                imageId = (record.id, field)
                if imageId in self.imageFiles:
                    fileName = self.imageFiles[imageId]
                else:
                    fd, fileName = tempfile.mkstemp()
                    try:
                        os.write(fd, base64.decodestring(value))
                    finally:
                        os.close(fd)
                    self.temporaryFiles.append(fileName)
                    self.imageFiles[imageId] = fileName
                value = fileName
            elif isinstance(value, str):
                value = value
            elif isinstance(value, float):
                value = '%.10f' % value
            elif not isinstance(value, str):
                value = str(value)
            row[self.report.fields()[currentPath]['name']] = value

# vim:noexpandtab:smartindent:tabstop=8:softtabstop=8:shiftwidth=8:
