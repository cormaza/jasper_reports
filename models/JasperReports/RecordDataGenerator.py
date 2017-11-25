# -*- encoding: utf-8 -*-

import csv
from xml.dom.minidom import getDOMImplementation
import codecs
from . AbstractDataGenerator import AbstractDataGenerator


class CsvRecordDataGenerator(AbstractDataGenerator):
    def __init__(self, report, records):
        self.report = report
        self.records = records
        self.temporaryFiles = []

    # CSV file generation using a list of dictionaries provided by
    # the parser function.
    def generate(self, fileName):
        f = open(fileName, 'wb+')
        try:
            csv.QUOTE_ALL = True
            fieldNames = self.report.fieldNames()
            # JasperReports CSV reader requires an extra colon
            # at the end of the line.
            writer = csv.DictWriter(f, fieldNames + [''], delimiter=',',
                                    quotechar='"')
            header = {}
            for field in fieldNames + ['']:
                header[field] = field
            writer.writerow(header)
            error_reported_fields = []
            for record in self.records:
                row = {}
                for field in record:
                    if field not in self.report.fields():
                        if field not in error_reported_fields:
                            error_reported_fields.append(field)
                        continue
                    value = record.get(field, False)
                    if value is False:
                        value = ''
                    elif isinstance(value, str):
                        value = value.encode('utf-8')
                    elif isinstance(value, float):
                        value = '%.10f' % value
                    elif not isinstance(value, str):
                        value = str(value)
                    row[self.report.fields()[field]['name']] = value
                writer.writerow(row)
        finally:
            f.close()


class XmlRecordDataGenerator(AbstractDataGenerator):

    # XML file generation using a list of dictionaries provided by
    # the parser function.
    def generate(self, fileName):
        # Once all records have been calculated, create the XML structure
        self.document = getDOMImplementation().createDocument(None, 'data',
                                                              None)
        topNode = self.document.documentElement
        for record in self.data['records']:
            recordNode = self.document.createElement('record')
            topNode.appendChild(recordNode)
            for field, value in record.iteritems():
                fieldNode = self.document.createElement(field)
                recordNode.appendChild(fieldNode)
                # The rest of field types must be converted into str
                if value is False:
                    value = ''
                elif isinstance(value, str):
                    value = str(value, 'utf-8')
                elif isinstance(value, float):
                    value = '%.10f' % value
                elif not isinstance(value, str):
                    value = str(value)
                valueNode = self.document.createTextNode(value)
                fieldNode.appendChild(valueNode)
        # Once created, the only missing step is to store the XML into a file
        f = codecs.open(fileName, 'wb+', 'utf-8')
        try:
            topNode.writexml(f)
        finally:
            f.close()

# vim:noexpandtab:smartindent:tabstop=8:softtabstop=8:shiftwidth=8:
