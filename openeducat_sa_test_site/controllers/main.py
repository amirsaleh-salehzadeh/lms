from odoo import http
from odoo.http import request


class SouthAfricanTestWebsite(http.Controller):
    @http.route('/sa-test', type='http', auth='public', website=True, sitemap=True)
    def homepage(self, **kwargs):
        return request.render('openeducat_sa_test_site.sa_test_homepage')
