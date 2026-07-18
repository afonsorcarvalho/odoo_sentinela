from odoo.tests.common import TransactionCase


class TestSecurityRules(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner_a = self.env['res.partner'].create({'name': 'Hospital A'})
        self.partner_b = self.env['res.partner'].create({'name': 'Hospital B'})
        self.site_a = self.env['sensor_monitor.site'].create({
            'name': 'CME A', 'partner_id': self.partner_a.id,
            'site_code': 'SITE-A', 'vertical': 'cme_hospitalar',
        })
        self.site_b = self.env['sensor_monitor.site'].create({
            'name': 'CME B', 'partner_id': self.partner_b.id,
            'site_code': 'SITE-B', 'vertical': 'cme_hospitalar',
        })
        view_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_view')
        self.user_a = self.env['res.users'].create({
            'name': 'Usuário A', 'login': 'usuario_a@teste.com',
            'partner_id': self.partner_a.id,
            'groups_id': [(6, 0, [view_group.id, self.env.ref('base.group_user').id])],
        })

    def test_user_sees_only_own_partner_site(self):
        sites = self.env['sensor_monitor.site'].with_user(self.user_a).search([])
        self.assertIn(self.site_a, sites)
        self.assertNotIn(self.site_b, sites)

    def test_admin_group_sees_all_sites(self):
        admin_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_admin')
        admin_user = self.env['res.users'].create({
            'name': 'Admin Interno', 'login': 'admin_interno@teste.com',
            'groups_id': [(6, 0, [admin_group.id, self.env.ref('base.group_user').id])],
        })
        sites = self.env['sensor_monitor.site'].with_user(admin_user).search([])
        self.assertIn(self.site_a, sites)
        self.assertIn(self.site_b, sites)
