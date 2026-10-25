{
    'name': 'OpenEduCat South African Test Website',
    'summary': 'A public-facing South African government-inspired test homepage',
    'version': '19.0.1.0.0',
    'category': 'Website/Theme',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/homepage.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            '/openeducat_sa_test_site/static/src/scss/homepage.scss',
        ],
    },
    'installable': True,
    'application': False,
}
