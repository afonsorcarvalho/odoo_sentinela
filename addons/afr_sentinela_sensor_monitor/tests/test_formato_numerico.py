from odoo.exceptions import ValidationError

from .test_faixa_plausivel import TestFaixaPlausivel


class TestFormatoNumerico(TestFaixaPlausivel):
    def test_padrao_duas_casas_um_digito(self):
        sensor = self._sensor()
        self.assertEqual((sensor.casas_decimais, sensor.digitos_inteiros), (2, 1))

    def test_limites_validos_persistem(self):
        sensor = self._sensor(casas_decimais=0, digitos_inteiros=12)
        sensor.casas_decimais = 6
        self.assertEqual(sensor.casas_decimais, 6)

    def test_fora_da_faixa_levanta_erro(self):
        for vals in ({'casas_decimais': 7}, {'casas_decimais': -1},
                     {'digitos_inteiros': 0}, {'digitos_inteiros': 13}):
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                self._sensor(**vals)
