-- EJECUTAR SOLO TRAS RESPALDO Y PREVALIDACION.
-- MySQL realiza COMMIT implícito para CREATE TABLE; ROLLBACK no deshace el DDL.
-- Si usuario_recintos ya existe, DETENERSE y revisar su estructura, NO continuar a ciegas.
USE red_protege_db;

CREATE TABLE usuario_recintos (
    usuario_id INT NOT NULL,
    recinto_id INT NOT NULL,
    PRIMARY KEY (usuario_id, recinto_id),
    KEY idx_usuario_recintos_recinto (recinto_id),
    CONSTRAINT fk_usuario_recintos_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE CASCADE,
    CONSTRAINT fk_usuario_recintos_recinto FOREIGN KEY (recinto_id)
        REFERENCES catalogo_recintos (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insertar solo si no existe; no cambiar IDs ni modificar nombres existentes.
INSERT INTO catalogo_recintos (nombre, activo)
SELECT 'SAPU Yandry Añazco', 1
WHERE NOT EXISTS (
    SELECT 1 FROM catalogo_recintos WHERE nombre = 'SAPU Yandry Añazco'
);
