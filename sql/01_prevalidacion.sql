-- SOLO LECTURA. Revisar resultados antes de migrar.
USE red_protege_db;
SELECT DATABASE() AS base_activa;
SHOW TABLES LIKE 'usuario_recintos';
SHOW CREATE TABLE usuarios;
SHOW CREATE TABLE catalogo_recintos;
SELECT id, nombre, activo FROM catalogo_recintos ORDER BY id;
SELECT COUNT(*) AS casos_previos FROM casos;
SELECT COUNT(*) AS casos_sin_recinto_valido
FROM casos c LEFT JOIN catalogo_recintos r ON r.id = c.recinto_notifica_id
WHERE r.id IS NULL;
SELECT id, nombre, activo FROM catalogo_recintos WHERE nombre = 'SAPU Yandry Añazco';
