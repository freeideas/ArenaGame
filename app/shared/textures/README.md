# Textures

All images here are CC0 (public domain) from [ambientCG](https://ambientcg.com), resized to 512 px and recompressed to keep the page small. Each surface has `<name>_color.jpg`, `<name>_normal.jpg` (OpenGL normal map) and `<name>_rough.jpg`.

| Name     | ambientCG asset  | Used for                      |
| -------- | ---------------- | ----------------------------- |
| plates   | MetalPlates006   | main deck top                 |
| concrete | Concrete034      | islands and pillars           |
| grate    | MetalWalkway013  | side decks and perch          |
| steel    | Metal032         | box sides and undersides      |
| painted  | PaintedMetal007  | spare                         |
| rust     | Rust004          | spare                         |
| sky.jpg  | NightSkyHDRI008  | sky (tone-mapped 2K equirectangular) |

To add one: download the 1K JPG zip from ambientCG, then `ffmpeg -i X_1K-JPG_Color.jpg -vf scale=512:512 -q:v 4 name_color.jpg` and the same for NormalGL and Roughness.
