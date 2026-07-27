import unittest

from scripts.backfill_pubkey_odoo import parear_registro


class TestBackfillPareamento(unittest.TestCase):
    def test_pareia_por_coletor_code(self):
        registro = {'COL-1': 'PEM1', 'COL-9': 'PEM9'}
        coletores_odoo = [{'id': 5, 'coletor_code': 'COL-1'}]
        pares = parear_registro(registro, coletores_odoo)
        self.assertEqual(pares, [(5, 'PEM1')])  # COL-9 sem coletor no Odoo -> ignorado
