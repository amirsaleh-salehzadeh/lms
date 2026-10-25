from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug=debug)
        if self.env.user.login != 'demo':
            return visible_ids

        hidden_root_xmlids = (
            'mail.menu_root_discuss',
            'website.menu_website_configuration',
            'hr.menu_hr_root',
            'utm.menu_link_tracker_root',
        )
        menus = self.sudo()
        hidden_ids = set()
        for xmlid in hidden_root_xmlids:
            root = self.env.ref(xmlid, raise_if_not_found=False)
            if root:
                hidden_ids.update(
                    menus.search([('id', 'child_of', root.id)]).ids
                )
        return frozenset(set(visible_ids) - hidden_ids)
