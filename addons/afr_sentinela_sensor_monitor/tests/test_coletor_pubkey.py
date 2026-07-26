from odoo.tests.common import TransactionCase


PEM_EXEMPLO = None  # preenchido no setUp a partir de uma chave gerada


class TestColetorPubkey(TransactionCase):
    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        chave = ec.generate_private_key(ec.SECP256R1())
        self.pem = chave.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        # fingerprint esperado (mesma formula do contrato.identidade)
        import hashlib
        der = chave.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        d = hashlib.sha256(der).hexdigest().upper()
        self.fp_esperado = ':'.join(d[i:i+2] for i in range(0, len(d), 2))
        self.partner = self.env['res.partner'].create({'name': 'Cliente Teste'})
        self.site = self.env['sensor_monitor.site'].create({
            'name': 'Site Teste',
            'partner_id': self.partner.id,
            'site_code': 'SITE-PUBKEY',
            'vertical': 'cme_hospitalar',
        })
        self.hub = self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': self.site.id, 'hub_code': 'HUB-T',
        })

    def _coletor(self, pem):
        return self.env['sensor_monitor.coletor'].create({
            'name': 'C', 'coletor_code': 'COL-T', 'hub_id': self.hub.id,
            'tipo': 'esp32_wifi', 'pubkey_pem': pem,
        })

    def test_fingerprint_derivado_do_pem(self):
        col = self._coletor(self.pem)
        self.assertEqual(col.pubkey_fingerprint, self.fp_esperado)

    def test_pem_invalido_fingerprint_vazio(self):
        col = self._coletor('nao eh pem')
        self.assertFalse(col.pubkey_fingerprint)

    def test_pem_vazio_preserva_fingerprint_manual(self):
        # Coletor com PEM válido (fingerprint calculado a partir dele).
        col = self._coletor(self.pem)
        self.assertEqual(col.pubkey_fingerprint, self.fp_esperado)
        # Fingerprint manual sobrescrito diretamente (sem alterar pubkey_pem,
        # então não dispara recompute).
        col.write({'pubkey_fingerprint': 'AA:BB'})
        self.assertEqual(col.pubkey_fingerprint, 'AA:BB')
        # Zerar o PEM É uma mudança real de dependência: dispara o recompute
        # de verdade (simula o -u com uma linha que tinha fingerprint setado
        # manualmente e ainda não recebeu o PEM do coletor).
        col.pubkey_pem = False
        self.assertEqual(col.pubkey_fingerprint, 'AA:BB',
                          'fingerprint manual não deve ser apagado quando pubkey_pem fica vazio')
