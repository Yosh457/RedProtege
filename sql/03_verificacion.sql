-- SOLO LECTURA: resultados previstos, sin exigir ID fijo al nuevo SAPU.
USE red_protege_db;
SHOW CREATE TABLE usuario_recintos;
SELECT id, nombre, activo FROM catalogo_recintos ORDER BY id;
SELECT id, nombre, activo FROM catalogo_recintos
WHERE nombre IN ('SAR La Tortuga', 'SAPU Dr. Héctor Reyno G.',
                 'SAPU El Boro', 'SAPU Yandry Añazco');
SELECT COUNT(*) AS total_asignaciones_usuario_recintos FROM usuario_recintos;
SELECT COUNT(*) AS total_casos FROM casos;
SELECT COUNT(*) AS casos_sin_recinto_valido
FROM casos c LEFT JOIN catalogo_recintos r ON r.id = c.recinto_notifica_id
WHERE r.id IS NULL;
SELECT COUNT(*) AS duplicados FROM (
 SELECT usuario_id, recinto_id FROM usuario_recintos
 GROUP BY usuario_id, recinto_id HAVING COUNT(*) > 1
) d;
