"""Comprobaciones de metadatos SQLAlchemy sin acceso a MySQL."""
import unittest
from sqlalchemy.orm import configure_mappers
from models import db, Usuario, CatalogoRecinto, Caso


class TestUsuarioRecintosModelo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def test_tabla_puente_y_clave_compuesta(self):
        tabla = db.metadata.tables['usuario_recintos']
        self.assertEqual(set(tabla.columns.keys()), {'usuario_id', 'recinto_id'})
        self.assertEqual({col.name for col in tabla.primary_key.columns},
                         {'usuario_id', 'recinto_id'})
        self.assertFalse(tabla.c.usuario_id.nullable)
        self.assertFalse(tabla.c.recinto_id.nullable)

    def test_claves_foraneas_y_borrado(self):
        tabla = db.metadata.tables['usuario_recintos']
        refs = {col.name: next(iter(col.foreign_keys)) for col in tabla.columns}
        self.assertEqual(refs['usuario_id'].target_fullname, 'usuarios.id')
        self.assertEqual(refs['recinto_id'].target_fullname, 'catalogo_recintos.id')
        self.assertEqual(refs['usuario_id'].ondelete, 'CASCADE')
        self.assertEqual(refs['recinto_id'].ondelete, 'RESTRICT')

    def test_relacion_bidireccional_y_secundaria(self):
        self.assertEqual(Usuario.recintos.property.secondary.name, 'usuario_recintos')
        self.assertEqual(CatalogoRecinto.usuarios_autorizados.property.secondary.name,
                         'usuario_recintos')
        self.assertEqual(Usuario.recintos.property.back_populates, 'usuarios_autorizados')
        self.assertEqual(CatalogoRecinto.usuarios_autorizados.property.back_populates,
                         'recintos')

    def test_se_preservan_relaciones_existentes(self):
        self.assertEqual(Usuario.ciclos.property.secondary.name, 'usuario_ciclos')
        self.assertEqual(Caso.recinto_notifica.property.mapper.class_, CatalogoRecinto)
        self.assertIn('recinto_notifica_id', Caso.__table__.c)
        self.assertIn('asignado_ts_id', Caso.__table__.c)
        self.assertIn('asignado_coord_id', Caso.__table__.c)


if __name__ == '__main__':
    unittest.main()
