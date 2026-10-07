"""Tipos para la documentación OpenAPI de la aplicación (SPEC-api-surface §3)."""

from typing import Required, TypedDict


class TagMetadata(TypedDict, total=False):
    """Una entrada de `openapi_tags`, tipada para que un typo en la clave lo cace `ty` y no Swagger.

    Cada controller declara la suya junto a su router, con el mismo nombre que usa en `tags=[...]`,
    y `main.py` las reúne en el orden en que deben leerse.

    Attributes:
        name: Nombre exacto del tag; debe coincidir con el que usa el router.
        description: Qué hace el grupo, qué credencial acepta y qué rol exige. Admite Markdown.
        externalDocs: Enlace opcional a documentación externa (`{"description": ..., "url": ...}`).
    """

    name: Required[str]
    description: str
    externalDocs: dict[str, str]
