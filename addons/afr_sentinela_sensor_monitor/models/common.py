from odoo.exceptions import ValidationError

FORBIDDEN_CHARS = ('|', '\n', '\r')


def validate_code(value):
    if value and any(char in value for char in FORBIDDEN_CHARS):
        raise ValidationError(
            "Identificadores não podem conter '|', quebra de linha ou retorno de carro."
        )
