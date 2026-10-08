# vendor/

`three.module.min.js`: three.js r170 (MIT), unchanged, from `https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js`. Served from here so the game needs no other site.

`GLTFLoader.js` and `BufferGeometryUtils.js`: the three.js r170 add-ons from `https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/loaders/GLTFLoader.js` and `.../examples/jsm/utils/BufferGeometryUtils.js`. One change each: the `from 'three'` import now reads `from './three.module.min.js'`, and GLTFLoader imports `./BufferGeometryUtils.js` instead of `../utils/BufferGeometryUtils.js`, so they work here without an import map.
