# Minecraft Bedrock Inverted Floating Library

This project procedurally generates a Bedrock Edition `.mcstructure` for an inverted floating magical library, then renders simple PNG previews by reading the generated structure file back from disk.

## Generate

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\generate_inverted_library.py
python scripts\validate_mcstructure.py out\inverted_library.mcstructure
python scripts\test_coordinate_order.py
python scripts\render_structure_preview.py out\inverted_library.mcstructure out\previews
```

Outputs:

- `out/inverted_library.mcstructure`
- `out/previews/iso.png`
- `out/previews/iso_close.png`
- `out/previews/front.png`
- `out/previews/side.png`
- `out/previews/top.png`
- `out/previews/cutaway.png`
- `out/previews/cutaway_close.png`
- `out/previews/interior_lower_top.png`
- `out/previews/interior_middle_top.png`
- `out/previews/interior_upper_top.png`

## Structure Notes

The generator intentionally uses stable full blocks and simple Bedrock little-endian NBT:

- Size: `128 x 160 x 128`
- Three open library floors with walkable surfaces at `y=45`, `y=73`, and `y=101`
- Regular central atrium, ring corridors, landing pads, docking doorways, and two block-stair cores
- 2.5-turn spiral walkway from `y=34` to `y=104`
- 26 hanging lanterns on branch arms around the outer spiral
- Ordered central crystal cluster from `y=50` to `y=108`
- Layered oxidized copper spire from `y=108` to `y=154`
- Inverted blue crystal pendant from `y=6` to `y=38`

`block_indices` are written in Bedrock ZYX order:

```python
index = x * size_y * size_z + y * size_z + z
```

Run `python scripts\test_coordinate_order.py` to generate and verify `out/coordinate_test.mcstructure`.

## Preview

The bundled preview renderer is a lightweight Pillow voxel renderer. It does not use Minecraft textures, but it color-codes bookshelves, stone, wood, copper, glowing blocks, and glass crystals so the silhouette can be checked quickly. The `cutaway.png` and `cutaway_close.png` views hide part of the front wall so the atrium and central crystal core are easier to inspect. The `interior_*_top.png` images show each library level from `walk_y` through `walk_y + 8`, making the atrium, ring corridor, docking entry, stairs, and bookshelf zones easier to audit.

You can also inspect `out/inverted_library.mcstructure` with MCStructure Preview for a more specialized external preview workflow.

## Import Into Minecraft Bedrock

Copy `out/inverted_library.mcstructure` into a world's `structures` folder. If the folder does not exist, create it.

Typical Windows Bedrock world path:

```text
%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe\LocalState\games\com.mojang\minecraftWorlds\<world_id>\structures\
```

After copying the file, load the world and run:

```text
/structure load inverted_library ~ ~ ~
```

The structure is 128 blocks wide and 160 blocks tall, so load it in open air with enough clearance.
