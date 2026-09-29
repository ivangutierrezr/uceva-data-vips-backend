# Scienti-UCEVA Backend Guidelines

## Contexto Base
- El backend Django es la fuente de verdad del dominio, los contratos API y los procesos batch.
- Antes de cambios importantes, reconstruye contexto desde test_backend/00_DOCUMENTO_BASE_CONTEXTO.md y los documentos enlazados alli.
- Si un documento historico contradice el codigo actual, prevalece el codigo actual.

## Prioridad Tecnica
- Entiende primero models.py, despues urls.py y views.py, y luego management commands.
- Trata sync_scienti, enrich_articles y enrich_researchers como piezas sensibles del sistema.
- Prefiere arreglos de causa raiz y cambios pequenos, consistentes con el estilo existente.

## Convenciones Del Proyecto
- Verifica que los endpoints existan realmente antes de proponer o consumir cambios desde frontend.
- Asume que parte de la logica esta concentrada en scienti/views.py y revisa impactos relacionados antes de editar.
- Ten en cuenta que datasets externos condicionan parte del enriquecimiento; si faltan, dilo de forma explicita.

## Restricciones Operativas
- No cambiar configuracion de entorno, base de datos o despliegue salvo que la tarea lo pida.
- No ejecutar sincronizaciones o enriquecimientos pesados si no son necesarios para resolver la tarea.
- No levantar servidores ni ejecutar builds salvo solicitud explicita del usuario.

## Validacion
- Cuando hagas cambios, valida con chequeos dirigidos, revision de errores o pruebas puntuales si aplica.
- Señala claramente cualquier diferencia entre lo documentado y lo implementado.