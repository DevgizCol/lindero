# -*- coding: utf-8 -*-
"""Pruebas unitarias para el motor de notificaciones por correo."""
import unittest
from motor.correo import _plantilla_correo, enviar_correo_entrega

class TestCorreo(unittest.TestCase):
    def test_generar_plantilla(self):
        datos = {
            "referencia": "LND-20261013-ABCDEF12",
            "id_transaccion": "tx-9999",
            "monto_formateado": "$4.000 COP",
            "cliente_nombre": "Albert Zapata",
            "correo": "albertg2109@gmail.com",
            "municipio": "Malambo (Atlántico)",
            "predios": 2,
            "firmante": "Ing. Topógrafo Registrado",
            "url_descarga": "https://lindero.onrender.com/descargar/test-123"
        }
        html = _plantilla_correo(datos)
        self.assertIn("LND-20261013-ABCDEF12", html)
        self.assertIn("https://lindero.onrender.com/descargar/test-123", html)
        self.assertIn("$4.000 COP", html)
        self.assertIn("Shapefiles", html)
        self.assertIn("Malambo", html)

    def test_envio_simulado(self):
        # Sin API keys configuradas, debe procesar en modo simulación sin error
        datos = {
            "referencia": "LND-20261013-SIMULADO",
            "correo": "test@ejemplo.com",
            "monto_formateado": "$4.000 COP",
            "url_descarga": "https://lindero.onrender.com/descargar/test-sim"
        }
        ok = enviar_correo_entrega(datos)
        self.assertTrue(ok)

if __name__ == "__main__":
    unittest.main()

