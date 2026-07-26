"""Root pytest configuration.

Mocks out Odoo and other heavy dependencies for pure unit tests.
This allows running pure unit tests without requiring Odoo to be installed.
"""
import sys
from unittest.mock import MagicMock

# Mock Odoo and its modules BEFORE anything else imports them
sys.modules['odoo'] = MagicMock()
sys.modules['odoo.exceptions'] = MagicMock()
sys.modules['odoo.tests'] = MagicMock()
sys.modules['odoo.tests.common'] = MagicMock()
sys.modules['odoo.models'] = MagicMock()
sys.modules['odoo.fields'] = MagicMock()

# Mock other potentially heavy dependencies
sys.modules['requests'] = MagicMock()
sys.modules['serial'] = MagicMock()
sys.modules['serial.tools'] = MagicMock()
sys.modules['serial.tools.list_ports'] = MagicMock()
sys.modules['paho'] = MagicMock()
sys.modules['paho.mqtt'] = MagicMock()
sys.modules['paho.mqtt.client'] = MagicMock()
sys.modules['cryptography'] = MagicMock()
sys.modules['cryptography.hazmat'] = MagicMock()
sys.modules['cryptography.hazmat.primitives'] = MagicMock()
sys.modules['cryptography.hazmat.primitives.serialization'] = MagicMock()
