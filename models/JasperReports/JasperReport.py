# -*- encoding: utf-8 -*-

import os
import lxml.etree as ET
import re

try:
    from tools.safe_eval import safe_eval
    import tools
except ImportError:
    from odoo.tools.safe_eval import safe_eval
    from odoo import tools

dataSourceExpressionRegExp = re.compile(r"""\$P\{(\w+)\}""")


class JasperReport:
    def __init__(self, fileName='', pathPrefix=''):
        self._reportPath = fileName
        self._pathPrefix = pathPrefix.strip()
        if self._pathPrefix and self._pathPrefix[-1] != '/':
            self._pathPrefix += '/'

        self._language = 'xpath'
        self._relations = []
        self._fields = {}
        self._fieldNames = []
        self._subreports = []
        self._datasets = []
        self._copies = 1
        self._copiesField = False
        self._isHeader = False
        if fileName:
            self.extractProperties()

    def language(self):
        return self._language

    def fields(self):
        return self._fields

    def fieldNames(self):
        return self._fieldNames

    def subreports(self):
        return self._subreports

    def datasets(self):
        return self._datasets

    def relations(self):
        return self._relations

    def copiesField(self):
        return self._copiesField

    def copies(self):
        return self._copies

    def isHeader(self):
        return self._isHeader

    def subreportDirectory(self):
        return os.path.join(os.path.abspath
                            (os.path.dirname(self._reportPath)), '')

    def standardDirectory(self):
        jasperdir = tools.config.get('jasperdir')
        if jasperdir:
            if jasperdir.endswith(os.sep):
                return jasperdir
            else:
                return os.path.join(jasperdir, '')
        return os.path.join(os.path.abspath(os.path.dirname(__file__)),
                            '..', 'report', '')

    def extractFields(self, fieldTags, ns):
        # fields and fieldNames
        fields = {}
        fieldNames = []
        # fieldTags = doc.xpath('/jr:jasperReport/jr:field', namespaces=nss)
        for tag in fieldTags:
            name = tag.get('name')
            class_type = tag.get('class')
            path = tag.findtext('{%s}fieldDescription' % ns, '').strip()
            # Make the path relative if it isn't already
            if path.startswith('/data/record/'):
                path = self._pathPrefix + path[13:]
            # Remove language specific data from the path so:
            # Empresa-partner_id/Nom-name becomes partner_id/name
            # We need to consider the fact that the name in user's language
            # might not exist, hence the easiest thing to do is split and [-1]
            newPath = []
            for x in path.split('/'):
                newPath.append(x.split('-')[-1])
            path = '/'.join(newPath)
            if path:
                fields[path] = {'name': name,
                                'type': class_type,
                                }
                fieldNames.append(name)
        return fields, fieldNames

    def extractProperties(self):
        # The function will read all relevant information from the jrxml file

        doc = ET.parse(self._reportPath)

        # Define namespaces
        ns = 'http://jasperreports.sourceforge.net/jasperreports'
        nss = {'jr': ns}

        # Language
        # is XPath.
        langTags = doc.xpath('/jr:jasperReport/jr:queryString', namespaces=nss)
        if langTags:
            if langTags[0].get('language'):
                self._language = langTags[0].get('language').lower()

        # Relations
        ex_path = '/jr:jasperReport/jr:property[@name="OPENERP_RELATIONS"]'
        relationTags = doc.xpath(ex_path, namespaces=nss)
        if relationTags and 'value' in relationTags[0].keys():
            relation = relationTags[0].get('value').strip()
            if relation.startswith('['):
                self._relations = safe_eval(relationTags[0].get('value'), {})
            else:
                self._relations = [x.strip() for x in relation.split(',')]
            self._relations = [self._pathPrefix + x for x in self._relations]
        if not self._relations and self._pathPrefix:
            self._relations = [self._pathPrefix[:-1]]

        # Repeat field
        path1 = '/jr:jasperReport/jr:property[@name="odoo_COPIES_FIELD"]'
        copiesFieldTags = doc.xpath(path1, namespaces=nss)
        if copiesFieldTags and 'value' in copiesFieldTags[0].keys():
            self._copiesField = (self._pathPrefix + copiesFieldTags[0].get
                                 ('value'))

        # Repeat
        path2 = '/jr:jasperReport/jr:property[@name="odoo_COPIES"]'
        copiesTags = doc.xpath(path2, namespaces=nss)
        if copiesTags and 'value' in copiesTags[0].keys():
            self._copies = int(copiesTags[0].get('value'))

        self._isHeader = False
        path3 = '/jr:jasperReport/jr:property[@name="odoo_HEADER"]'
        headerTags = doc.xpath(path3, namespaces=nss)
        if headerTags and 'value' in headerTags[0].keys():
            self._isHeader = True

        fieldTags = doc.xpath('/jr:jasperReport/jr:field', namespaces=nss)
        self._fields, self._fieldNames = self.extractFields(fieldTags, ns)

        # Subreports
        # Here we expect the following structure in the .jrxml file:
        # <subreport>
        #  <dataSourceExpression><![CDATA[$P{REPORT_DATA_SOURCE}]]>
        # </dataSourceExpression>
        # <subreportExpression class="java.lang.String">
        # <![CDATA[$P{STANDARD_DIR} + "report_header.jasper"]]>
        # </subreportExpression>
        # </subreport>
        subreportTags = doc.xpath('//jr:subreport', namespaces=nss)
        for tag in subreportTags:
            text1 = '{%s}dataSourceExpression'
            dataSourceExpression = tag.findtext(text1 % ns, '')
            if not dataSourceExpression:
                continue
            dataSourceExpression = dataSourceExpression.strip()
            m = dataSourceExpressionRegExp.match(dataSourceExpression)
            if not m:
                continue
            dataSourceExpression = m.group(1)
            if dataSourceExpression == 'REPORT_DATA_SOURCE':
                continue

            subreportExpression = tag.findtext('{%s}subreportExpression' % ns,
                                               '')
            if not subreportExpression:
                continue
            subreportExpression = subreportExpression.strip()
            subreportExpression = (subreportExpression.replace
                                   ('$P{STANDARD_DIR}',
                                    '"%s"' % self.standardDirectory()))
            subreportExpression = (subreportExpression.replace
                                   ('$P{SUBREPORT_DIR}',
                                    '"%s"' % self.subreportDirectory()))
            try:
                subreportExpression = safe_eval(subreportExpression, {})
            except:
                continue
            if subreportExpression.endswith('.jasper'):
                subreportExpression = subreportExpression[:-6] + 'jrxml'

            # Model
            model = ''
            path4 = '//jr:reportElement/jr:property[@name="odoo_MODEL"]'
            modelTags = tag.xpath(path4, namespaces=nss)
            if modelTags and 'value' in modelTags[0].keys():
                model = modelTags[0].get('value')

            pathPrefix = ''
            pat = '//jr:reportElement/jr:property[@name="odoo_PATH_PREFIX"]'
            pathPrefixTags = tag.xpath(pat, namespaces=nss)
            if pathPrefixTags and 'value' in pathPrefixTags[0].keys():
                pathPrefix = pathPrefixTags[0].get('value')

            self._isHeader = False
            path5 = '//jr:reportElement/jr:property[@name="odoo_HEADER"]'
            headerTags = tag.xpath(path5, namespaces=nss)
            if headerTags and 'value' in headerTags[0].keys():
                self._isHeader = True

            # Add our own pathPrefix to subreport's pathPrefix
            subPrefix = []
            if self._pathPrefix:
                subPrefix.append(self._pathPrefix)
            if pathPrefix:
                subPrefix.append(pathPrefix)
            subPrefix = '/'.join(subPrefix)

            subreport = JasperReport(subreportExpression, subPrefix)
            self._subreports.append({
                'parameter': dataSourceExpression,
                'filename': subreportExpression,
                'model': model,
                'pathPrefix': pathPrefix,
                'report': subreport,
                'depth': 1,
            })
            for subsubInfo in subreport.subreports():
                subsubInfo['depth'] += 1
                # Note hat 'parameter' (the one used to pass report's
                # DataSource) must be the same in all reports
                self._subreports.append(subsubInfo)

        # Dataset
        # Here we expect the following structure in the .jrxml file:
        # <datasetRun>
        #  <dataSourceExpression><![CDATA[$P{REPORT_DATA_SOURCE}]]>
        # </dataSourceExpression>
        # </datasetRun>
        datasetTags = doc.xpath('//jr:datasetRun', namespaces=nss)
        for tag in datasetTags:
            path7 = '{%s}dataSourceExpression'
            dataSourceExpression = tag.findtext(path7 % ns, '')
            if not dataSourceExpression:
                continue
            dataSourceExpression = dataSourceExpression.strip()
            m = dataSourceExpressionRegExp.match(dataSourceExpression)
            if not m:
                continue
            dataSourceExpression = m.group(1)
            if dataSourceExpression == 'REPORT_DATA_SOURCE':
                continue
            subDatasetName = tag.get('subDataset')
            if not subDatasetName:
                continue

            # Relations
            relations = []
            path8 = '../../jr:reportElement/jr:property \
            [@name="OPENERP_RELATIONS"]'
            relationTags = tag.xpath(path8, namespaces=nss)
            if relationTags and 'value' in relationTags[0].keys():
                relation = relationTags[0].get('value').strip()
                if relation.startswith('['):
                    relations = safe_eval(relationTags[0].get('value'), {})
                else:
                    relations = [x.strip() for x in relation.split(',')]
                relations = [self._pathPrefix + x for x in relations]
            if not relations and self._pathPrefix:
                relations = [self._pathPrefix[:-1]]

            # Repeat field
            copiesField = None
            path9 = '../../jr:reportElement/jr:property \
            [@name="odoo_COPIES_FIELD"]'
            copiesFieldTags = tag.xpath(path9, namespaces=nss)
            if copiesFieldTags and 'value' in copiesFieldTags[0].keys():
                copiesField = self._pathPrefix + copiesFieldTags[0
                                                                 ].get('value'
                                                                       )

            # Repeat
            copies = None
            path11 = '../../jr:reportElement/jr:property \
            [@name="odoo_COPIES"]'
            copiesTags = tag.xpath(path11, namespaces=nss)
            if copiesTags and 'value' in copiesTags[0].keys():
                copies = int(copiesTags[0].get('value'))

            # Model
            model = ''
            path12 = '../../jr:reportElement/jr:property \
            [@name="odoo_MODEL"]'
            modelTags = tag.xpath(path12, namespaces=nss)
            if modelTags and 'value' in modelTags[0].keys():
                model = modelTags[0].get('value')

            pathPrefix = ''
            path13 = '../../jr:reportElement/jr:property \
            [@name="odoo_PATH_PREFIX"]'
            pathPrefixTags = tag.xpath(path13, namespaces=nss)
            if pathPrefixTags and 'value' in pathPrefixTags[0].keys():
                pathPrefix = pathPrefixTags[0].get('value')

            # We need to find the appropriate subDataset definition
            # for this dataset run.
            path14 = '//jr:subDataset[@name="%s"]'
            subDataset = doc.xpath(path14 % subDatasetName, namespaces=nss)[0]
            fieldTags = subDataset.xpath('jr:field', namespaces=nss)
            fields, fieldNames = self.extractFields(fieldTags, ns)

            dataset = JasperReport()
            dataset._fields = fields
            dataset._fieldNames = fieldNames
            dataset._relations = relations
            dataset._copiesField = copiesField
            dataset._copies = copies
            self._subreports.append({
                'parameter': dataSourceExpression,
                'model': model,
                'pathPrefix': pathPrefix,
                'report': dataset,
                'filename': 'DATASET',
            })

# vim:noexpandtab:smartindent:tabstop=8:softtabstop=8:shiftwidth=8:
