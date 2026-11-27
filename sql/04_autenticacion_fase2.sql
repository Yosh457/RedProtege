-- REDPROTEGE: EJECUTAR UNA SOLA VEZ SOLO DESPUÉS DE RESPALDO VERIFICADO.
-- MySQL 8: seleccionar red_protege_db de DESARROLLO; detener Flask.
-- No ejecutar en producción sin plan de despliegue controlado.
USE red_protege_db;

ALTER TABLE usuarios
    MODIFY COLUMN password_hash VARCHAR(255) NULL,
    MODIFY COLUMN reset_token VARCHAR(64) NULL,
    ADD COLUMN activacion_pendiente BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN activacion_token_hash VARCHAR(64) NULL UNIQUE,
    ADD COLUMN activacion_token_expiracion DATETIME NULL,
    ADD COLUMN sesion_version INT NOT NULL DEFAULT 1;

-- El esquema previo guardaba tokens en claro: invalidarlos al migrar.
UPDATE usuarios SET reset_token = NULL, reset_token_expiracion = NULL;

-- Control de frecuencia compartido entre procesos usando MySQL.
CREATE TABLE IF NOT EXISTS limites_solicitudes (
    clave CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    ventana BIGINT UNSIGNED NOT NULL,
    intentos INT UNSIGNED NOT NULL DEFAULT 0,
    expira_en DATETIME NOT NULL,
    PRIMARY KEY (clave, ventana),
    INDEX idx_limites_expira (expira_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Limpieza opcional por tarea programada (NO ejecutar automáticamente):
-- DELETE FROM limites_solicitudes WHERE expira_en < UTC_TIMESTAMP() - INTERVAL 1 DAY;
