# -*- encoding: utf-8 -*-

{
    "name": "Jasper Reports",
    "version": "1.1.1",
    "description": '''
    This module integrates Jasper Reports with odoo. V6 and v7 compatible"
    version was made by NaN-tic.
    Serpent Consulting Services Pvt. Ltd. has migrated it to v8. 
    Christopher Ormaza has migrated to v
    ''',
    "author": "NaN·tic, Serpent Consulting Services Pvt. Ltd., Christopher Ormaza",
    "website": "http://www.nan-tic.com, http://www.serpentcs.com, https://www.vision-estrategica.com",
    'images': [],
    "depends": [
                "base",
                "web",
                ],
    "category": "Generic Modules/Jasper Reports",
    "data": [
             'data/jasper_data.xml',
             'security/ir.model.access.csv',
             'wizard/jasper_create_data_template.xml',
             'wizard/jasper_wizard.xml',
             'views/report_xml_view.xml',
             'views/assets_view.xml',
             ],
    "active": False,
    "installable": True,
    'application': False,
    'license': 'LGPL-3',
}
