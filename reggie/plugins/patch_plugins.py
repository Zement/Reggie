"""Patch-level plugin registry and the uniform hook helper.

Reggie supports *patch plugins*: named feature toggles a game patch declares in
its ``plugins.xml`` (loaded into ``gamedef.plugins`` by
:mod:`reggie.io.gamedef`). Feature code then checks whether a plugin is enabled
for the active patch to decide whether to show UI / change behaviour.

Historically each check was written inline as ``'name' in globals_.gamedef.plugins``
with a raw string literal. Those literals drifted — e.g. the Connected Pipe hook
in the entrance editor checked ``'connected_pipe_direction'`` while every
declaration used ``'connected_pipe_exit'``, so the feature silently never
activated. This module removes that whole class of bug:

* **Plugin IDs are named constants** (`CONNECTED_PIPE_EXIT`, …) — one source of
  truth, grep-able, no raw strings at the hook sites.
* **:func:`is_enabled`** is the single, uniform way to test a hook.
* **:data:`REGISTRY`** holds each plugin's id / display name / default params, so
  the default-``plugins.xml`` writer and the Patch Manager UI can be driven from
  the same list instead of duplicating it.

Adding a new plugin: add a constant + a `PluginDef` in ``REGISTRY`` here, then
guard the feature code with ``if is_enabled(MY_PLUGIN, gamedef): …``. That's the
whole uniform pattern — the hook points themselves are still wherever the feature
lives (unavoidably "random"), but they all look the same and share one contract.
"""

from dataclasses import dataclass, field


# ---- Plugin IDs (the single source of truth for the string keys) ------------

CONNECTED_PIPE_EXIT = 'connected_pipe_exit'
SPECIAL_EVENT_SPRITE = 'special_event_sprite'


@dataclass(frozen=True)
class PluginParam:
    """A configurable parameter of a patch plugin."""
    name: str
    default: str
    label: str = ''  # human-readable label for the Patch Manager UI

    def __post_init__(self):
        if not self.label:
            object.__setattr__(self, 'label', self.name)


@dataclass(frozen=True)
class PluginDef:
    """Static metadata for one patch plugin — the single source of truth used by
    the hook helper, the default-``plugins.xml`` writer and the Patch Manager UI."""
    id: str
    display_name: str
    description: str = ''
    params: tuple = ()  # tuple[PluginParam, ...]

    @property
    def default_params(self):
        """Param name -> default value, e.g. for writing plugins.xml."""
        return {p.name: p.default for p in self.params}


# ---- Registry: drives the default plugins.xml and the Patch Manager UI -------

REGISTRY = (
    PluginDef(
        id=CONNECTED_PIPE_EXIT,
        display_name='Connected Pipe Exit Direction',
        description='Enables the connected pipe exit direction option',
    ),
    PluginDef(
        id=SPECIAL_EVENT_SPRITE,
        display_name='Custom Special Event Sprite ID',
        description='Use a custom sprite ID for the Special Event sprite',
        params=(PluginParam('sprite_name', 'Special Event', 'Sprite Name'),),
    ),
)


def get(plugin_id):
    """Return the PluginDef for ``plugin_id``, or None."""
    for p in REGISTRY:
        if p.id == plugin_id:
            return p
    return None


def is_enabled(plugin_id, gamedef=None):
    """Return True if ``plugin_id`` is enabled for the given (or active) gamedef.

    This is the uniform hook every feature should use instead of an inline
    ``'name' in globals_.gamedef.plugins`` check. ``gamedef`` defaults to the
    active patch (``globals_.gamedef``); pass one explicitly to test a specific
    patch. Safe when no gamedef/plugins exist yet (returns False).
    """
    if gamedef is None:
        # Imported lazily to avoid a hard import cycle at module load.
        from reggie.core import globals_
        gamedef = getattr(globals_, 'gamedef', None)

    plugins = getattr(gamedef, 'plugins', None)
    return bool(plugins) and plugin_id in plugins
