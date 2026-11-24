"""Pruebas locales sin MySQL ni archivos clinicos. Python 3.10+."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.rutas_actas import resolver_ruta_acta

class TestSeguridadRutasActas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.jaula = self.base / 'uploads' / 'actas'
        self.jaula.mkdir(parents=True)
        self.pdf = self.jaula / 'acta_1_FIC-001.pdf'
        self.pdf.write_bytes(b'%PDF-1.4\n%%EOF')

    def resuelve(self, ruta):
        return resolver_ruta_acta(self.base, ruta)

    def test_ruta_normal(self):
        self.assertEqual(self.resuelve('uploads/actas/acta_1_FIC-001.pdf'), str(self.pdf.resolve()))

    def test_separadores_windows(self):
        self.assertEqual(self.resuelve(r'uploads\actas\acta_1_FIC-001.pdf'), str(self.pdf.resolve()))

    def test_pdf_en_subcarpeta(self):
        sub = self.jaula / 'historicas'
        sub.mkdir()
        self.assertEqual(self.resuelve('uploads/actas/historicas/acta.pdf'), str((sub / 'acta.pdf').resolve()))

    def test_rechaza_escape_padre(self):
        for ruta in ('uploads/actas/../../../secreto.pdf', 'uploads/actas/../otro.pdf',
                     r'uploads\actas\..\..\secreto.pdf'):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                self.resuelve(ruta)

    def test_rechaza_absolutas(self):
        for ruta in ('/etc/passwd', r'C:\Windows\temp\acta.pdf', r'\\servidor\recurso\acta.pdf'):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                self.resuelve(ruta)

    def test_rechaza_fuera_jaula_y_prefijo_parecido(self):
        for ruta in ('otros/acta.pdf', 'uploads/actas2/acta.pdf', 'uploads/actas'):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                self.resuelve(ruta)

    def test_rechaza_extension_distinta(self):
        for ruta in ('uploads/actas/informe.txt', 'uploads/actas/documento.pdf.exe'):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                self.resuelve(ruta)

    def test_rechaza_valores_invalidos(self):
        for ruta in (None, '', ' ', 123, 'uploads/actas/a\x00.pdf'):
            with self.subTest(ruta=repr(ruta)), self.assertRaises(ValueError):
                self.resuelve(ruta)

    def test_rechaza_symlink_fuera_de_la_jaula(self):
        externo = self.base / 'fuera.pdf'
        externo.write_bytes(b'%PDF-1.4\n%%EOF')
        enlace = self.jaula / 'enlace.pdf'
        try:
            enlace.symlink_to(externo)
        except (OSError, NotImplementedError):
            self.skipTest('El sistema no permite crear symlinks en este entorno')
        with self.assertRaises(ValueError):
            self.resuelve('uploads/actas/enlace.pdf')

    def test_rechaza_symlink_directorio_fuera_de_la_jaula(self):
        externo = self.base / 'externo'
        externo.mkdir()
        (externo / 'secreto.pdf').write_bytes(b'%PDF-1.4\n%%EOF')
        enlace = self.jaula / 'subdir'
        try:
            enlace.symlink_to(externo, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('El sistema no permite crear symlinks en este entorno')
        with self.assertRaises(ValueError):
            self.resuelve('uploads/actas/subdir/secreto.pdf')

if __name__ == '__main__':
    unittest.main()