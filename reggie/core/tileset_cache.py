"""Cache of decompressed tileset archives (Block D, phase 2).

Loading a tileset is dominated by one step. Measured on MidnightWii, whose
tilesets ship LH-compressed:

    read file        0.0003 s
    LH decompress    1.8192 s   <- 99.6% of the total
    U8 parse         0.0005 s
    LZ77 texture     0.0012 s
    decode texture   0.0032 s
    slice 256 tiles  0.0010 s

`libs/lz77_huffman.py` is a pure-Python Huffman decoder costing roughly
18 ms per KB of input, and `nsmblib` - which is installed - has no
`decompressLH` to hand the work to, so there is no fast path to fall back on.

That makes this cache the whole fix for "tileset loading is slow on consecutive
loads": the decompression cannot be made faster here, but it does not have to
happen twice. A four-slot level on MidnightWii pays about 7.6 s per load today,
nearly all of it repeating work done moments earlier.

What is cached is the *decompressed archive bytes*, keyed by resolved path plus
the file's mtime and size. Deliberately not the parsed U8, the QPixmaps or the
TilesetTile objects: bytes are immutable and cheap to hand out, while the
decoded tiles are per-session mutable state (animation frames, override
processing) that must not be shared between two open areas.
"""

import os


class TilesetCache:
    """Decompressed archive bytes, keyed by path + mtime + size.

    Bounded by total retained bytes rather than entry count, since tileset
    archives vary from tens of KB to a few MB and a count-based bound would
    either waste memory or evict far too eagerly.
    """

    #: Default ceiling on retained decompressed bytes. Sized so a full level's
    #: four slots plus a second area's worth stay resident on any real patch.
    DEFAULT_LIMIT = 64 * 1024 * 1024

    def __init__(self, limit=DEFAULT_LIMIT):
        self.limit = limit
        self._entries = {}      # key -> bytes
        self._order = []        # keys, least-recently-used first
        self._bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # -- keys ------------------------------------------------------------

    @staticmethod
    def key_for(path):
        """Identity for a file: its path, mtime and size.

        mtime and size are part of the key rather than checked separately so
        that an edited tileset simply misses instead of serving stale bytes.
        A patch being reinstalled under the same path is the case that matters.

        Returns None if the file cannot be stat'd, which makes the caller treat
        it as uncacheable rather than raising.
        """
        try:
            st = os.stat(path)
        except OSError:
            return None
        return (os.path.normcase(os.path.abspath(path)), st.st_mtime_ns, st.st_size)

    # -- access ----------------------------------------------------------

    def get(self, key):
        if key is None:
            return None

        data = self._entries.get(key)
        if data is None:
            self.misses += 1
            return None

        self.hits += 1
        # Move to the most-recently-used end.
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)
        return data

    def put(self, key, data):
        if key is None or data is None:
            return

        # A single archive larger than the whole budget is not worth evicting
        # everything else for.
        if len(data) > self.limit:
            return

        if key in self._entries:
            self._bytes -= len(self._entries[key])
            try:
                self._order.remove(key)
            except ValueError:
                pass

        self._entries[key] = data
        self._order.append(key)
        self._bytes += len(data)

        while self._bytes > self.limit and self._order:
            oldest = self._order.pop(0)
            self._bytes -= len(self._entries.pop(oldest, b''))
            self.evictions += 1

    # -- maintenance -----------------------------------------------------

    def clear(self):
        self._entries.clear()
        del self._order[:]
        self._bytes = 0

    def invalidate_path(self, path):
        """Drop every entry for a path, whatever its mtime/size.

        For when a file is known to have changed under us - a patch reinstall,
        or a collab asset transfer landing new tilesets.
        """
        target = os.path.normcase(os.path.abspath(path))
        for key in [k for k in self._entries if k[0] == target]:
            self._bytes -= len(self._entries.pop(key, b''))
            try:
                self._order.remove(key)
            except ValueError:
                pass

    @property
    def retained_bytes(self):
        return self._bytes

    def stats(self):
        total = self.hits + self.misses
        return {
            'entries': len(self._entries),
            'bytes': self._bytes,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': (self.hits / total) if total else 0.0,
        }


#: The editor-wide cache. Keyed by resolved path, so it is deliberately shared
#: across sessions: two areas using the same tileset should decompress it once.
cache = TilesetCache()
